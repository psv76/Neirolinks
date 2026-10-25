#!/bin/sh
# Single-command WB installer: use only published approved GitHub Releases.
set -eu
if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root on Wiren Board (e.g. wget ... | sudo bash)." >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required on Wiren Board." >&2
  exit 1
}
temp="$(mktemp -d /tmp/neirolinks-bootstrap.XXXXXXXX)"
trap 'rm -rf "$temp"' EXIT HUP INT TERM
url="https://raw.githubusercontent.com/psv76/Neirolinks/main/Systems/NST/tools-ui/tools/bootstrap_latest.py"
if command -v wget >/dev/null 2>&1; then
  wget -q -T 40 -O "$temp/bootstrap_latest.py" "$url" || {
    echo "Cannot download verified installer source from GitHub." >&2
    exit 1
  }
elif command -v curl >/dev/null 2>&1; then
  curl -fsSL --connect-timeout 15 --max-time 90 "$url" -o "$temp/bootstrap_latest.py" || {
    echo "Cannot download verified installer source from GitHub." >&2
    exit 1
  }
else
  echo "wget or curl is required." >&2
  exit 1
fi
test -s "$temp/bootstrap_latest.py" || {
  echo "Bootstrap source is empty." >&2
  exit 1
}
python3 "$temp/bootstrap_latest.py" "$@"
