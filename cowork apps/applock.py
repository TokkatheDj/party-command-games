"""Cross-process advisory lock for .app_data.json read-modify-write cycles.

serve_apps.py (a multi-threaded HTTP server) and daily_check.py (a scheduled
job) are separate OS processes. serve_apps.py serializes its own threads with
an in-process threading.Lock, but that lock is invisible to daily_check.py --
so a concurrent load -> mutate -> save in each process can silently lose the
other's update (and, since both write the same .app_data.tmp before os.replace,
could even collide on the temp file). Both processes wrap every read-modify-
write in `with data_lock():` so exactly one is ever inside a cycle at a time.

Stdlib only (msvcrt on Windows, fcntl on POSIX) to keep the project dependency
free. Best-effort: if the lock can't be taken within `timeout`, the cycle
proceeds anyway rather than hanging the server -- hold times are milliseconds
(the slow `claude` call in daily_check runs OUTSIDE the lock), so real
contention is rare, and a once-in-a-blue-moon lost update beats a wedged HTTP
request. The context manager yields whether the lock was actually acquired.
"""
import os
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_FILE = Path(__file__).parent / ".app_data.lock"

try:
    import msvcrt

    def _try_acquire(fh):
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _release(fh):
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

except ImportError:  # POSIX
    import fcntl

    def _try_acquire(fh):
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fh):
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def data_lock(timeout=10.0, poll=0.05):
    fh = open(LOCK_FILE, "a+")
    try:
        # A one-byte region has to exist to lock byte 0 deterministically.
        if os.fstat(fh.fileno()).st_size == 0:
            try:
                fh.write("\0")
                fh.flush()
            except OSError:
                pass
        deadline = time.time() + timeout
        acquired = False
        while True:
            if _try_acquire(fh):
                acquired = True
                break
            if time.time() >= deadline:
                break  # best-effort: proceed rather than hang the request
            time.sleep(poll)
        try:
            yield acquired
        finally:
            if acquired:
                _release(fh)
    finally:
        fh.close()
