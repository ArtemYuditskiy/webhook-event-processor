import json
import sqlite3
import time

from flask import Blueprint, jsonify, request

from .db import get_db


api = Blueprint("api", __name__)


def validation_error(data: object) -> str | None:
    if not isinstance(data, dict):
        return "Тело запроса должно быть JSON-объектом"
    if not isinstance(data.get("event_id"), str) or not data["event_id"].strip():
        return "Поле event_id должно быть непустой строкой"
    if not isinstance(data.get("type"), str) or not data["type"].strip():
        return "Поле type должно быть непустой строкой"
    if not isinstance(data.get("payload"), dict):
        return "Поле payload должно быть JSON-объектом"
    return None


@api.post("/webhook")
def webhook():
    if not request.is_json:
        return jsonify(error="Ожидается Content-Type: application/json"), 415

    data = request.get_json(silent=True)
    error = validation_error(data)
    if error:
        return jsonify(error=error), 400

    connection = get_db()
    now = time.time()

    try:
        with connection:
            cursor = connection.execute(
                "INSERT INTO events (event_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    data["event_id"],
                    data["type"],
                    json.dumps(data["payload"], ensure_ascii=False),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO queue_tasks
                    (event_id, status, attempts, next_attempt_at, created_at, updated_at)
                VALUES (?, 'pending', 0, ?, ?, ?)
                """,
                (cursor.lastrowid, now, now, now),
            )
    except sqlite3.IntegrityError:
        existing = connection.execute(
            "SELECT id FROM events WHERE event_id = ?",
            (data["event_id"],),
        ).fetchone()
        if existing is not None:
            return jsonify(event_id=data["event_id"], duplicate=True), 200
        raise

    return jsonify(event_id=data["event_id"], duplicate=False), 201


@api.get("/stats")
def stats():
    connection = get_db()
    events = connection.execute(
        "SELECT type, COUNT(*) AS count FROM events GROUP BY type ORDER BY type"
    ).fetchall()
    tasks = connection.execute(
        "SELECT status, COUNT(*) AS count FROM queue_tasks GROUP BY status"
    ).fetchall()

    task_counts = {status: 0 for status in ("pending", "success", "failed", "skipped")}
    task_counts.update({row["status"]: row["count"] for row in tasks})

    return jsonify(
        events_by_type={row["type"]: row["count"] for row in events},
        tasks_by_status=task_counts,
    )

