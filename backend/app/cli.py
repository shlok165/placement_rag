"""Operational commands: `python -m app.cli <command>`."""

import argparse
import getpass
import logging
import os
import sys

from sqlalchemy import select

from app import seed
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import User
from app.db.session import get_sessionmaker

logger = logging.getLogger("app.cli")


def bootstrap() -> None:
    """Run once at start-up, after migrations."""
    if not get_settings().seed_demo:
        return
    with get_sessionmaker()() as db:
        seed.seed_users(db)
        seed.seed_jobs(db)


def create_coordinator(email: str, name: str) -> int:
    password = getpass.getpass("Password (10+ characters): ")
    if len(password) < 10:
        print("Use at least 10 characters.", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        if db.scalar(select(User.id).where(User.email == email.lower())):
            print("An account with this email already exists.", file=sys.stderr)
            return 1
        seed.create_coordinator(db, email, name, password)
    print("Coordinator created.")
    return 0


def showcase() -> int:
    """Sample postings and a shared demo student for a public demo. Reads SHOWCASE_PASSWORD."""
    password = os.environ.get("SHOWCASE_PASSWORD", "")
    try:
        with get_sessionmaker()() as db:
            result = seed.seed_showcase(db, password)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    postings = result["postings"]
    print(f"Showcase ready: {postings} sample postings, demo student {seed.SHOWCASE_STUDENT}.")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="seed demo data when SEED_DEMO=1")
    creator = commands.add_parser("create-coordinator", help="create a coordinator account")
    creator.add_argument("email")
    creator.add_argument("name")
    commands.add_parser("showcase", help="sample postings and a demo student (SHOWCASE_PASSWORD)")
    args = parser.parse_args()
    if args.command == "create-coordinator":
        return create_coordinator(args.email, args.name)
    if args.command == "showcase":
        return showcase()
    bootstrap()
    return 0


if __name__ == "__main__":
    sys.exit(main())
