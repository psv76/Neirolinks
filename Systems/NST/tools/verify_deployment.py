#!/usr/bin/env python3
"""Offline verification of an NST deployment using only locally available Git objects."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from nst.deployment import validate_deployment, verify_offline
from nst.util import decode, safe_relative


def read_git(commit, path):
    safe_relative(path)
    return subprocess.check_output(["git", "-C", str(REPO_ROOT), "show", commit + ":" + path])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "deployments/ABF62SL.json"))
    args = parser.parse_args(argv)
    data = validate_deployment(decode(Path(args.manifest).read_bytes()))
    verify_offline(data, read_git)
    print("offline deployment verification: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
