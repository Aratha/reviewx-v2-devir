"""Response text extraction for both request formats, ported from the previous application.

These helpers only read already-received JSON; they never log or keep the text.
"""

import json
from typing import Any


def error_field_message(body: object) -> str | None:
    """LM Studio may answer 200 with {"error": ...}; such a body is a failed call."""

    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if err is None:
        return None
    if isinstance(err, str):
        return err.strip() or None
    if isinstance(err, dict):
        for key in ("message", "detail", "msg"):
            value = err.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(err).strip() or None


def _join_message_parts(parts: list[Any]) -> str | None:
    """LM Studio / Qwen: output: [{type, content}, ...]; message parts win over the others."""

    message_chunks: list[str] = []
    other_chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        target = (
            message_chunks
            if str(part.get("type") or "").strip().lower() == "message"
            else other_chunks
        )
        for key in ("content", "text"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                target.append(value)
                break
    chunks = message_chunks or other_chunks
    if not chunks:
        return None
    return "\n".join(chunks).strip()


def extract_response_text(data: object) -> str:
    """The answer text from the JSON shapes the supported endpoints return."""

    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return str(data)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"]).strip()
            if first.get("text"):
                return str(first["text"]).strip()
    for key in ("output", "outputs", "messages"):
        parts = data.get(key)
        if isinstance(parts, list) and parts:
            joined = _join_message_parts(parts)
            if joined:
                return joined
    for key in ("message", "response", "output", "text", "content", "reply"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict) and value.get("content"):
            return str(value["content"]).strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        return extract_response_text(nested)
    return json.dumps(data, ensure_ascii=False)


def stream_delta(chunk: dict[str, Any]) -> str:
    """OpenAI-compatible stream: choices[0].delta.content (text or parts), else message.content."""

    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta") or {}
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return str(message["content"])
    return ""


def usage_tokens(body: object, key: str) -> int | None:
    """``usage.<key>`` when the endpoint reports it as an integer."""

    if not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if isinstance(usage, dict):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None
