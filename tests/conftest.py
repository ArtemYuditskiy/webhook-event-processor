import pytest

from webhook_processor import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "QUEUE_RETRY_BASE_DELAY": 0,
            "QUEUE_LOCK_TIMEOUT": 0,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def webhook_data():
    return {
        "event_id": "abc-123",
        "type": "payment_succeeded",
        "payload": {"amount": 500},
    }

