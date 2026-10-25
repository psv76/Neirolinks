#!/usr/bin/env python3
"""Offline installer kit: published NST 2.5 + this approved Tools 1.0 Debian binary."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NST_SHA = "d778b5cf7acd2ab74d58646b28755b29707e6654a264b938b934d7d001af0942"


def make(nst, tools, tools_sha, target):
    nst = Path(nst)
    tools = Path(tools)
    assert nst.name == "nst_2.5_all.deb"
    assert tools.name == "neirolinks-tools_1.0_all.deb"
    assert hashlib.sha256(nst.read_bytes()).hexdigest() == NST_SHA, "NST approved 2.5 hash mismatch"
    assert hashlib.sha256(tools.read_bytes()).hexdigest() == tools_sha, "Tools Linux CI hash mismatch"
    checksums = (NST_SHA + "  " + nst.name + "\n" +
                 tools_sha + "  " + tools.name + "\n")
    parts = [
        (nst.name, nst.read_bytes(), 0o644),
        (tools.name, tools.read_bytes(), 0o644),
        ("SHA256SUMS", checksums.encode("ascii"), 0o644),
        ("install.sh", (ROOT/"packaging/install.sh").read_bytes().replace(b"\r\n",b"\n"), 0o755),
        ("README.md", (ROOT/"README.md").read_bytes().replace(b"\r\n",b"\n"), 0o644),
    ]
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw, mode in sorted(parts):
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 25, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (0o100000 | mode) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(target) as archive:
        for name, raw, _ in parts:
            assert archive.read(name) == raw
    print(target, hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--nst",required=True)
    p.add_argument("--tools",required=True)
    p.add_argument("--tools-sha",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    make(a.nst,a.tools,a.tools_sha,Path(a.output))
