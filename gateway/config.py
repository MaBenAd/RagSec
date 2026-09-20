from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Limits:
    request_bytes: int = 65536
    upload_bytes: int = 2 * 1024 * 1024
    parser_seconds: int = 10
    parser_memory_mb: int = 256
    extracted_chars: int = 32768
    query_chars: int = 4096
    history_chars: int = 4096
    context_chars: int = 12000
    source_chars: int = 4000
    chunks: int = 5
    output_chars: int = 8192
    generation_tokens: int = 2048
    total_seconds: float = 20.0
    attempts: int = 2
    tool_steps: int = 1
    concurrency: int = 4
    actor_requests_per_minute: int = 10
    actor_tokens_per_minute: int = 500000
    cache_seconds: int = 60


POLICY_VERSION = "ragsec-1"
PROMPT_VERSION = "ragsec-prompt-1"


def signing_key() -> bytes:
    value = os.environ.get("RAGSEC_SIGNING_KEY", "")
    if len(value) < 32:
        raise RuntimeError("RAGSEC_SIGNING_KEY must contain at least 32 characters")
    return value.encode()
