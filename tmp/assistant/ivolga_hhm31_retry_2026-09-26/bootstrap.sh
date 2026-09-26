#!/bin/sh
set -eu

DEST="${1:-/root/field_retry.py}"
ARCHIVE_URL="https://raw.githubusercontent.com/psv76/Neirolinks/88de039875331418b22f1a55216c6cf031029385/tmp/assistant/ivolga_hhm31_retry_2026-09-26/field_retry.py.gz"
ARCHIVE_SHA256="2a8daab5ce0986cbde1cd6babbcccb80a32275f3212adbe541629a11301429f8"
SOURCE_SHA256="5196db7f63176054f37bedd3421afe7386c9a49ad98555a45033af3ae3a9d2c9"

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
