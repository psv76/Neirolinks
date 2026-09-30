#!/usr/bin/env python3
"""Reproducible Debian binary package, stdlib only; no maintainer scripts."""
import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def archive(entries, epoch):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.GNU_FORMAT) as tar:
        directories = {str(parent) for name, _, _ in entries for parent in PurePosixPath(name).parents
                       if str(parent) != "."}
        for name in sorted(directories, key=lambda p: (p.count("/"), p)):
            info = tarfile.TarInfo("./" + name + "/")
            info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, epoch
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            tar.addfile(info)
        for name, data, mode in sorted(entries):
            info = tarfile.TarInfo("./" + name)
            info.size, info.mode, info.mtime = len(data), mode, epoch
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(out.getvalue(), mtime=epoch)


def build(output, epoch=0):
    control = [("control", (ROOT / "debian/control").read_bytes().replace(b"\r\n", b"\n"), 0o644)]
    data = [
            ("usr/bin/nst", (ROOT / "bin/nst").read_bytes().replace(b"\r\n", b"\n"), 0o755),
            ("usr/share/nst/default-config.json", b'{"object":"unconfigured","role":"unconfigured",'
             b'"hostname":"unconfigured","components":{}}\n', 0o644)]
    for path in sorted((ROOT / "nst").glob("*.py")):
        data.append(("usr/lib/nst/nst/" + path.name, path.read_bytes().replace(b"\r\n", b"\n"), 0o644))
    for path in sorted((ROOT / "examples").rglob("*.json")):
        data.append(("usr/share/nst/examples/" + path.relative_to(ROOT / "examples").as_posix(),
                     path.read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/controller-registry.json",
                 (ROOT / "generated/controller-registry.json").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/controller-profile.schema.json",
                 (ROOT / "controller-profile.schema.json").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/deployment.schema.json",
                 (ROOT / "deployment.schema.json").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/deployment/approved-components.json",
                 (ROOT / "deployment/approved-components.json").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    for path in sorted((ROOT / "deployments").glob("*.json")):
        data.append(("usr/share/nst/deployments/" + path.name,
                     path.read_bytes().replace(b"\r\n", b"\n"), 0o644))
    for path in sorted((ROOT / "diagnostics").glob("*.json")):
        data.append(("usr/share/nst/diagnostics/" + path.name,
                     path.read_bytes().replace(b"\r\n", b"\n"), 0o644))
    # Immutable baseline payload is runtime data. Preserve exact bytes (no LF
    # normalization); live 507 1.0 intentionally has no terminal LF.
    for path in sorted((ROOT / "releases").rglob("*.js")):
        data.append(("usr/share/nst/payload/NLI/" + path.relative_to(ROOT).as_posix(),
                     path.read_bytes(), 0o644))
    for path in sorted((ROOT / 'releases').glob('hhm-*.json')):
        data.append(('usr/share/nst/known/' + path.name,
                     path.read_bytes().replace(b'\r\n', b'\n'), 0o644))
    data.append(("usr/share/nst/manifest.schema.json", (ROOT / "manifest.schema.json").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    # Smoke/bootstrap instructions are needed even on WB with dpkg nodoc policy.
    data.append(("usr/share/nst/WB_SMOKE.md", (ROOT / "WB_SMOKE.md").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/PRESSURE_MAKEUP.md", (ROOT / "PRESSURE_MAKEUP.md").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/RECOVERY.md", (ROOT / "RECOVERY.md").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(("usr/share/nst/register_pressure_makeup.py",
                 (ROOT / "tools/register_pressure_makeup.py").read_bytes().replace(b"\r\n", b"\n"), 0o644))
    data.append(('usr/share/nst/RELEASES.md', (ROOT / 'RELEASES.md').read_bytes().replace(b'\r\n', b'\n'), 0o644))
    data.append(('usr/share/nst/DEPLOYMENT.md', (ROOT / 'DEPLOYMENT.md').read_bytes().replace(b'\r\n', b'\n'), 0o644))
    for name in ("README.md", "NST_MIGRATION.md", "SECURITY.md", "FIRMWARE.md", "TEST_RESULTS.md"):
        data.append(("usr/share/doc/nst/" + name, (ROOT / name).read_bytes().replace(b"\r\n", b"\n"), 0o644))
    content = bytearray(b"!<arch>\n")
    for name, value in [("debian-binary", b"2.0\n"), ("control.tar.gz", archive(control, epoch)),
                        ("data.tar.gz", archive(data, epoch))]:
        header = f"{name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{len(value):<10}`\n"
        content.extend(header.encode("ascii"))
        content.extend(value)
        if len(value) % 2:
            content.extend(b"\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content).hexdigest() + "  " + output.name + "\n", encoding="ascii")
    print(str(output))
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "dist/nst_2.0_all.deb")
    args = p.parse_args()
    build(args.output, int(os.environ.get("SOURCE_DATE_EPOCH", "0")))
