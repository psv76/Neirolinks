#!/bin/sh
# Ivolga only. Installs reviewed files; never arms heating or runs commissioning.
set -eu
[ "$#" -eq 2 ] || { echo "Usage: $0 install OBJECT_DIR | rollback BACKUP_DIR" >&2; exit 2; }
python3 - "$@" <<'PY'
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

mode, source_arg = sys.argv[1:]
if mode not in ('install', 'rollback'):
    raise SystemExit('Expected install or rollback')
source = Path(source_arg).resolve()
names = ['501_tp_dom_manager.js', '502_gp_dom_manager.js', '620_thermostats.js']
live = Path('/etc/wb-rules')
source_files = source / 'Wirenboard/wb-rules' if mode == 'install' else source
manifest = source / 'tools/cold_slab_v2.sha256.json' if mode == 'install' else source / 'sha256.json'
expected = json.loads(manifest.read_text())
for name in names:
    data = (source_files / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected[name]:
        raise SystemExit('Checksum mismatch: ' + name)
    if not (live / name).is_file():
        raise SystemExit('Missing live file: ' + name)
    if name.startswith(('501', '502')):
        text = data.decode('utf-8')
        for marker in ("sc('outputs_enabled', false);", "sc('manual_commissioning_grant', false);"):
            if marker not in text:
                raise SystemExit('Restore file lacks startup disarm; manual review required: ' + name)
        if mode == 'install' and 'maxWarmupS: 3600' not in text:
            raise SystemExit('Not a reviewed v2 manager: ' + name)

lock = open('/run/lock/hm2-cold-slab-v2.lock', 'w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
subprocess.run(['systemctl', 'is-active', '--quiet', 'wb-rules'], check=True)
def get(device, control):
    return subprocess.check_output(['mosquitto_sub', '-C', '1', '-W', '2',
        '-t', '/devices/' + device + '/controls/' + control], timeout=4, text=True).strip()
def disarm():
    failures = []
    for device in ('hm2_501_tp_dom', 'hm2_502_gp_dom'):
        for control in ('enabled', 'outputs_enabled', 'local_permit',
                        'manual_commissioning_grant', 'response_commissioned'):
            try:
                subprocess.run(['mosquitto_pub', '-t', '/devices/' + device +
                    '/controls/' + control + '/on', '-m', '0'], check=True, timeout=4)
            except Exception as error:
                failures.append(str(error))
    if failures:
        raise RuntimeError('Disarm writes failed: ' + '; '.join(failures))
def verify_off():
    for device in ('hm2_501_tp_dom', 'hm2_502_gp_dom'):
        for control in ('enabled', 'outputs_enabled', 'local_permit',
                        'manual_commissioning_grant', 'response_commissioned', 'heat_demand'):
            if get(device, control) != '0':
                raise RuntimeError('Not OFF: ' + device + '/' + control)
    for device, control in [('A03', 'K1'), ('A03', 'K2'),
            ('A05', 'Channel 1 Switch'), ('A05', 'Channel 2 Switch'),
            ('A05', 'Channel 1 Dimming Level'), ('A05', 'Channel 2 Dimming Level')]:
        if float(get(device, control)) != 0:
            raise RuntimeError('Nonzero output: ' + device + '/' + control)

disarm()
time.sleep(5)
verify_off()  # Do not replace anything until actual MQTT zeros are observed.
backup_root = Path('/root/hm2/backups')
backup_root.mkdir(parents=True, exist_ok=True)
backup = Path(tempfile.mkdtemp(prefix='cold_slab_v2_' + time.strftime('%Y%m%d_%H%M%S') + '_', dir=backup_root))
for name in names:
    shutil.copy2(live / name, backup / name)
hashes = {name: hashlib.sha256((backup / name).read_bytes()).hexdigest() for name in names}
(backup / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
print('BACKUP_DIR=' + str(backup), flush=True)
print('Rollback: sh tools/hm2_install_cold_slab_v2.sh rollback ' + str(backup), flush=True)
try:
    for name in names:
        # Stage outside *.js and atomically replace on the same filesystem.
        fd, staged = tempfile.mkstemp(prefix='.hm2-v2-', suffix='.tmp', dir=live)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write((source_files / name).read_bytes())
                out.flush()
                os.fsync(out.fileno())
            shutil.copymode(live / name, staged)
            os.replace(staged, live / name)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
    time.sleep(8)  # wb-rules automatically reloads changed rule files only.
    disarm()
    time.sleep(3)
    verify_off()
    subprocess.run(['systemctl', 'is-active', '--quiet', 'wb-rules'], check=True)
except BaseException:
    # No automatic restoration/arming; keep the backup and stop for inspection.
    disarm()
    print('INSTALL/RESTORE FAILED. Inspect logs and BACKUP_DIR above.', file=sys.stderr)
    raise
print('Files replaced; 501/502 OFF verified by MQTT. Inspect wb-rules reload logs.')
print('No commissioning test, no global service restart, no 503/source file changes.')
PY
