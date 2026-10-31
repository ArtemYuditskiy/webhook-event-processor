import logging

from webhook_processor import create_app
from webhook_processor.queue import QueueProcessor


def main() -> None:
    app = create_app()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    with app.app_context():
        QueueProcessor().run()


if __name__ == "__main__":
    main()

