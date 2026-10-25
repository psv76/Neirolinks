#!/usr/bin/env python3
"""Reproducible Debian package for the separately managed WB HomeUI companion."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile
import re

ROOT = Path(__file__).resolve().parents[1]


def pack(entries, epoch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as tf:
        directories = {str(parent) for path, _data, _mode in entries for parent in PurePosixPath(path).parents
                       if str(parent) != "."}
        for dirname in sorted(directories, key=lambda x: (x.count("/"), x)):
            entry = tarfile.TarInfo("./" + dirname + "/")
            entry.type = tarfile.DIRTYPE
            entry.mode, entry.mtime = 0o755, epoch
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            tf.addfile(entry)
        for name, data, mode in sorted(entries):
            entry = tarfile.TarInfo("./" + name)
            entry.size, entry.mode, entry.mtime = len(data), mode, epoch
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            tf.addfile(entry, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=epoch)


def build(destination, epoch=0):
    control = (ROOT/"packaging/control").read_bytes().replace(b"\r\n", b"\n")
    assert b"Package: neirolinks-tools\n" in control
    assert b"Version: 1.0\n" in control
    ctl = [("control", control, 0o644)]
    for name in ("preinst", "postinst", "prerm", "postrm"):
        ctl.append((name, (ROOT/"packaging"/name).read_bytes().replace(b"\r\n", b"\n"), 0o755))
    filenames = {
        "service/server.py": "usr/lib/neirolinks-tools/server.py",
        "service/executor.py": "usr/lib/neirolinks-tools/executor.py",
        "web/index.html": "usr/share/neirolinks-tools/web/index.html",
        "web/style.css": "usr/share/neirolinks-tools/web/style.css",
        "web/app.js": "usr/share/neirolinks-tools/web/app.js",
        "config/menu.json": "usr/share/wb-mqtt-homeui/custom-menu/neirolinks.json",
        "config/gate.json": "usr/share/wb-mqtt-homeui/gates.d/neirolinks-tools.json",
        "config/neirolinks-tools.service": "lib/systemd/system/neirolinks-tools.service",
        "config/sudoers": "etc/sudoers.d/neirolinks-tools",
        "README.md": "usr/share/doc/neirolinks-tools/README.md",
    }
    data = []
    for source, target in filenames.items():
        data.append((target, (ROOT/source).read_bytes().replace(b"\r\n", b"\n"),
                     0o440 if source == "config/sudoers" else 0o644))
    result = bytearray(b"!<arch>\n")
    for name, blob in (("debian-binary", b"2.0\n"), ("control.tar.gz", pack(ctl, epoch)),
                       ("data.tar.gz", pack(data, epoch))):
        header = f"{name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{len(blob):<10}`\n"
        result.extend(header.encode("ascii"))
        result.extend(blob)
        if len(blob) % 2:
            result.extend(b"\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(result)
    sha = hashlib.sha256(result).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        sha + "  " + destination.name + "\n", encoding="ascii")
    print(destination, sha)
    return destination


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=ROOT/"dist/neirolinks-tools_1.0_all.deb")
    a = p.parse_args()
    build(a.output)
