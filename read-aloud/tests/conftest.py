import pytest

import core


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Tests must never touch the real state folder (temp text files, worker.pid)."""
    monkeypatch.setattr(core, "STATE_DIR", tmp_path / "state")
