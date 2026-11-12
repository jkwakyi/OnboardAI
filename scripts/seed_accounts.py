"""Create or reset the two synthetic development accounts (ON-36).

    python scripts/seed_accounts.py

One Employee and one HR administrator, so the team can sign in to both
halves of the application and a grader can see the role difference without
anybody handing round real credentials. The addresses end in `.example`,
which RFC 2606 reserves and which therefore cannot reach a real mailbox.

Safe to run again. It resets the name, role and password of an account that
is already there rather than failing, which is what you want after dropping
the database or forgetting the development password.

The passwords come from the environment - SEED_EMPLOYEE_PASSWORD and
SEED_HR_PASSWORD, documented in .env.example. Nothing here prints them, and
the script refuses to run at all when ONBOARDAI_ENV is production.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.auth import SeedRefused, seed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list",
        action="store_true",
        help="show which accounts would be seeded, and change nothing",
    )
    arguments = parser.parse_args(argv)

    settings = get_settings()

    if arguments.list:
        # Imported here so --list still works when the passwords are the
        # only thing missing: it reports that, rather than a traceback.
        from app.services.auth import seed_accounts_from_settings

        try:
            for account in seed_accounts_from_settings(settings):
                print(f"{account.role:18} {account.email}  ({account.full_name})")
        except SeedRefused as refusal:
            print(f"Cannot seed: {refusal}", file=sys.stderr)
            return 1
        return 0

    try:
        with SessionLocal() as session:
            outcomes = seed(session, settings)
    except SeedRefused as refusal:
        print(f"Cannot seed: {refusal}", file=sys.stderr)
        return 1
    except SQLAlchemyError as error:
        print(
            f"The Main Database refused the write: {error.__class__.__name__}: {error}\n"
            "Is PostgreSQL running (docker compose up -d) and has the schema "
            "been applied (alembic upgrade head)?",
            file=sys.stderr,
        )
        return 2

    for outcome in outcomes:
        print(outcome.describe())
    print(
        f"\n{len(outcomes)} synthetic accounts ready. Their passwords are the ones "
        "in your .env; this script never prints them."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
