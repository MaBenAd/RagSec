import base64
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

from gateway.errors import ControlError

INJECTION = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|"
    r"(?:system|developer)\s*:|reveal\s+(?:the\s+)?(?:secret|password)|"
    r"ignore[rz]?\s+(?:les\s+)?instructions|تجاهل\s+التعليمات",
    re.I,
)
SENSITIVE = re.compile(
    r"RAGSEC[_-]CANARY[_-][A-Z0-9_-]+|"
    r"(?:api[_ -]?key|password|secret)\s*[:=]\s*\S+|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.I,
)


@dataclass(frozen=True)
class Inspection:
    original_hash: str
    normalized: str
    signals: tuple[str, ...]


def inspect_text(text: str, limit: int = 32768) -> Inspection:
    if not isinstance(text, str) or len(text) > limit or len(text.encode()) > limit * 4:
        raise ControlError("input_size")
    normalized = unicodedata.normalize("NFKC", text)
    invisible = any(unicodedata.category(c) == "Cf" for c in normalized)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Cf")
    for _ in range(2):
        decoded = unquote(normalized)
        def decode(match):
            try:
                return base64.b64decode(match[1], validate=True).decode("utf-8")
            except (ValueError, UnicodeError):
                return match[0]
        decoded = re.sub(r"base64:([A-Za-z0-9+/=]{4,4096})", decode, decoded)
        if len(decoded) > limit * 2:
            raise ControlError("normalization_size")
        if decoded == normalized:
            break
        normalized = decoded
    signals = []
    if invisible:
        signals.append("invisible_unicode")
    if INJECTION.search(normalized):
        signals.append("instruction_pattern")
    return Inspection(hashlib.sha256(text.encode()).hexdigest(), normalized, tuple(signals))


def disclosure_gate(text: str, limit: int = 32768) -> None:
    inspected = inspect_text(text, limit)
    if SENSITIVE.search(inspected.normalized):
        raise ControlError("sensitive_data")


def output_gate(text: str, limit: int = 8192) -> None:
    disclosure_gate(text, limit)
    # Markdown images can exfiltrate via a browser fetch. HTML remains inert in UI.
    if re.search(r"!\[|<\s*(?:img|script|iframe)|(?:javascript|data)\s*:", text, re.I):
        raise ControlError("unsafe_output")
