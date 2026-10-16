"""Cross-process coordination for the two writers of the shared spreadsheet.

* write_lock(): short exclusive lock (flock) held around a read-modify-write of
  the sheet, by the CLI sync and by the web server alike.
* cli_session(): marks a running CLI command so the web app can show a notice.
"""
import json
import os
import threading
import time
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # Windows: no cross-process lock, the in-process one still applies
    fcntl = None

from ..config import Config

LOCK_FILE = os.path.join(Config.DATA_DIR, "sheet.lock")
BUSY_FILE = os.path.join(Config.DATA_DIR, "cli_busy.json")

_thread_lock = threading.RLock()
_depth = 0
_fd = None


class SheetBusy(Exception):
    pass


@contextmanager
def write_lock(timeout=60.0):
    """Exclusive, re-entrant lock; raises SheetBusy if not obtained within `timeout` seconds."""
    global _depth, _fd
    if not _thread_lock.acquire(timeout=timeout):
        raise SheetBusy("another thread holds the sheet lock")
    try:
        if _depth == 0 and fcntl:
            os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
            fd = open(LOCK_FILE, "w")
            deadline = time.time() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.time() >= deadline:
                        fd.close()
                        raise SheetBusy("another process holds the sheet lock")
                    time.sleep(0.2)
            _fd = fd
        _depth += 1
        try:
            yield
        finally:
            _depth -= 1
            if _depth == 0 and _fd:
                fcntl.flock(_fd, fcntl.LOCK_UN)
                _fd.close()
                _fd = None
    finally:
        _thread_lock.release()


@contextmanager
def cli_session(command):
    """Flags that a CLI command (which may rewrite the sheet) is running."""
    os.makedirs(os.path.dirname(BUSY_FILE), exist_ok=True)
    with open(BUSY_FILE, "w") as f:
        json.dump({"pid": os.getpid(), "command": command, "since": time.time()}, f)
    try:
        yield
    finally:
        try:
            os.remove(BUSY_FILE)
        except OSError:
            pass


def busy_info():
    """{'command', 'since'} of a live CLI session, else None (stale markers are ignored)."""
    try:
        with open(BUSY_FILE) as f:
            info = json.load(f)
        os.kill(info["pid"], 0)
        return {"command": info.get("command", ""), "since": info.get("since", 0)}
    except (OSError, ValueError, KeyError):
        return None
