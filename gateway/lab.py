"""Generate local-only credentials without printing them or committing them."""
import argparse
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["configure"])
    args = parser.parse_args()
    path = Path(".env.protected")
    # Exclusive creation preserves any operator's existing credentials.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        for name in ["DB_PASSWORD", "JWT_KEY", "VECTOR_WRITE_KEY", "VECTOR_READ_KEY", "OPA_TOKEN",
                     "INGEST_TOKEN", "SIGNING_KEY", "DEMO_PASSWORD"]:
            stream.write(f"RAGSEC_{name}={secrets.token_urlsafe(36)}\n")
    print("Created .env.protected with mode 0600. This file is ignored by Git.")


if __name__ == "__main__":
    main()
