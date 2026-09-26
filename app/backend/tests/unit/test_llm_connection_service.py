"""Local LLM connection settings: in-process changes, URL rules and the network check on save.

sql-review/PRDs/006-llm-connection Requirement 1, 2, 4 and 13 (Acceptance 1).
"""

import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.domain.models.llm_call import LlmChatApi
from app.schemas.llm.contracts import LlmConnectionUpdate
from app.services.llm_connection_service import (
    LlmConnectionConfig,
    LlmConnectionService,
    LlmConnectionStore,
    initial_llm_connection,
)

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
KEY = f"anahtar-{uuid4().hex}"
STORED = LlmConnectionConfig(
    chat_api=LlmChatApi.OPENAI,
    base_url="https://llm.corp.example.test/inference/m/v1",
    model="/data/models--Test",
    api_key=KEY,
)


class Resolver:
    def __init__(self, answers: dict[str, list[str]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.calls.append((host, port))
        if host not in self.answers:
            raise OSError("unknown host")
        return self.answers[host]


def _service(
    environment: str = "development", resolver: Resolver | None = None
) -> LlmConnectionService:
    return LlmConnectionService(
        settings=Settings(_env_file=None, environment=environment),
        store=LlmConnectionStore(STORED),
        resolver=resolver or Resolver({"llm.corp.example.test": ["10.14.3.99"]}),
    )


def test_initial_values_come_from_the_typed_settings() -> None:
    config = initial_llm_connection(
        Settings(
            _env_file=None,
            llm_chat_api="openai",
            llm_base_url=" https://h/v1 ",
            llm_model=" m ",
            llm_api_key="k",
        )
    )
    assert (config.base_url, config.model, config.api_key) == ("https://h/v1", "m", "k")
    endpoint = config.endpoint()
    assert endpoint is not None and endpoint.chat_url == "https://h/v1/chat/completions"
    assert initial_llm_connection(Settings(_env_file=None)).endpoint() is None


def test_views_never_carry_the_key_and_nonprod_shows_only_format_and_model() -> None:
    local = _service().view().model_dump(exclude_none=True)
    assert local == {
        "environment": "local",
        "editable": True,
        "chat_api": "openai",
        "model": "/data/models--Test",
        "base_url": STORED.base_url,
        "chat_url": "",
        "resolved_chat_url": f"{STORED.base_url}/chat/completions",
        "api_key_set": True,
    }
    assert _service("staging").view().model_dump(exclude_none=True) == {
        "environment": "nonprod",
        "editable": False,
        "chat_api": "openai",
        "model": "/data/models--Test",
    }
    assert KEY not in repr(local)


async def test_update_changes_only_this_process_and_handles_the_key() -> None:
    resolver = Resolver({"127.0.0.1": ["127.0.0.1"], "lmstudio.lan": ["192.168.1.20"]})
    service = _service(resolver=resolver)
    before_files = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in BACKEND.glob(".env*")
    }
    before_environment = dict(os.environ)

    view = await service.update(
        LlmConnectionUpdate(
            chat_api="api_v1_chat", base_url="http://lmstudio.lan:1234/v1", model=" qwen "
        )
    )
    assert view.resolved_chat_url == "http://lmstudio.lan:1234/api/v1/chat"
    assert view.model == "qwen" and view.api_key_set is True
    assert resolver.calls == [("lmstudio.lan", 1234)]
    removed = await service.update(LlmConnectionUpdate(api_key=""))
    assert removed.api_key_set is False
    endpoint = service.store.endpoint()
    assert endpoint is not None and endpoint.api_key is None and endpoint.model == "qwen"
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in BACKEND.glob(".env*")
    } == before_files
    assert dict(os.environ) == before_environment


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "https://user:secret@llm.corp.example.test/v1"},
        {"chat_url": "https://llm.corp.example.test/v1#x"},
        {"base_url": "file:///etc/passwd"},
        {"chat_url": "llm.corp.example.test/v1"},
    ],
)
async def test_unsafe_urls_are_rejected_and_nothing_changes(change: dict[str, Any]) -> None:
    service = _service()
    with pytest.raises(ApplicationError) as raised:
        await service.update(LlmConnectionUpdate(**change))
    assert (raised.value.status_code, raised.value.code) == (422, "llm_url_invalid")
    assert "secret" not in raised.value.message
    assert service.store.current() == STORED


@pytest.mark.parametrize(
    ("answers", "url"),
    [
        ({"public.example.com": ["93.184.216.34"]}, "https://public.example.com/v1"),
        ({"mixed.example.com": ["10.0.0.1", "8.8.8.8"]}, "https://mixed.example.com/v1"),
        ({}, "https://unknown.example.test/v1"),
        ({}, "https://8.8.8.8/v1"),
    ],
)
async def test_addresses_outside_the_private_network_are_not_saved(
    answers: dict[str, list[str]], url: str
) -> None:
    service = _service(resolver=Resolver(answers))
    with pytest.raises(ApplicationError) as raised:
        await service.update(LlmConnectionUpdate(base_url=url))
    assert (raised.value.status_code, raised.value.code) == (422, "network_policy_denied")
    assert service.store.current() == STORED


async def test_nonprod_refuses_changes() -> None:
    with pytest.raises(ApplicationError) as raised:
        await _service("staging").update(LlmConnectionUpdate(model="x"))
    assert raised.value.status_code == 404
