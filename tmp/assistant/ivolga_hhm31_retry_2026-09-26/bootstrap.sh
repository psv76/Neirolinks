#!/bin/sh
set -eu

DEST="${1:-/root/field_retry.py}"
ARCHIVE_URL="https://raw.githubusercontent.com/psv76/Neirolinks/a1e198a658296d1af94b6be1b65c591a9e0da418/tmp/assistant/ivolga_hhm31_retry_2026-09-26/field_retry.py.gz"
ARCHIVE_SHA256="bf5f873581ca7b7800e9b50580005e1e4a09a0585fabb3a91703c204de0e6827"
SOURCE_SHA256="23b4a74ab771bd5971736df250ae69ec81f692f9b7de07300ff6e4054270dc2c"

python3 - "$DEST" "$ARCHIVE_URL" "$ARCHIVE_SHA256" "$SOURCE_SHA256" <<'PY'
import gzip
import hashlib
from pathlib import Path
import sys
import urllib.request

dest = Path(sys.argv[1])
url, archive_expected, source_expected = sys.argv[2:5]
with urllib.request.urlopen(url, timeout=30) as response:
    archive = response.read(2 * 1024 * 1024)
if hashlib.sha256(archive).hexdigest() != archive_expected:
    raise SystemExit("field_retry.py.gz SHA256 mismatch")
source = gzip.decompress(archive)
if hashlib.sha256(source).hexdigest() != source_expected:
    raise SystemExit("field_retry.py SHA256 mismatch")
dest.write_bytes(source)
dest.chmod(0o700)
print("installed:", dest)
print("sha256:", source_expected)
PY

python3 "$DEST" selftest
