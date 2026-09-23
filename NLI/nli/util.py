"""Small durable filesystem primitives, shared by all components."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile


class Error(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Error(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda x: require(False, "Nonfinite JSON: " + x))
    except (ValueError, UnicodeError) as exc:
        raise Error("Invalid JSON: " + str(exc)) from exc


def read_json(path):
    return decode(Path(path).read_bytes())


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
            "Unsafe path")
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in value.split("/")),
            "Path traversal: " + value)
    return p


def beneath(root, relative):
    relative = safe_relative(relative)
    root = Path(root).absolute()
    require(not root.is_symlink(), "Symlink root: " + str(root))
    p = root
    for part in relative.parts:
        p = p / part
        require(not p.is_symlink() and not getattr(p, "is_junction", lambda: False)(),
                "Symlink/junction rejected: " + str(p))
    require(p.resolve().is_relative_to(root.resolve()), "Path escapes root")
    return p


def sync_dir(path):
    if os.name == "posix":
        fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic(path, data, mode=0o600, owner=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".nli-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode) if os.name == "posix" else None
            if owner is not None and os.name == "posix":
                os.fchown(stream.fileno(), *owner)
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, data):
    atomic(path, (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())


class Lock:
    """Kernel lock, released on process death. Lock file is never unlinked."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.name == "posix":
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # Windows development sandbox only
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.file.close()
            raise Error("NLI_BUSY: another mutation is in progress") from exc
        return self

    def __exit__(self, *args):
        self.file.close()
