"""Shared helpers of the review run integration tests (sql-review 003, 004, 005)."""

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select

from app.db.session import async_session_factory
from app.domain.models.review import (
    ReviewFinding,
    ReviewRuleResult,
    ReviewRun,
    ReviewRunObject,
)
from app.domain.models.user import User
from app.main import app
from tests.integration.conftest import CLIENT_ADDRESS, ReviewEnv, RoleSession


async def runs_of(owner_public_id: str) -> list[ReviewRun]:
    async with async_session_factory() as session:
        return list(
            await session.scalars(
                select(ReviewRun)
                .join(User, User.user_id == ReviewRun.owner_user_id)
                .where(User.public_id == owner_public_id)
                .order_by(ReviewRun.review_run_id)
            )
        )


async def run_of(public_id: str) -> ReviewRun:
    async with async_session_factory() as session:
        run = await session.scalar(select(ReviewRun).where(ReviewRun.public_id == public_id))
        assert run is not None
        return run


async def objects_of(run: ReviewRun) -> list[ReviewRunObject]:
    async with async_session_factory() as session:
        return list(
            await session.scalars(
                select(ReviewRunObject)
                .where(ReviewRunObject.review_run_id == run.review_run_id)
                .order_by(ReviewRunObject.position)
            )
        )


async def result_counts(run: ReviewRun) -> tuple[int, int]:
    async with async_session_factory() as session:
        results = await session.scalar(
            select(func.count())
            .select_from(ReviewRuleResult)
            .join(
                ReviewRunObject,
                ReviewRunObject.review_run_object_id == ReviewRuleResult.review_run_object_id,
            )
            .where(ReviewRunObject.review_run_id == run.review_run_id)
        )
        findings = await session.scalar(
            select(func.count())
            .select_from(ReviewFinding)
            .join(
                ReviewRuleResult,
                ReviewRuleResult.review_rule_result_id == ReviewFinding.review_rule_result_id,
            )
            .join(
                ReviewRunObject,
                ReviewRunObject.review_run_object_id == ReviewRuleResult.review_run_object_id,
            )
            .where(ReviewRunObject.review_run_id == run.review_run_id)
        )
    return int(results or 0), int(findings or 0)


async def stream_until(
    env: ReviewEnv,
    session: RoleSession,
    path: str,
    body: dict[str, Any],
    stop: Callable[[dict[str, Any]], bool],
    *,
    pause: asyncio.Event | None = None,
    timeout: float = 10,
) -> tuple[list[dict[str, Any]], float]:
    """Drive the ASGI app directly and drop the connection once ``stop`` sees its event.

    With ``pause`` the client stops reading after the first event until the event is set, the
    way a slow browser connection holds the stream back.
    """

    payload = json.dumps(body).encode("utf-8")
    headers = [(name.lower().encode(), value.encode()) for name, value in session.headers.items()]
    headers += [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode()),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"{env.prefix}{path}",
        "raw_path": f"{env.prefix}{path}".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": (CLIENT_ADDRESS, 50000),
        "server": ("test", 80),
    }
    disconnected = asyncio.Event()
    dropped_at = [0.0]
    sent = False
    events: list[dict[str, Any]] = []
    buffer = ""

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal buffer
        if message["type"] != "http.response.body":
            return
        if pause is not None and events:
            await pause.wait()
        buffer += message.get("body", b"").decode("utf-8")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            if block.startswith("data: "):
                event = json.loads(block[len("data: ") :])
                events.append(event)
                if stop(event) and not disconnected.is_set():
                    dropped_at[0] = time.monotonic()
                    disconnected.set()

    await asyncio.wait_for(app(scope, receive, send), timeout)
    return events, dropped_at[0]
