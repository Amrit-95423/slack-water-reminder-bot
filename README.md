# Slack Water Reminder Bot

This is a small Python Slack bot that lets each user control their own water-reminder interval.

## Commands

- `/water set 60` starts reminders every 60 minutes.
- `/water status` shows your current interval.
- `/water off` disables your reminders.
- `/water` shows the help text.

Intervals are limited to 5 minutes through 24 hours. Settings are saved locally in `data/reminders.json` so they survive a restart. The file contains Slack user IDs and reminder times, not credentials.

## Local setup

1. Install Python 3.9 or newer, then create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```

2. Create the local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. In `.env`, replace the placeholders with the tokens from your Slack app:

   ```text
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   REMINDER_STORE_PATH=data/reminders.json
   ```

4. Run the bot:

   ```powershell
   py app.py
   ```

5. In Slack, install the app in your development workspace and try `/water set 60`.

## Slack app configuration

This first version uses Slack Bolt for Python with Socket Mode, so local development does not need a public request URL. In the Slack app settings:

1. Enable Socket Mode and create an app-level token with the `connections:write` scope.
2. Add these bot token scopes under OAuth & Permissions:
   - `chat:write` to send reminder messages.
   - `im:write` to open a direct message conversation for a user.
3. Add the `/water` slash command. A request URL is not needed while Socket Mode is enabled.
4. Install or reinstall the app after changing scopes.

Slash-command requests are acknowledged immediately, then answered privately to the invoking user. Reminder messages are sent in a one-to-one DM opened through Slack's Conversations API.

## Credential safety

- `.env` is ignored by Git; never commit it or paste tokens into source files.
- `.env.example` contains placeholders only and is safe to share.
- If a token is ever exposed, revoke or rotate it in Slack immediately and replace the local value.
- The app logs user IDs and API error names, but never logs token values.

## Tests

Run the standard-library tests with:

```powershell
py -m unittest discover -s tests -v
```
