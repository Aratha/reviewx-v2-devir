"""Create or reset a local test account with one application role (local environment only).

application-foundation/PRDs/001-directory-login Requirement 11 and Decision 9: developers try
both roles with local accounts while the directory is disabled; no fake directory server exists.
The command refuses to run when the directory is enabled or the environment is not local.
"""

import argparse
import asyncio
import getpass
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.session import async_session_factory
from app.domain.directory import InvalidDirectoryName, validate_local_account_name
from app.domain.models.role import APPLICATION_ROLES, SUPER_ADMIN_ROLE
from app.domain.models.tenant import PLATFORM_TENANT_CODE
from app.domain.models.user import AccountType, User
from app.infrastructure.repositories.user_repository import UserRepository


class LocalUserRefused(Exception):
    """The environment or the existing records do not allow the requested local account."""


@dataclass(frozen=True, slots=True)
class LocalUserResult:
    user_public_id: UUID
    role: str
    created: bool


async def ensure_local_user(
    session: AsyncSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    role_code: str,
    email: str | None = None,
    display_name: str | None = None,
) -> LocalUserResult:
    if settings.directory_enabled:
        raise LocalUserRefused("dizin girişi açıkken yerel test hesabı oluşturulamaz")
    if settings.runtime_environment != "local":
        raise LocalUserRefused("yerel test hesabı yalnız yerel ortamda oluşturulabilir")
    if role_code not in APPLICATION_ROLES:
        raise LocalUserRefused(f"rol {', '.join(APPLICATION_ROLES)} değerlerinden biri olmalı")
    try:
        name = validate_local_account_name(username, settings.directory_upn_suffix)
    except InvalidDirectoryName as exc:
        raise LocalUserRefused("kullanıcı adı yerel hesap kurallarına uymuyor") from exc
    address = (email or f"{name}@example.invalid").strip().casefold()
    if "@" not in address:
        raise LocalUserRefused("e-posta adresi geçersiz")
    password_hash = hash_password(password, context=(name, address.partition("@")[0]))

    repository = UserRepository(session)
    tenant = await repository.get_tenant_by_code(PLATFORM_TENANT_CODE)
    role = await repository.get_role(role_code)
    if tenant is None or role is None:
        raise LocalUserRefused("platform kiracısı veya roller yok; önce göçleri uygulayın")

    user = await repository.get_local_by_username(name)
    conflict = await repository.find_identity_conflict(
        email=address, username=name, excluding_user_id=user.user_id if user else None
    )
    if conflict is not None:
        raise LocalUserRefused("bu kullanıcı adı veya e-posta başka bir hesapta kullanılıyor")
    created = user is None
    if user is None:
        user = await repository.add_user(
            User(
                home_tenant_id=tenant.tenant_id,
                username=name,
                email=address,
                display_name=(display_name or name).strip()[:255],
                account_type=AccountType.LOCAL.value,
                password_hash=password_hash,
                is_active=True,
            )
        )
        user.created_by = user.user_id
    else:
        if SUPER_ADMIN_ROLE in await repository.role_codes(user):
            raise LocalUserRefused("süper yönetici hesabı bu komutla değiştirilemez")
        user.home_tenant_id = tenant.tenant_id
        user.email = address
        user.password_hash = password_hash
        user.is_active = True
        if display_name:
            user.display_name = display_name.strip()[:255]
    user.updated_by = user.user_id
    await repository.set_application_role(
        user, role, actor_user_id=user.user_id, now=datetime.now(UTC)
    )
    await session.commit()
    return LocalUserResult(user_public_id=UUID(user.public_id), role=role.code, created=created)


def _password_from_operator(use_stdin: bool) -> str:
    if use_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise LocalUserRefused("parola girişi boş")
        return password
    first = getpass.getpass("Parola: ")
    if first != getpass.getpass("Parola (tekrar): "):
        raise LocalUserRefused("parolalar eşleşmiyor")
    return first


async def _run(args: argparse.Namespace) -> LocalUserResult:
    settings = get_settings()
    password = _password_from_operator(args.password_stdin)
    async with async_session_factory() as session:
        return await ensure_local_user(
            session,
            settings,
            username=args.username,
            password=password,
            role_code=args.role,
            email=args.email,
            display_name=args.display_name,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Yerel test hesabı oluştur veya parolasını yenile")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=APPLICATION_ROLES)
    parser.add_argument("--email")
    parser.add_argument("--display-name")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="parolayı istem yerine standart girdiden tek satır olarak oku",
    )
    try:
        result = asyncio.run(_run(parser.parse_args()))
    except (LocalUserRefused, ValueError) as exc:
        print(f"yerel test hesabı oluşturulmadı: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    action = "oluşturuldu" if result.created else "güncellendi"
    print(f"yerel test hesabı {action}: user={result.user_public_id} rol={result.role}")


if __name__ == "__main__":
    main()
