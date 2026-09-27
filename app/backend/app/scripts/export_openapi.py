"""Export the application contract without starting a server or connecting to PostgreSQL."""

import argparse
import json
from pathlib import Path
from typing import Any, cast

from app.core.config import get_settings
from app.main import create_application


def default_output() -> Path:
    scaffold_root = Path(__file__).resolve().parents[4]
    return scaffold_root / "specs" / "openapi" / "app-api.yaml"


# Keys whose value maps names chosen by the application (fields, schemas, paths, media types, ...)
# to objects. A name such as ``title`` there is data, never the keyword of the same spelling.
NAME_MAP_KEYWORDS = frozenset(
    {
        "$defs",
        "callbacks",
        "content",
        "definitions",
        "dependentRequired",
        "dependentSchemas",
        "encoding",
        "headers",
        "links",
        "mapping",
        "parameters",
        "pathItems",
        "paths",
        "patternProperties",
        "properties",
        "requestBodies",
        "responses",
        "schemas",
        "scopes",
        "securitySchemes",
        "variables",
        "webhooks",
    }
)
# Keys whose value is an example or constant instance, copied exactly as the application wrote it.
LITERAL_KEYWORDS = frozenset({"const", "default", "enum", "example", "examples"})
# Generated keywords left out of the contract so it stays stable when code is renamed.
GENERATED_KEYWORDS = frozenset({"operationId", "title"})


def _canonical_object(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical_object(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key in sorted(value):
        if key in GENERATED_KEYWORDS:
            continue
        child = value[key]
        if key in LITERAL_KEYWORDS:
            normalized[key] = child
        elif key in NAME_MAP_KEYWORDS and isinstance(child, dict):
            normalized[key] = _canonical_names(child)
        elif key == "security" and isinstance(child, list):
            # Each security requirement maps scheme names to scopes.
            normalized[key] = [_canonical_names(item) for item in child]
        else:
            normalized[key] = _canonical_object(child)
    return normalized


def _canonical_names(value: dict[str, Any]) -> dict[str, Any]:
    return {name: _canonical_object(value[name]) for name in sorted(value)}


def canonicalize(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop generated ``title`` and ``operationId`` keywords, keeping the API title in ``info``.

    Only keywords are dropped: a field, schema, parameter or example named ``title`` stays.
    """

    normalized = cast(dict[str, Any], _canonical_object(schema))
    info = schema.get("info")
    if isinstance(info, dict) and "title" in info:
        normalized["info"]["title"] = info["title"]
    return normalized


def export_openapi(output: Path) -> dict[str, Any]:
    settings = get_settings()
    # The contract lists every route, including the settings write and test endpoints that only
    # the local environment registers, whatever environment runs the export.
    raw_schema = create_application(
        settings.model_copy(update={"environment": "development"})
    ).openapi()
    schemes = raw_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["tenant"] = {
        "type": "apiKey",
        "in": "header",
        "name": settings.tenant_header,
    }
    # Every bearer-protected operation also needs the active-tenant header.
    for operations in raw_schema["paths"].values():
        for operation in operations.values():
            if {"HTTPBearer": []} in operation.get("security", []):
                operation["security"] = [{"HTTPBearer": [], "tenant": []}]
    schema = canonicalize(raw_schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {str(key): value for key, value in schema.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI contract")
    parser.add_argument("--output", type=Path, default=default_output())
    args = parser.parse_args()
    schema = export_openapi(args.output)
    print(f"wrote {args.output} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
