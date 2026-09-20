"""Runs only inside the credential-free parser container; bounded child process."""
import io
import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    import pdfplumber
    raw = sys.stdin.buffer.read(2 * 1024**2 + 1)
    if len(raw) > 2 * 1024**2 or not raw.startswith(b"%PDF-"):
        raise ValueError("pdf_type_or_size")
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        if pdf.doc.encryption:
            raise ValueError("encrypted_pdf")
        parts, total = [], 0
        for index, page in enumerate(pdf.pages):
            if index >= 100:
                raise ValueError("pdf_page_limit")
            text = page.extract_text() or ""
            total += len(text)
            if total > 32768:
                raise ValueError("pdf_expansion")
            parts.append(text)
    sys.stdout.write(json.dumps({"text": "\n".join(parts)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
