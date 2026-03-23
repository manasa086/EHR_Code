import hashlib
import json
from typing import Any, Optional


class InMemoryCache:
    def __init__(self):
        self._store: dict = {}

    def _key(self, data: dict) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(self, data: dict) -> Optional[Any]:
        return self._store.get(self._key(data))

    def set(self, data: dict, result: Any) -> None:
        self._store[self._key(data)] = result

    def clear(self) -> None:
        self._store.clear()


# Single shared instance used across the app
cache = InMemoryCache()
