import json


LEGACY_MARKER_PREFIX = "[LEGACY_META]"


def build_legacy_meta_text(payload: dict) -> str:
    return f"{LEGACY_MARKER_PREFIX}{json.dumps(payload, ensure_ascii=False)}"


def extract_legacy_meta(text: str | None) -> dict:
    if not text:
        return {}
    marker_line = None
    for line in str(text).splitlines():
        if line.startswith(LEGACY_MARKER_PREFIX):
            marker_line = line[len(LEGACY_MARKER_PREFIX) :]
            break
    if not marker_line:
        return {}
    try:
        payload = json.loads(marker_line)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def upsert_legacy_meta(text: str | None, payload: dict) -> str:
    lines = []
    if text:
        for line in str(text).splitlines():
            if not line.startswith(LEGACY_MARKER_PREFIX):
                lines.append(line)
    lines.insert(0, build_legacy_meta_text(payload))
    return "\n".join(lines).strip()


def strip_legacy_meta(text: str | None) -> str:
    if not text:
        return ""
    lines = [
        line
        for line in str(text).splitlines()
        if not line.startswith(LEGACY_MARKER_PREFIX)
    ]
    return "\n".join(lines).strip()
