"""The write lock excludes other processes; cli_session is visible to busy_info."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services import sheet_lock


@pytest.fixture(autouse=True)
def tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sheet_lock, "LOCK_FILE", str(tmp_path / "sheet.lock"))
    monkeypatch.setattr(sheet_lock, "BUSY_FILE", str(tmp_path / "busy.json"))


def test_reentrant():
    with sheet_lock.write_lock(1):
        with sheet_lock.write_lock(1):
            pass


def test_other_process_blocked_then_released():
    probe = ("import sys; sys.path.insert(0, %r)\n"
             "from src.services import sheet_lock as l\n"
             "l.LOCK_FILE = %r\n"
             "try:\n"
             "    with l.write_lock(0.5): print('got')\n"
             "except l.SheetBusy: print('busy')\n") % (os.path.join(os.path.dirname(__file__), ".."), sheet_lock.LOCK_FILE)
    run = lambda: subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True).stdout.strip()
    with sheet_lock.write_lock(1):
        assert run() == "busy"
    assert run() == "got"


def test_cli_session_marker():
    assert sheet_lock.busy_info() is None
    with sheet_lock.cli_session("playlist sync"):
        assert sheet_lock.busy_info()["command"] == "playlist sync"
    assert sheet_lock.busy_info() is None
