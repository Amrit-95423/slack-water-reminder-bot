from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from reminder_store import Reminder, ReminderStore, parse_interval


LOGGER = logging.getLogger(__name__)
HELP_TEXT = (
    "Usage: `/water set MINUTES` to start or change reminders, "
    "`/water status` to view your setting, or `/water off` to stop them. "
    f"Intervals must be between 5 and 1440 minutes."
)


def format_interval(interval_minutes: int) -> str:
    if interval_minutes % 60 == 0:
        hours = interval_minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{interval_minutes} minutes"


def format_status(reminder: Reminder | None) -> str:
    if reminder is None:
        return "You do not have an active water reminder. " + HELP_TEXT
    return (
        f"Your water reminder is set to every "
        f"{format_interval(reminder.interval_minutes)}."
    )


def create_app(store: ReminderStore, bot_token: str) -> App:
    app = App(token=bot_token)

    @app.command("/water")
    def handle_water_command(ack, respond, command):
        # Acknowledge first so Slack receives a response within its deadline.
        ack()
        user_id = command["user_id"]
        arguments = command.get("text", "").strip().split()
        action = arguments[0].lower() if arguments else "help"

        try:
            if action in {"help", ""}:
                message = HELP_TEXT
            elif action == "status":
                message = format_status(store.get(user_id))
            elif action == "off":
                was_enabled = store.disable(user_id)
                message = (
                    "Your water reminders are off."
                    if was_enabled
                    else "You did not have an active water reminder."
                )
            elif action == "set" and len(arguments) == 2:
                interval_minutes = parse_interval(arguments[1])
                reminder = store.set_interval(user_id, interval_minutes)
                message = (
                    f"Done — I’ll remind you every "
                    f"{format_interval(reminder.interval_minutes)}."
                )
            else:
                message = HELP_TEXT
        except (ValueError, OSError) as error:
            LOGGER.warning("Could not update reminder for %s: %s", user_id, error)
            message = str(error)

        respond(message, response_type="ephemeral")

    return app


def send_reminder(client, user_id: str) -> None:
    dm_response = client.conversations_open(users=user_id)
    dm_id = dm_response["channel"]["id"]
    client.chat_postMessage(
        channel=dm_id,
        text="💧 Time for some water! Take a quick sip and stay hydrated.",
    )


def run_reminder_loop(app: App, store: ReminderStore, stop_event: threading.Event) -> None:
    while not stop_event.wait(1):
        for user_id, reminder in store.claim_due():
            try:
                send_reminder(app.client, user_id)
                LOGGER.info("Sent water reminder to %s", user_id)
            except SlackApiError as error:
                error_code = error.response.get("error", "unknown_error")
                LOGGER.warning("Could not remind %s: %s", user_id, error_code)
            except Exception:
                LOGGER.exception("Unexpected error while reminding %s", user_id)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bot_token = required_env("SLACK_BOT_TOKEN")
    app_token = required_env("SLACK_APP_TOKEN")
    store_path = Path(os.getenv("REMINDER_STORE_PATH", "data/reminders.json"))
    store = ReminderStore(store_path)
    app = create_app(store, bot_token)
    stop_event = threading.Event()
    reminder_thread = threading.Thread(
        target=run_reminder_loop,
        args=(app, store, stop_event),
        name="water-reminders",
        daemon=True,
    )
    reminder_thread.start()

    try:
        SocketModeHandler(app, app_token).start()
    finally:
        stop_event.set()
        reminder_thread.join(timeout=2)


if __name__ == "__main__":
    main()
