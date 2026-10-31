import time

from webhook_processor.db import get_db
from webhook_processor.queue import QueueProcessor


def test_successful_task_is_processed(app, client, webhook_data):
    client.post("/webhook", json=webhook_data)

    with app.app_context():
        assert QueueProcessor().process_next() is True
        task = get_db().execute("SELECT status, attempts FROM queue_tasks").fetchone()

    assert dict(task) == {"status": "success", "attempts": 1}


def test_task_fails_after_three_attempts(app, client, webhook_data):
    webhook_data["payload"]["simulate_failure"] = True
    client.post("/webhook", json=webhook_data)

    with app.app_context():
        processor = QueueProcessor()
        for _ in range(3):
            assert processor.process_next() is True

        task = get_db().execute(
            "SELECT status, attempts, last_error FROM queue_tasks"
        ).fetchone()

    assert task["status"] == "failed"
    assert task["attempts"] == 3
    assert "Сымитированная ошибка" in task["last_error"]


def test_stale_task_is_recovered_and_eventually_failed(app, client, webhook_data):
    client.post("/webhook", json=webhook_data)

    with app.app_context():
        connection = get_db()
        with connection:
            connection.execute(
                "UPDATE queue_tasks SET attempts = 3, locked_at = ?",
                (time.time() - 10,),
            )

        assert QueueProcessor().process_next() is False
        task = connection.execute("SELECT status, locked_at FROM queue_tasks").fetchone()

    assert task["status"] == "failed"
    assert task["locked_at"] is None

