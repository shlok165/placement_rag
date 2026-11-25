"""Operational commands: `python -m app.cli <command>`."""

import argparse
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("app.cli")


def bootstrap() -> None:
    """Run once at start-up, after migrations."""
    if get_settings().seed_demo:
        logger.info("demo seed requested")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="seed demo data when SEED_DEMO=1")
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap()


if __name__ == "__main__":
    main()
