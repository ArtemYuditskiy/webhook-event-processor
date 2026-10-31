import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from flask import current_app

from .db import get_db


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    event_id: str
    type: str
    payload: dict


class SkipEvent(Exception):
    pass


def handle_payment_succeeded(event: Event) -> None:
    if event.payload.get("simulate_failure"):
        raise RuntimeError("Сымитированная ошибка обработки платежа")
    logger.info("Платёж обработан: %s", event.event_id)


def handle_user_registered(event: Event) -> None:
    if event.payload.get("simulate_failure"):
        raise RuntimeError("Сымитированная ошибка обработки пользователя")
    logger.info("Регистрация обработана: %s", event.event_id)


HANDLERS: dict[str, Callable[[Event], None]] = {
    "payment_succeeded": handle_payment_succeeded,
    "user_registered": handle_user_registered,
}


def handle_event(event: Event) -> None:
    handler = HANDLERS.get(event.type)
    if handler is None:
        raise SkipEvent(f"Нет обработчика для типа {event.type}")
    handler(event)


class QueueProcessor:
    def __init__(self, handler: Callable[[Event], None] = handle_event) -> None:
        self.handler = handler

    def _claim_task(self):
        connection = get_db()
        now = time.time()
        stale_before = now - current_app.config["QUEUE_LOCK_TIMEOUT"]
        max_attempts = current_app.config["QUEUE_MAX_ATTEMPTS"]

        # BEGIN IMMEDIATE не позволяет двум воркерам одновременно забрать одну задачу.
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                UPDATE queue_tasks
                SET status = 'failed', locked_at = NULL,
                    last_error = COALESCE(last_error, 'Исчерпано количество попыток'),
                    updated_at = ?
                WHERE status = 'pending' AND attempts >= ?
                  AND (locked_at IS NULL OR locked_at <= ?)
                """,
                (now, max_attempts, stale_before),
            )
            task = connection.execute(
                """
                SELECT q.id, q.attempts, e.event_id, e.type, e.payload
                FROM queue_tasks AS q
                JOIN events AS e ON e.id = q.event_id
                WHERE q.status = 'pending'
                  AND q.attempts < ?
                  AND q.next_attempt_at <= ?
                  AND (q.locked_at IS NULL OR q.locked_at <= ?)
                ORDER BY q.id
                LIMIT 1
                """,
                (max_attempts, now, stale_before),
            ).fetchone()

            if task is not None:
                connection.execute(
                    """
                    UPDATE queue_tasks
                    SET attempts = attempts + 1, locked_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, task["id"]),
                )
            connection.commit()
            return task
        except Exception:
            connection.rollback()
            raise

    def _finish(self, task_id: int, status: str, error: str | None = None) -> None:
        connection = get_db()
        now = time.time()
        with connection:
            connection.execute(
                """
                UPDATE queue_tasks
                SET status = ?, locked_at = NULL, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error, now, task_id),
            )

    def _retry_or_fail(self, task_id: int, previous_attempts: int, error: Exception) -> None:
        connection = get_db()
        attempts = previous_attempts + 1
        max_attempts = current_app.config["QUEUE_MAX_ATTEMPTS"]
        now = time.time()

        if attempts >= max_attempts:
            self._finish(task_id, "failed", str(error))
            return

        delay = current_app.config["QUEUE_RETRY_BASE_DELAY"] * (2 ** (attempts - 1))
        with connection:
            connection.execute(
                """
                UPDATE queue_tasks
                SET locked_at = NULL, next_attempt_at = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (now + delay, str(error), now, task_id),
            )

    def process_next(self) -> bool:
        task = self._claim_task()
        if task is None:
            return False

        try:
            event = Event(
                event_id=task["event_id"],
                type=task["type"],
                payload=json.loads(task["payload"]),
            )
            self.handler(event)
        except SkipEvent as error:
            self._finish(task["id"], "skipped", str(error))
        except Exception as error:
            logger.exception("Ошибка обработки события %s", task["event_id"])
            self._retry_or_fail(task["id"], task["attempts"], error)
        else:
            self._finish(task["id"], "success")
        return True

    def run(self) -> None:
        interval = current_app.config["QUEUE_POLL_INTERVAL"]
        logger.info("Воркер запущен")
        try:
            while True:
                if not self.process_next():
                    time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Воркер остановлен")
