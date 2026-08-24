from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DbObjectRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(serialization_alias="schema")
    object_name: str = Field(serialization_alias="name")
    object_type: str = Field(serialization_alias="type")
    type_code: str
    created_at: datetime | None = Field(
        default=None,
        description="sys.objects.create_date",
    )
    last_modified: datetime | None = None


class ObjectSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(..., alias="schema")
    object_name: str = Field(..., alias="name")
    type_code: str = Field(..., alias="object_type")
    database: str | None = Field(
        default=None,
        description="Catalog veritabanı; boşsa istekteki database kullanılır.",
    )


class ReviewRequest(BaseModel):
    database: str = Field(
        default="",
        description="Varsayılan catalog; seçimlerde database yoksa kullanılır.",
    )
    selections: list[ObjectSelection]

    @model_validator(mode="after")
    def _database_present(self) -> Self:
        if not self.selections:
            return self
        if (self.database or "").strip():
            return self
        for s in self.selections:
            if not (s.database or "").strip():
                raise ValueError(
                    "İstekte database boşken her seçimde database alanı zorunludur."
                )
        return self


class ScriptReviewRequest(BaseModel):
    """Veritabanından nesne çekilmeden, doğrudan SQL metni ile inceleme."""

    sql: str = Field(..., min_length=1, max_length=200_000)
    label: str | None = Field(
        None,
        max_length=200,
        description="Sonuçlarda gösterilecek kısa ad (isteğe bağlı).",
    )


class ObjectDefinitionRequest(BaseModel):
    database: str = Field(..., min_length=1)
    schema: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    object_type: str = Field(..., min_length=1)


class ObjectDefinitionResponse(BaseModel):
    sql: str | None = None


Severity = Literal["LOW", "MEDIUM", "HIGH"]


class ViolationItem(BaseModel):
    rule_id: str
    severity: str
    description: str
    line_reference: str = ""
    code_snippet: str = ""


class RuleCheckItem(BaseModel):
    """Yayınlanmış her kural için tek satırlık inceleme sonucu."""

    rule_id: str
    tier: str = ""  # critical | normal
    status: str  # PASS | FAIL | NOT_APPLICABLE | UNKNOWN
    severity: str = ""
    decision_basis: str = ""  # direct_evidence | not_applicable | "" (PASS/uygunsuzluk yok)
    description: str = ""
    line_reference: str = ""
    code_snippet: str = ""


class ObjectReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(..., alias="schema")
    object_name: str = Field(..., alias="name")
    object_type: str
    database: str = Field(
        default="",
        description="Nesnenin bağlandığı catalog veritabanı",
    )
    rule_checks: list[RuleCheckItem] = Field(default_factory=list)
    violations: list[ViolationItem] = Field(default_factory=list)
    source_sql: str | None = None
    error: str | None = None
    parse_warning: str | None = None


class ReviewResponse(BaseModel):
    results: list[ObjectReviewResult]


class LlmConfigResponse(BaseModel):
    """LLM ayarları (API anahtarı yalnızca ayarlı/ayarsız bilgisi)."""

    llm_chat_api: str
    llm_base_url: str
    llm_chat_url: str
    llm_model: str
    sql_review_llm_model: str
    llm_http_trust_env: bool
    llm_enforce_private_network: bool
    llm_allow_public_hosts: str
    llm_log_full_payloads: bool
    sql_review_max_concurrent_rules: int = Field(ge=1, le=512)
    api_key_set: bool


class LlmConfigUpdate(BaseModel):
    """Kısmi güncelleme; gönderilmeyen alanlar değişmez. llm_api_key: boş string = sil."""

    llm_chat_api: str | None = None
    llm_base_url: str | None = None
    llm_chat_url: str | None = None
    llm_model: str | None = None
    sql_review_llm_model: str | None = None
    llm_api_key: str | None = None
    llm_http_trust_env: bool | None = None
    llm_enforce_private_network: bool | None = None
    llm_allow_public_hosts: str | None = None
    llm_log_full_payloads: bool | None = None
    sql_review_max_concurrent_rules: int | None = Field(None, ge=1, le=512)


class SqlConfigResponse(BaseModel):
    """SQL Server bağlantı ayarları (şifre yalnızca ayarlı/ayarsız bilgisi)."""

    mssql_server: str
    mssql_port: int = Field(ge=1, le=65535)
    mssql_user: str
    mssql_trusted_connection: bool
    mssql_encrypt: bool
    mssql_trust_server_certificate: bool
    password_set: bool
    configured: bool


class SqlConfigUpdate(BaseModel):
    """Kısmi güncelleme; mssql_password boş string = kayıtlı şifreyi sil."""

    mssql_server: str | None = None
    mssql_port: int | None = Field(None, ge=1, le=65535)
    mssql_user: str | None = None
    mssql_password: str | None = None
    mssql_trusted_connection: bool | None = None
    mssql_encrypt: bool | None = None
    mssql_trust_server_certificate: bool | None = None


class SqlConfigTestRequest(BaseModel):
    """Kaydetmeden bağlantı testi; boş alanlar mevcut kayıtlı değerleri kullanır."""

    mssql_server: str | None = None
    mssql_port: int | None = Field(None, ge=1, le=65535)
    mssql_user: str | None = None
    mssql_password: str | None = None
    mssql_trusted_connection: bool | None = None
    mssql_encrypt: bool | None = None
    mssql_trust_server_certificate: bool | None = None


class SqlConfigTestResponse(BaseModel):
    ok: bool
    message: str
    databases: list[str] = Field(default_factory=list)
