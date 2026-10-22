"""Small cache for expensive assembly of bundled, read-only resource indexes."""
from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable


class SourceCache:
    def __init__(self, ttl: float = 30):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._signature = None
        self._expires = 0.0
        self._value = None

    def get(self, paths: Iterable[Path], loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        signature = []
        for path in paths:
            try:
                stat = path.stat()
                signature.append((str(path.resolve()), stat.st_mtime_ns, stat.st_size))
            except OSError:
                signature.append((str(path.resolve()), None, None))
        with self._lock:
            if signature != self._signature or time.monotonic() >= self._expires:
                value = loader()
                self._value = value
                self._signature = signature
                self._expires = time.monotonic() + self.ttl
            # Callers annotate rows; never let one request mutate another's data.
            return copy.deepcopy(self._value)
