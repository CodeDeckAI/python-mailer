# CodeDeck Mailer

A personalized email campaign tool built by [Bruno Bertapeli](https://x.com/brunobertapeli), powered by the Gmail API.

Part of the [CodeDeckAI.com](https://codedeckai.com) ecosystem.

## What It Does

CodeDeck Mailer sends personalized emails to a list of recipients using the Gmail API. It supports:

- **Two recipient sources**: MongoDB database and/or a local JSON file
- **Spintax**: Randomize words and phrases so every email is unique (`{Hi|Hello|Hey}`)
- **Variable substitution**: Personalize with `{{first_name}}` and other placeholders
- **Smart rate limiting**: Built-in delays with jitter to stay within Gmail limits
- **Resume capability**: If interrupted, it picks up exactly where it left off
- **Daily limits**: Configurable cap to prevent exceeding Gmail quotas
- **Dry run mode**: Preview everything before sending a single email

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/codedeck-mailer.git
cd codedeck-mailer
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up Gmail API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Gmail API** (APIs & Services > Library > search "Gmail API")
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. Select **Desktop app** as the application type
7. Download the JSON file and save it as `config/credentials.json`

The first time you run the script, a browser window will open asking you to authorize the app. After that, a token is saved locally and you won't need to authorize again until it expires.

### 4. Configure the mailer

```bash
cp config/config.example.json config/config.json
```

Edit `config/config.json` with your settings:

```json
{
  "sender_name": "Your Name",
  "rate_limiting": {
    "emails_per_hour": 20,
    "base_interval_seconds": 180,
    "jitter_range_min": 0,
    "jitter_range_max": 45,
    "daily_limit": 100
  },
  "mongodb": {
    "enabled": false,
    "uri": "mongodb+srv://user:password@cluster.mongodb.net/dbname",
    "database": "your_database",
    "collection": "users",
    "filter": {},
    "email_field": "email",
    "name_field": "name"
  }
}
```

- Set `mongodb.enabled` to `true` if you want to pull recipients from a MongoDB collection
- The script looks for the field specified in `email_field` for email addresses and `name_field` for recipient names
- You can use `filter` to query only specific documents (e.g., `{"subscribed": true}`)

### 5. Add your recipients

You can provide recipients via MongoDB (configured above), a JSON file, or both. Duplicates are automatically removed.

```bash
cp data/emails.example.json data/emails.json
```

Edit `data/emails.json`:

```json
{
  "recipients": [
    {
      "email": "john@example.com",
      "name": "John Doe"
    },
    {
      "email": "jane@example.com",
      "name": "Jane Smith"
    },
    {
      "email": "no-name@example.com"
    }
  ]
}
```

The `name` field is optional. If missing, the email will use "there" as the fallback (e.g., "Hey there,").

### 6. Create your email template

```bash
cp data/template.example.txt data/template.txt
```

Edit `data/template.txt`:

```
SUBJECT: {Hello|Hey} {{first_name}}, {check this out|this is for you}!
---
Hey {{first_name}},

Your message body goes here.

Best,
Your Name
```

**Format rules:**
- First line must start with `SUBJECT:`
- A line with just `---` separates the subject from the body
- Use `{{first_name}}` for personalization
- Use `{option1|option2|option3}` for spintax (random variation per email)

## Usage

```bash
# Preview what would be sent (no emails go out)
python mailer.py --dry-run

# Send to a specific test address first
python mailer.py --to you@gmail.com

# Send only 5 emails (good for initial testing)
python mailer.py --limit 5

# Run the full campaign
python mailer.py

# Clear all progress and start fresh
python mailer.py --reset
```

Press `Ctrl+C` at any time to pause. Progress is saved automatically, so you can resume later by running the script again.

## Gmail Best Practices (Avoid Getting Blacklisted)

Gmail has sending limits and reputation systems. Follow these practices to protect your account:

### Use multiple Gmail accounts

Do NOT send all emails from a single account. Rotate between 2-3 accounts to spread the volume. To switch accounts:

1. Delete `data/token.json`
2. Run the script again - it will open a browser for you to authorize a different Gmail account
3. The new token is saved and used for subsequent sends

### Use Google Workspace accounts

Google Workspace (paid Gmail) accounts have significantly higher sending limits and are far less likely to be flagged or blacklisted compared to free `@gmail.com` accounts:

| Account Type | Daily Limit | Risk Level |
|---|---|---|
| Free Gmail (@gmail.com) | ~500/day | Higher risk of being flagged |
| Google Workspace | ~2,000/day | Much lower risk |

If you're serious about email campaigns, use a Workspace account tied to your own domain.

### Rate limiting

The default settings are conservative on purpose:

- **3-minute base delay** between emails with random jitter
- **20 emails per hour**
- **100 emails per day** (configurable)

Do not increase these aggressively. Gmail monitors sending patterns and sudden spikes will trigger blocks.

### Content best practices

- Write emails that sound personal and human (spintax helps with this)
- Avoid spammy words in subject lines (FREE, URGENT, ACT NOW, etc.)
- Include a clear way for people to know why they received the email
- Keep emails short and relevant
- Do not include too many links

### Warm up new accounts

If using a new Gmail account, start slow:

1. **Week 1**: 10-20 emails/day
2. **Week 2**: 30-50 emails/day
3. **Week 3+**: Gradually increase to your target

### Monitor your reputation

- Check [Google Postmaster Tools](https://postmaster.google.com/) to monitor your sending domain reputation
- Watch for bounce rates - high bounces damage your reputation
- If you get a "rate limit" error, stop for the day and reduce your daily limit

## File Structure

```
codedeck-mailer/
  config/
    config.example.json    # Template - copy to config.json
    credentials.json       # Your Gmail API credentials (gitignored)
    config.json            # Your settings (gitignored)
  data/
    emails.example.json    # Template - copy to emails.json
    template.example.txt   # Template - copy to template.txt
    emails.json            # Your recipient list (gitignored)
    template.txt           # Your email template (gitignored)
    token.json             # Gmail OAuth token (gitignored, auto-generated)
    progress.json          # Send progress tracker (gitignored, auto-generated)
  mailer.py                # Main script
  requirements.txt         # Python dependencies
  .gitignore
  README.md
```

## License

MIT

---

Built by [Bruno Bertapeli](https://x.com/brunobertapeli) | [CodeDeckAI.com](https://codedeckai.com)
