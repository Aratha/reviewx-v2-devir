"""Create or reset the application-level super administrator idempotently.

application-foundation/PRDs/001-directory-login Requirement 14: the command shares its creation
path with the backend start (app.services.super_admin_service). It reads the password only from
its prompt or, with --password-stdin, from one line of standard input; the deployment's start-up
password (DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD) is never used for a reset.
"""

import argparse
import asyncio
import getpass
import sys

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.super_admin_service import SuperAdminResult, ensure_super_admin


def _password_from_operator(use_stdin: bool) -> str:
    if use_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise ValueError("password input was empty")
        return password
    first = getpass.getpass("Super-admin password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


async def _run(args: argparse.Namespace) -> SuperAdminResult:
    settings = get_settings()
    password = _password_from_operator(args.password_stdin)
    async with async_session_factory() as session:
        return await ensure_super_admin(
            session,
            email=args.email or settings.bootstrap_super_admin_email,
            username=args.username or settings.bootstrap_super_admin_username,
            password=password,
            tenant_code=args.tenant_code,
            tenant_name=args.tenant_name,
            upn_suffix=settings.directory_upn_suffix,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset the application super admin")
    parser.add_argument("--email")
    parser.add_argument("--username")
    parser.add_argument("--tenant-code", default="platform")
    parser.add_argument("--tenant-name", default="Platform")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input instead of prompting",
    )
    result = asyncio.run(_run(parser.parse_args()))
    action = "created" if result.created else "updated"
    print(
        f"super admin {action}: user={result.user_public_id} " f"tenant={result.tenant_public_id}"
    )


if __name__ == "__main__":
    main()
