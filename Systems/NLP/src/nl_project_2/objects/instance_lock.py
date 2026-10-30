"""OS-owned lifetime lock for one NL Project SQLite file (Issue #187).

The one-byte lock is released by the operating system on process termination,
including kill or reboot. The persistent lock file is intentionally NOT deleted:
deleting a locked inode would allow a second process to open a different inode.
"""

from __future__ import annotations

import os
from pathlib import Path


class ApplicationAlreadyRunning(RuntimeError):
    """Another live NLP instance holds the database's operating-system lock."""


class DatabaseInstanceLock:
    def __init__(self, database_path: Path):
        database = Path(database_path).resolve()
        self.path = database.parent / f".{database.name}.instance.lock"
        self._fd: int | None = None

    def __enter__(self) -> DatabaseInstanceLock:
        self.acquire()
        return self

    def __exit__(self, _kind, _error, _traceback) -> None:
        self.release()

    def acquire(self) -> None:
        if self._fd is not None:
            raise RuntimeError("The application lock is already held")
        # The application requires this directory to be writable for SQLite.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            os.close(fd)
            raise ApplicationAlreadyRunning(
                f"База {self.path.name.removeprefix('.').removesuffix('.instance.lock')} "
                "уже открыта в другом экземпляре NL Project. "
                "Закройте вторую программу; не удаляйте файл блокировки."
            ) from exc
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
