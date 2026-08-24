from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Proje kökünden veya backend klasöründen uvicorn çalışsa da .env bulunsun
BACKEND_ROOT = Path(__file__).resolve().parent
_ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mssql_connection_string: str = ""
    mssql_server: str = ""
    mssql_port: int = 1433
    mssql_user: str = ""
    mssql_password: str = ""
    mssql_trusted_connection: bool = False
    mssql_encrypt: bool = True
    mssql_trust_server_certificate: bool = True
    llm_base_url: str = "http://localhost:1234/v1"
    # openai: POST .../v1/chat/completions + messages[] | api_v1_chat: POST .../api/v1/chat + system_prompt + input
    llm_chat_api: str = "api_v1_chat"
    llm_chat_url: str = ""
    # Genel isim; Windows ortaminda LLM_MODEL baska araclarca set edilebilir ve .env'i ezer.
    llm_model: str = "openai/gpt-oss-120b"
    # Bu doluysa her zaman kullanilir (SQL_REVIEW_LLM_MODEL=.env) — model secimini garanti eder.
    sql_review_llm_model: str = ""
    llm_api_key: str = ""
    # httpx: True ise sistem HTTP(S)_PROXY kullanilir. Ağdaki LLM (LAN IP) için False önerilir — aksi halde
    # "All connection attempts failed" sık görülür. Kurumsal proxy üzerinden bulut API ise true yapin.
    llm_http_trust_env: bool = False
    # LLM HTTP isteklerinde User-Agent (Cortex/Forcepoint log ve DLP korelasyonu için sabit tanımlayıcı).
    llm_http_user_agent: str = "DWHCodeReview-Backend/1.0 (internal SQL review; httpx)"
    # Kurumsal güvenlik: varsayılan olarak LLM hedefi private/Tailscale ağında olmalı.
    llm_enforce_private_network: bool = True
    # İstisna hostname listesi (virgülle): private olmayan ancak izin verilen hedefler.
    llm_allow_public_hosts: str = ""
    # LLM günlüklerinde ham request/response gövdelerini sakla mı? (öneri: false)
    llm_log_full_payloads: bool = False
    # Yerel LLM (LM Studio) kuyrukta beklerken ReadTimeout olmaması için düşük tutun (örn. 4–8).
    sql_review_max_concurrent_rules: int = 6
    # httpx okuma zaman aşımı (saniye); uzun üretimler veya sıra beklemesi için yükseltin.
    llm_read_timeout_seconds: float = 900.0
    # ReadTimeout / ConnectTimeout sonrası ek deneme sayısı (geçici ağ/sunucu yükü için).
    llm_request_retries: int = 2
    # SQL bu karakter sayısını aşınca nesne iki parçada analiz edilir (bağlam taşması riskini azaltır).
    sql_review_two_part_threshold_chars: int = 45000
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    # Boş değilse /api uçları X-API-Key ile korunur.
    api_access_token: str = ""
    # Boş değilse yönetim uçları (rules/llm-config/llm-logs) X-Admin-Key ister.
    api_admin_token: str = ""
    # Review uçlarında basit hız limiti (IP başına pencere bazlı).
    api_rate_limit_enabled: bool = True
    api_rate_limit_window_seconds: int = 60
    api_rate_limit_review_max: int = 30


def get_settings() -> Settings:
    return Settings()


def resolved_llm_model(settings: Settings) -> str:
    """Oncelik: SQL_REVIEW_LLM_MODEL; yoksa LLM_MODEL (env + .env)."""
    s = (settings.sql_review_llm_model or "").strip()
    return s if s else settings.llm_model
