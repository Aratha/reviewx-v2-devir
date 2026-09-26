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


def _canonicalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if key == "operationId":
                continue
            if key == "title" and path != ("info",):
                continue
            normalized[key] = _canonicalize(value[key], (*path, key))
        return normalized
    if isinstance(value, list):
        return [_canonicalize(item, path) for item in value]
    return value


def export_openapi(output: Path) -> dict[str, Any]:
    raw_schema = create_application().openapi()
    settings = get_settings()
    schemes = raw_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["tenant"] = {
        "type": "apiKey",
        "in": "header",
        "name": settings.tenant_header,
    }
    me_operation = raw_schema["paths"][f"{settings.api_prefix}/auth/me"]["get"]
    me_operation["security"] = [{"HTTPBearer": [], "tenant": []}]
    schema = cast(dict[str, Any], _canonicalize(raw_schema))
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
