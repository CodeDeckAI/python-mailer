#!/usr/bin/env python3
"""
CodeDeck Mailer - Send personalized emails using Gmail API.

Usage:
    python mailer.py --dry-run     # Test without sending
    python mailer.py --limit 3     # Send only 3 emails
    python mailer.py               # Run full campaign
    python mailer.py --reset       # Clear progress and start fresh

https://codedeckai.com
"""

import argparse
import base64
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pymongo import MongoClient

# ============================================================================
# FILE PATHS
# ============================================================================

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CONFIG_PATH = Path("config/config.json")
CREDENTIALS_PATH = Path("config/credentials.json")
TOKEN_PATH = Path("data/token.json")
PROGRESS_PATH = Path("data/progress.json")
EMAILS_PATH = Path("data/emails.json")
TEMPLATE_PATH = Path("data/template.txt")


# ============================================================================
# CONFIG LOADER
# ============================================================================

def load_config() -> dict:
    """Load configuration from config/config.json."""
    if not CONFIG_PATH.exists():
        print(f"\nERROR: {CONFIG_PATH} not found!")
        print(f"\nCopy config/config.example.json to {CONFIG_PATH} and fill in your settings.")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    return config


def load_template() -> tuple[str, str]:
    """
    Load email template from data/template.txt.

    Format:
        SUBJECT: Your subject line here
        ---
        Your email body here
    """
    if not TEMPLATE_PATH.exists():
        print(f"\nERROR: {TEMPLATE_PATH} not found!")
        print(f"\nCopy data/template.example.txt to {TEMPLATE_PATH} and customize your message.")
        sys.exit(1)

    with open(TEMPLATE_PATH) as f:
        content = f.read()

    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        print(f"\nERROR: Invalid template format in {TEMPLATE_PATH}")
        print("The file must have a SUBJECT: line, then '---' on its own line, then the body.")
        sys.exit(1)

    subject_line = parts[0].strip()
    if not subject_line.startswith("SUBJECT:"):
        print(f"\nERROR: Template must start with 'SUBJECT: ...'")
        sys.exit(1)

    subject = subject_line[len("SUBJECT:"):].strip()
    body = parts[1].strip()

    return subject, body


# ============================================================================
# GMAIL AUTHENTICATION
# ============================================================================

class GmailAuth:
    """Handle Gmail OAuth2 authentication."""

    def __init__(self):
        self.creds = None
        self.service = None

    def authenticate(self):
        """Load or create OAuth credentials and build Gmail service."""
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                print("Refreshing expired token...")
                self.creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    print(f"\nERROR: {CREDENTIALS_PATH} not found!")
                    print("\nTo set up Gmail API:")
                    print("1. Go to https://console.cloud.google.com/")
                    print("2. Create a project")
                    print("3. Enable Gmail API")
                    print("4. Create OAuth credentials (Desktop app)")
                    print(f"5. Download JSON to {CREDENTIALS_PATH}")
                    sys.exit(1)

                print("\nStarting OAuth authorization flow...")
                print("A browser window will open for you to authorize the app.\n")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as f:
                f.write(self.creds.to_json())
            print(f"Token saved to {TOKEN_PATH}")

        self.service = build("gmail", "v1", credentials=self.creds)
        print("Gmail authenticated successfully!\n")
        return self.service

    def send_email(self, to_email: str, subject: str, body: str, sender_name: str) -> bool:
        """Send an email via Gmail API."""
        try:
            message = MIMEText(body)
            message["to"] = to_email
            message["subject"] = subject
            message["from"] = sender_name

            encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
            self.service.users().messages().send(
                userId="me", body={"raw": encoded}
            ).execute()
            return True
        except HttpError as e:
            raise Exception(f"Gmail API error: {e}")


# ============================================================================
# SPINTAX PROCESSOR
# ============================================================================

def process_spintax(text: str) -> str:
    """
    Process spintax in text: {option1|option2|option3} -> random choice.
    """
    pattern = r"\{([^{}]+)\}"

    def replace_spin(match):
        options = match.group(1).split("|")
        return random.choice(options)

    while re.search(pattern, text):
        text = re.sub(pattern, replace_spin, text)

    return text


def replace_variables(text: str, variables: dict) -> str:
    """Replace {{variable}} placeholders with values."""
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def build_message(first_name: str, subject_template: str, body_template: str) -> tuple[str, str]:
    """Build personalized subject and body with random variations."""
    variables = {"first_name": first_name}

    subject = replace_variables(subject_template, variables)
    subject = process_spintax(subject)

    body = replace_variables(body_template, variables)
    body = process_spintax(body)

    return subject, body


# ============================================================================
# PROGRESS TRACKER
# ============================================================================

class ProgressTracker:
    """Track email sending progress for resume capability."""

    def __init__(self):
        self.data = {
            "campaign": "email-campaign",
            "sent": [],
            "failed": {},
            "last_updated": None,
            "daily_count": 0,
            "daily_date": None,
        }
        self._load()

    def _load(self):
        if PROGRESS_PATH.exists():
            try:
                with open(PROGRESS_PATH) as f:
                    self.data = json.load(f)
                print(f"Loaded progress: {len(self.data['sent'])} sent, {len(self.data['failed'])} failed")
            except json.JSONDecodeError:
                print("Warning: Could not parse progress file, starting fresh")

    def _save(self):
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)

        temp_path = PROGRESS_PATH.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(self.data, f, indent=2)
        temp_path.replace(PROGRESS_PATH)

    def is_sent(self, email: str) -> bool:
        return email.lower() in [e.lower() for e in self.data["sent"]]

    def mark_sent(self, email: str):
        self.data["sent"].append(email)
        self._update_daily_count()
        self._save()

    def mark_failed(self, email: str, reason: str):
        self.data["failed"][email] = reason
        self._save()

    def _update_daily_count(self):
        today = datetime.now(timezone.utc).date().isoformat()
        if self.data.get("daily_date") != today:
            self.data["daily_date"] = today
            self.data["daily_count"] = 1
        else:
            self.data["daily_count"] = self.data.get("daily_count", 0) + 1

    def get_daily_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.data.get("daily_date") != today:
            return 0
        return self.data.get("daily_count", 0)

    def reset(self):
        self.data = {
            "campaign": "email-campaign",
            "sent": [],
            "failed": {},
            "last_updated": None,
            "daily_count": 0,
            "daily_date": None,
        }
        self._save()
        print("Progress reset!")


# ============================================================================
# RECIPIENT FETCHER
# ============================================================================

def extract_first_name(full_name: str | None) -> str:
    """Extract first name from full name, with fallback."""
    if not full_name or not full_name.strip():
        return "there"
    return full_name.strip().split()[0]


def fetch_from_mongodb(config: dict) -> dict[str, dict]:
    """Fetch recipients from MongoDB. Returns {email: {email, first_name, source}}."""
    mongo_config = config.get("mongodb", {})
    if not mongo_config.get("enabled", False):
        return {}

    recipients = {}
    uri = mongo_config["uri"]
    db_name = mongo_config["database"]
    coll_name = mongo_config["collection"]
    email_field = mongo_config.get("email_field", "email")
    name_field = mongo_config.get("name_field", "name")
    query_filter = mongo_config.get("filter", {})

    print(f"Connecting to MongoDB ({db_name}/{coll_name})...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        db = client[db_name]
        collection = db[coll_name]

        cursor = collection.find(query_filter, {email_field: 1, name_field: 1})

        count = 0
        for doc in cursor:
            email = doc.get(email_field)
            if not email or not isinstance(email, str):
                continue

            email = email.strip().lower()
            if not email or "@" not in email:
                continue

            if email in recipients:
                continue

            full_name = doc.get(name_field)
            first_name = extract_first_name(full_name)

            recipients[email] = {
                "email": email,
                "first_name": first_name,
                "source": "MongoDB",
            }
            count += 1

        client.close()
        print(f"  Found {count} recipients from MongoDB")

    except Exception as e:
        print(f"  ERROR connecting to MongoDB: {e}")

    return recipients


def fetch_from_json() -> dict[str, dict]:
    """Fetch recipients from data/emails.json. Returns {email: {email, first_name, source}}."""
    if not EMAILS_PATH.exists():
        return {}

    recipients = {}
    try:
        with open(EMAILS_PATH) as f:
            data = json.load(f)

        for entry in data.get("recipients", []):
            email = entry.get("email")
            if not email or not isinstance(email, str):
                continue

            email = email.strip().lower()
            if not email or "@" not in email:
                continue

            if email in recipients:
                continue

            name = entry.get("name")
            first_name = extract_first_name(name)

            recipients[email] = {
                "email": email,
                "first_name": first_name,
                "source": "JSON",
            }

        print(f"  Found {len(recipients)} recipients from emails.json")

    except (json.JSONDecodeError, Exception) as e:
        print(f"  ERROR reading emails.json: {e}")

    return recipients


def fetch_recipients(config: dict) -> list[dict]:
    """
    Fetch recipients from all configured sources and deduplicate.
    Sources: MongoDB (if enabled) + data/emails.json (if exists).
    Returns list of {email, first_name, source}.
    """
    all_recipients = {}

    # MongoDB source
    mongo_recipients = fetch_from_mongodb(config)
    all_recipients.update(mongo_recipients)

    # JSON file source
    json_recipients = fetch_from_json()
    for email, data in json_recipients.items():
        if email not in all_recipients:
            all_recipients[email] = data

    # Shuffle for varied sending order
    recipients = list(all_recipients.values())
    random.shuffle(recipients)

    print(f"\nTotal unique recipients: {len(recipients)}")
    return recipients


# ============================================================================
# RATE LIMITER
# ============================================================================

def calculate_delay(config: dict) -> float:
    """Calculate delay with jitter to avoid pattern detection."""
    rate = config.get("rate_limiting", {})
    base = rate.get("base_interval_seconds", 180)
    jitter_min = rate.get("jitter_range_min", 0)
    jitter_max = rate.get("jitter_range_max", 45)
    jitter = random.uniform(jitter_min, jitter_max)
    return base + jitter


def wait_with_countdown(seconds: float):
    """Wait with a countdown display."""
    end_time = time.time() + seconds
    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        print(f"\r  Waiting: {mins:02d}:{secs:02d} ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 30 + "\r", end="")


# ============================================================================
# MAIN RUNNER
# ============================================================================

def run_campaign(dry_run: bool = False, limit: int | None = None, test_email: str | None = None):
    """Run the email campaign."""
    print("=" * 60)
    print("CodeDeck Mailer")
    print("=" * 60)
    print()

    # Load configuration
    config = load_config()
    sender_name = config.get("sender_name", "Mailer")
    rate = config.get("rate_limiting", {})
    daily_limit = rate.get("daily_limit", 100)

    # Load email template
    subject_template, body_template = load_template()

    # Initialize progress tracker
    progress = ProgressTracker()

    # Check daily limit
    daily_count = progress.get_daily_count()
    if daily_count >= daily_limit:
        print(f"\nDaily limit reached ({daily_limit} emails)!")
        print("Please wait until tomorrow to continue.")
        return

    remaining_today = daily_limit - daily_count
    print(f"Daily quota: {daily_count}/{daily_limit} sent today, {remaining_today} remaining")

    # Use test email or fetch from sources
    if test_email:
        print(f"\n[TEST MODE] Sending to: {test_email}")
        name_part = test_email.split("@")[0]
        first_name = name_part.split(".")[0].capitalize()
        recipients = [{"email": test_email, "first_name": first_name, "source": "Test"}]
    else:
        print("\nFetching recipients...")
        recipients = fetch_recipients(config)

    if not recipients:
        print("No recipients found!")
        print("Add recipients to data/emails.json and/or enable MongoDB in config/config.json.")
        return

    # Filter out already sent
    pending = [r for r in recipients if not progress.is_sent(r["email"])]
    print(f"Pending emails: {len(pending)} (skipping {len(recipients) - len(pending)} already sent)")

    if not pending:
        print("\nAll emails have been sent!")
        return

    # Apply limit
    if limit:
        pending = pending[:limit]
        print(f"Limited to {limit} emails for this run")

    # Cap at daily remaining
    if len(pending) > remaining_today:
        pending = pending[:remaining_today]
        print(f"Capped at {remaining_today} emails (daily limit)")

    # Dry run mode
    if dry_run:
        print("\n[DRY RUN MODE - No emails will be sent]\n")
        print("Recipients to send:")
        for i, r in enumerate(pending[:20], 1):
            subject, _ = build_message(r["first_name"], subject_template, body_template)
            print(f"  {i}. {r['email']} ({r['first_name']}) - {r['source']}")
            print(f"      Subject: {subject}")
        if len(pending) > 20:
            print(f"  ... and {len(pending) - 20} more")

        print("\n\nSample email preview:")
        print("-" * 40)
        sample = pending[0]
        subject, body = build_message(sample["first_name"], subject_template, body_template)
        print(f"To: {sample['email']}")
        print(f"From: {sender_name}")
        print(f"Subject: {subject}")
        print(f"\n{body}")
        print("-" * 40)
        return

    # Authenticate Gmail
    gmail = GmailAuth()
    gmail.authenticate()

    # Send emails
    print(f"\nStarting to send {len(pending)} emails...")
    print("Press Ctrl+C to pause (progress is saved)\n")

    sent_count = 0
    for i, recipient in enumerate(pending, 1):
        email = recipient["email"]
        first_name = recipient["first_name"]

        subject, body = build_message(first_name, subject_template, body_template)

        print(f"[{i}/{len(pending)}] Sending to {email}...", end=" ", flush=True)

        try:
            gmail.send_email(email, subject, body, sender_name)
            progress.mark_sent(email)
            sent_count += 1
            print("Sent")

        except Exception as e:
            error_msg = str(e)
            progress.mark_failed(email, error_msg)
            print(f"Failed: {error_msg}")

            if "429" in error_msg or "quota" in error_msg.lower():
                print("\nRate limit hit! Waiting 5 minutes before retry...")
                wait_with_countdown(300)

        # Wait between emails (except after last one)
        if i < len(pending):
            delay = calculate_delay(config)
            wait_with_countdown(delay)

    # Summary
    print("\n" + "=" * 60)
    print("Campaign Summary")
    print("=" * 60)
    print(f"Sent this run: {sent_count}")
    print(f"Total sent: {len(progress.data['sent'])}")
    print(f"Total failed: {len(progress.data['failed'])}")
    print(f"Remaining: {len(recipients) - len(progress.data['sent']) - len(progress.data['failed'])}")


def main():
    parser = argparse.ArgumentParser(
        description="CodeDeck Mailer - Send personalized emails using Gmail API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Send only N emails (for testing)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear progress and start fresh",
    )
    parser.add_argument(
        "--to",
        type=str,
        help="Send test email to specific address (bypasses other sources)",
    )

    args = parser.parse_args()

    if args.reset:
        tracker = ProgressTracker()
        tracker.reset()
        if not args.dry_run and args.limit is None:
            return

    try:
        run_campaign(dry_run=args.dry_run, limit=args.limit, test_email=args.to)
    except KeyboardInterrupt:
        print("\n\nPaused! Progress has been saved.")
        print("Run the script again to resume from where you left off.")


if __name__ == "__main__":
    main()
