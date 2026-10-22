"""Generate deployment credentials interactively on the cloud VM."""
from __future__ import annotations
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.auth import hash_password


def main():
    password = getpass.getpass("Workbench password: ")
    if len(password) < 12:
        raise SystemExit("Use a password with at least 12 characters.")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    # Single quoting protects the dollar signs in the hash from Compose interpolation.
    print("OMICS_GEM_PASSWORD_HASH='" + hash_password(password) + "'")
    print("OMICS_GEM_SESSION_SECRET='" + secrets.token_urlsafe(48) + "'")


if __name__ == "__main__":
    main()
