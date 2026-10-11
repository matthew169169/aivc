#!/usr/bin/env python3
"""Start the cloned Omics-GEM Studio UI and FastAPI backend together."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("OMICS_GEM_AUTH_ENABLED", "false")


def main() -> None:
    import uvicorn

    host = os.environ.get("OMICS_GEM_HOST") or ("0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    port = int(os.environ.get("OMICS_GEM_PORT", os.environ.get("PORT", "8765")))
    print(f"Omics-GEM Studio → http://{host}:{port}")
    uvicorn.run("api.browser_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
