import os

from flask import Flask

from . import db
from .routes import api


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "events.sqlite3"),
        QUEUE_POLL_INTERVAL=1.0,
        QUEUE_RETRY_BASE_DELAY=2.0,
        QUEUE_LOCK_TIMEOUT=30.0,
        QUEUE_MAX_ATTEMPTS=3,
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    app.register_blueprint(api)

    with app.app_context():
        db.init_db()

    return app

