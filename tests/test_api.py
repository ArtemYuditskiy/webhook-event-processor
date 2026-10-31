from webhook_processor.db import get_db


def test_webhook_creates_event_and_task(app, client, webhook_data):
    response = client.post("/webhook", json=webhook_data)

    assert response.status_code == 201
    assert response.get_json() == {"event_id": "abc-123", "duplicate": False}

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        task = get_db().execute("SELECT status, attempts FROM queue_tasks").fetchone()
        assert dict(task) == {"status": "pending", "attempts": 0}


def test_duplicate_webhook_does_not_create_duplicate(app, client, webhook_data):
    assert client.post("/webhook", json=webhook_data).status_code == 201
    response = client.post("/webhook", json=webhook_data)

    assert response.status_code == 200
    assert response.get_json()["duplicate"] is True

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert get_db().execute("SELECT COUNT(*) FROM queue_tasks").fetchone()[0] == 1


def test_invalid_webhook_returns_clear_error(client):
    response = client.post(
        "/webhook",
        json={"event_id": "", "type": "payment_succeeded", "payload": {}},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Поле event_id должно быть непустой строкой"}


def test_stats_returns_counts(client, webhook_data):
    client.post("/webhook", json=webhook_data)
    client.post(
        "/webhook",
        json={"event_id": "user-1", "type": "user_registered", "payload": {}},
    )

    response = client.get("/stats")

    assert response.status_code == 200
    assert response.get_json() == {
        "events_by_type": {"payment_succeeded": 1, "user_registered": 1},
        "tasks_by_status": {"pending": 2, "success": 0, "failed": 0, "skipped": 0},
    }

