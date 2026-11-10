"""Shared fixtures: a fake plugin context and a temporary home for files."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeState:
    """Stand-in for ctx.state (atomic JSON k/v in real Hermes)."""

    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = json.loads(json.dumps(value))


class FakeCtx:
    def __init__(self, base_url: str | None = None, timeout_seconds: int | None = None):
        self.settings = {"base_url": base_url, "timeout_seconds": timeout_seconds}
        self.state = FakeState()

    def get_config(self, key: str, default=None):
        value = self.settings.get(key)
        return default if value is None else value


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
