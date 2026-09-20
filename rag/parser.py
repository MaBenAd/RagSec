"""Parser client uses a Unix socket to a network-disabled, credential-free worker."""
import httpx
from gateway.errors import ControlError


class Parser:
    def __init__(self, socket="/ipc/parser.sock", limits=None):
        from gateway.config import Limits
        self.limits = limits or Limits()
        self.client = httpx.Client(transport=httpx.HTTPTransport(uds=socket), base_url="http://parser",
                                   timeout=self.limits.parser_seconds + 2, trust_env=False)

    def extract(self, data: bytes) -> str:
        if len(data) > self.limits.upload_bytes or not data.startswith(b"%PDF-"):
            raise ControlError("pdf_type_or_size")
        try:
            result = self.client.post("/parse", content=data)
            result.raise_for_status()
            if len(result.content) > self.limits.extracted_chars * 4 + 1024:
                raise ValueError()
            text = result.json()["text"]
            if not isinstance(text, str) or len(text) > self.limits.extracted_chars:
                raise ValueError()
            return text
        except Exception:
            raise ControlError("parser_failed", "unavailable") from None
