"""Daily call counter for the cost cap. Survives restarts when given a path."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Callable


class DailyUsage:
    def __init__(self, limit: int, path: Path | str | None = None, today: Callable[[], date] = date.today):
        self.limit, self.path, self._today = limit, Path(path) if path else None, today
        self._counts: dict[str, int] = {}
        if self.path and self.path.exists():
            self._counts = {k: int(v) for k, v in json.loads(self.path.read_text(encoding='utf-8')).items()}

    def used(self) -> int:
        return self._counts.get(self._today().isoformat(), 0)

    def remaining(self) -> int:
        return max(self.limit - self.used(), 0)

    def try_consume(self) -> bool:
        """Count one API attempt; False (and nothing counted) when today's cap is reached."""
        if self.remaining() <= 0:
            return False
        key = self._today().isoformat()
        # Keep only today: old days are not needed for a daily cap.
        self._counts = {key: self._counts.get(key, 0) + 1}
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._counts), encoding='utf-8')
        return True
