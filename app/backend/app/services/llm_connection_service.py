"""LLM connection settings of this process (sql-review/PRDs/006-llm-connection Req. 1, 2, 4, 13).

Format, base URL, chat URL, model and key start from the typed settings. Locally a rule manager
may change them; the change lives only in this process (Decision 4) and a save is refused when
the resolved address is not a private-network address. Nonprod exposes only format and model.
The key never leaves the server; responses carry ``api_key_set``.
"""

import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import status

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.domain.llm import (
    LlmEndpoint,
    LlmEndpointInvalid,
    resolve_chat_url,
    validate_endpoint_url,
)
from app.domain.models.llm_call import LlmChatApi
from app.infrastructure.llm.network import (
    NetworkPolicyDenied,
    Resolver,
    resolve_private,
)
from app.schemas.llm.contracts import LlmConnectionUpdate, LlmConnectionView

_RESOLUTION_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class LlmConnectionConfig:
    chat_api: LlmChatApi
    base_url: str = ""
    chat_url: str = ""
    model: str = ""
    api_key: str | None = field(default=None, repr=False)

    @property
    def resolved_chat_url(self) -> str | None:
        return resolve_chat_url(self.chat_api, self.base_url, self.chat_url)

    def endpoint(self) -> LlmEndpoint | None:
        url = self.resolved_chat_url
        if url is None or not self.model:
            return None
        return LlmEndpoint(self.chat_api, url, self.model, self.api_key)


def initial_llm_connection(settings: Settings) -> LlmConnectionConfig:
    key = settings.llm_api_key
    return LlmConnectionConfig(
        chat_api=LlmChatApi(settings.llm_chat_api),
        base_url=settings.llm_base_url.strip(),
        chat_url=settings.llm_chat_url.strip(),
        model=settings.llm_model.strip(),
        api_key=key.get_secret_value() if key is not None else None,
    )


class LlmConnectionStore:
    def __init__(self, initial: LlmConnectionConfig) -> None:
        self._config = initial
        self._lock = threading.Lock()

    def current(self) -> LlmConnectionConfig:
        return self._config

    def endpoint(self) -> LlmEndpoint | None:
        return self._config.endpoint()

    def replace(self, config: LlmConnectionConfig) -> None:
        with self._lock:
            self._config = config


def _url_invalid() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "llm_url_invalid",
        "LLM adresi geçersiz: kullanıcı bilgisi veya parça içermeyen bir http(s) adresi girin.",
    )


def _policy_denied(message: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, "network_policy_denied", message)


class LlmConnectionService:
    def __init__(
        self, *, settings: Settings, store: LlmConnectionStore, resolver: Resolver
    ) -> None:
        self.settings = settings
        self.store = store
        self.resolver = resolver

    @property
    def editable(self) -> bool:
        return self.settings.runtime_environment == "local"

    def view(self) -> LlmConnectionView:
        config = self.store.current()
        if not self.editable:
            return LlmConnectionView(
                environment="nonprod",
                editable=False,
                chat_api=config.chat_api.value,
                model=config.model,
            )
        return LlmConnectionView(
            environment="local",
            editable=True,
            chat_api=config.chat_api.value,
            model=config.model,
            base_url=config.base_url,
            chat_url=config.chat_url,
            resolved_chat_url=config.resolved_chat_url,
            api_key_set=config.api_key is not None,
        )

    async def update(self, change: LlmConnectionUpdate) -> LlmConnectionView:
        if not self.editable:
            raise ApplicationError(status.HTTP_404_NOT_FOUND, "not_found", "Bulunamadı.")
        current = self.store.current()
        updated = LlmConnectionConfig(
            chat_api=LlmChatApi(change.chat_api) if change.chat_api else current.chat_api,
            base_url=(change.base_url if change.base_url is not None else current.base_url).strip(),
            chat_url=(change.chat_url if change.chat_url is not None else current.chat_url).strip(),
            model=(change.model if change.model is not None else current.model).strip(),
            api_key=(change.api_key or None) if change.api_key is not None else current.api_key,
        )
        await self._check(updated)
        self.store.replace(updated)
        return self.view()

    async def _check(self, config: LlmConnectionConfig) -> None:
        try:
            for url in (config.base_url, config.chat_url):
                if url:
                    validate_endpoint_url(url, allow_http=True)
            resolved = config.resolved_chat_url
            if resolved is not None:
                validate_endpoint_url(resolved, allow_http=True)
        except LlmEndpointInvalid:
            raise _url_invalid() from None
        if resolved is None:
            return
        parts = urlsplit(resolved)
        try:
            await resolve_private(
                self.resolver,
                parts.hostname or "",
                parts.port or (443 if parts.scheme == "https" else 80),
                timeout=_RESOLUTION_TIMEOUT_SECONDS,
            )
        except NetworkPolicyDenied:
            raise _policy_denied(
                "LLM adresi kurum içi ağ dışında bir adrese çözülüyor; kaydedilmedi."
            ) from None
        except Exception:  # noqa: BLE001 - unresolved or timed out: the policy cannot be met
            raise _policy_denied(
                "LLM adresi çözümlenemedi; kurum ağı denetimi yapılamadığı için kaydedilmedi."
            ) from None
