from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60


@dataclass(frozen=True)
class Reminder:
    interval_minutes: int
    next_reminder_at: float


def parse_interval(value: str) -> int:
    """Parse and validate a user-provided interval in minutes."""
    try:
        interval_minutes = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Interval must be a whole number of minutes.") from error

    if not MIN_INTERVAL_MINUTES <= interval_minutes <= MAX_INTERVAL_MINUTES:
        raise ValueError(
            f"Interval must be between {MIN_INTERVAL_MINUTES} and "
            f"{MAX_INTERVAL_MINUTES} minutes."
        )

    return interval_minutes


class ReminderStore:
    """Thread-safe local persistence for per-user reminder settings."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = RLock()
        self._reminders = self._load()

    def get(self, user_id: str) -> Reminder | None:
        with self._lock:
            return self._reminders.get(user_id)

    def set_interval(
        self, user_id: str, interval_minutes: int, *, now: float | None = None
    ) -> Reminder:
        if not user_id:
            raise ValueError("A Slack user ID is required.")
        interval_minutes = parse_interval(str(interval_minutes))
        current_time = time.time() if now is None else now
        reminder = Reminder(
            interval_minutes=interval_minutes,
            next_reminder_at=current_time + interval_minutes * 60,
        )

        with self._lock:
            self._reminders[user_id] = reminder
            self._save()

        return reminder

    def disable(self, user_id: str) -> bool:
        with self._lock:
            if user_id not in self._reminders:
                return False
            del self._reminders[user_id]
            self._save()
            return True

    def claim_due(self, *, now: float | None = None) -> list[tuple[str, Reminder]]:
        """Return due reminders and advance them by one interval.

        Advancing before sending prevents duplicate reminders if a Slack API call
        takes longer than the scheduler tick. A failed send will be retried on the
        next interval and is logged by the caller.
        """
        current_time = time.time() if now is None else now
        due: list[tuple[str, Reminder]] = []

        with self._lock:
            for user_id, reminder in self._reminders.items():
                if reminder.next_reminder_at > current_time:
                    continue

                due.append((user_id, reminder))
                self._reminders[user_id] = Reminder(
                    interval_minutes=reminder.interval_minutes,
                    next_reminder_at=current_time + reminder.interval_minutes * 60,
                )

            if due:
                self._save()

        return due

    def _load(self) -> dict[str, Reminder]:
        if not self.path.exists():
            return {}

        with self.path.open("r", encoding="utf-8") as file:
            raw_data = json.load(file)

        if not isinstance(raw_data, dict):
            raise ValueError(f"Reminder store must contain a JSON object: {self.path}")

        reminders: dict[str, Reminder] = {}
        for user_id, raw_reminder in raw_data.items():
            if not isinstance(user_id, str) or not isinstance(raw_reminder, dict):
                raise ValueError(f"Invalid reminder entry in {self.path}")
            try:
                interval_minutes = parse_interval(str(raw_reminder["interval_minutes"]))
                next_reminder_at = float(raw_reminder["next_reminder_at"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid reminder entry for {user_id}") from error

            reminders[user_id] = Reminder(
                interval_minutes=interval_minutes,
                next_reminder_at=next_reminder_at,
            )

        return reminders

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            user_id: {
                "interval_minutes": reminder.interval_minutes,
                "next_reminder_at": reminder.next_reminder_at,
            }
            for user_id, reminder in self._reminders.items()
        }

        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, self.path)
