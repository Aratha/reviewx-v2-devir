"""The exported contract drops generated schema titles but never a field that is named ``title``."""

from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.scripts.export_openapi import canonicalize

pytestmark = pytest.mark.unit


class Note(BaseModel):
    title: str
    operationId: str = Field(description="A field whose name is also an OpenAPI keyword.")
    body: str = Field(title="Body text", examples=[{"title": "example title"}])


def _contract() -> dict[str, Any]:
    application = FastAPI(title="Contract", version="1")

    @application.get("/notes/{title}", response_model=Note, operation_id="read_note")
    async def read_note(title: str) -> Note:
        return Note(title=title, operationId="x", body="y")

    return canonicalize(application.openapi())


def test_a_model_field_named_title_stays_in_the_contract() -> None:
    note = _contract()["components"]["schemas"]["Note"]

    assert note["required"] == ["title", "operationId", "body"]
    assert note["properties"]["title"] == {"type": "string"}
    assert note["properties"]["operationId"] == {
        "description": "A field whose name is also an OpenAPI keyword.",
        "type": "string",
    }


def test_generated_titles_and_operation_ids_are_removed() -> None:
    contract = _contract()
    note = contract["components"]["schemas"]["Note"]
    operation = contract["paths"]["/notes/{title}"]["get"]

    assert "title" not in note
    assert "title" not in note["properties"]["body"]
    assert "operationId" not in operation
    assert operation["parameters"][0]["name"] == "title"
    assert "title" not in operation["parameters"][0]["schema"]
    assert contract["info"]["title"] == "Contract"


def test_example_values_are_kept_verbatim() -> None:
    body = _contract()["components"]["schemas"]["Note"]["properties"]["body"]

    assert body["examples"] == [{"title": "example title"}]


def test_names_in_keyword_maps_are_data_not_keywords() -> None:
    contract = canonicalize(
        {
            "info": {"title": "Contract", "version": "1"},
            "components": {
                "schemas": {
                    "title": {
                        "title": "Generated",
                        "type": "object",
                        "properties": {"properties": {"title": "Nested", "type": "string"}},
                        "patternProperties": {"^title$": {"title": "Pattern"}},
                        "$defs": {"title": {"title": "Definition", "type": "integer"}},
                        "default": {"title": "a default value"},
                    }
                }
            },
        }
    )
    schema = contract["components"]["schemas"]["title"]

    assert schema == {
        "type": "object",
        "properties": {"properties": {"type": "string"}},
        "patternProperties": {"^title$": {}},
        "$defs": {"title": {"type": "integer"}},
        "default": {"title": "a default value"},
    }
