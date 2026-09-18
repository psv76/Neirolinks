#!/usr/bin/env python3
# HM2 Iset #51/#52. Default: read-only preflight. --apply explicitly changes live rules.
# NEVER invoked automatically from Github. Requires a human on site for --apply.
import argparse
import datetime
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request

COMMIT = '02a669831fcc9021ae6f9ff2eb1a98429ccb51de'
BASE = 'https://raw.githubusercontent.com/psv76/Neirolinks/' + COMMIT + '/objects/05_16_Iset/Wirenboard/'
RULES = pathlib.Path('/etc/wb-rules')
MODULES = pathlib.Path('/etc/wb-rules-modules')
DATA = pathlib.Path('/mnt/data')
NAMES = ['%02d_heating_%s.js' % (n, x) for n, x in [
    (20, 'safety_supervisor'), (21, 'floor_manager'), (22, 'basement_manager'),
    (23, 'living_manager'), (24, 'dhw_manager'), (25, 'ahu_manager'),
    (26, 'demand_arbiter'), (27, 'source_manager')]]
BASE_SHA = [
    '4115f6cdc5b9c23d18e90f851e20c1f1e1134fd4eb64f586d474265ac199bc45',
    '63ef0ef4d4f24ce01f88d7197cfa9f8edcc5677c977c250a9373eba04cdbd9c1',
    '2ed26630f7c94a3a46967de446415050cc96271517539a40268ef4c655e7a246',
    'dc2843a1c473e5c42405f51384b8c54ab4ac56d7cbbb5c2a980f722c9ef47f3b',
    '2d306e5a7c3a5d11906eb5205ec90599689237e8852f4508f570c2025f45f17f',
    '51b3ff424b9e9ec899025532c209686425c070fdf280d0d8964d1903ed34b1f6',
    '24cec204a986716c95b220f628abd0786e07fd46d13e3530c5a102d08c5cdf86',
    '2c0891faa6c863ad455bf905551678e5d5a6837c89a7951e97ba20726755ee32']
MODULE_SHA = {'HeatingCommon.js': '0de0010cf391651fbc14592df0f0d96d88b1d4f2b08bfae1f801d5db897e0692',
              'HeatingConfig.js': '6a088dffb80d672a981c8b4b0360d3785dad4f30aa0c674c65a7981e90a447eb'}
BLOBS = {
    NAMES[0]: '7287813d270836aed6bbe54a78084a93dd7d3ac8',
    NAMES[2]: 'dd3158da7620a542b9fc5ce60f0f91ee96e83596',
    NAMES[3]: '81ba7c468b014f05a7b6e6ea3922bfb037d99888',
    NAMES[4]: '1d65717f73cdd3195d1ac536e7ed5a332806a80a',
    '21_floor_reliability.patch': 'b38b0027aca3262b978e7d3b29ea0b0c2d10eb89'}
FLOOR_NEW_SHA = '48fc71c07710378182c4c217d115e927422e6f13b83258ecad5d518901986834'
# Archiving only; no unverified deletions and no moving of the only pre-HM2 backup.
ARCHIVE_NAMES = [
    '05_16_Iset_diag_20260831_201328.tar.gz',
    '05_16_Iset_issue19_20260909_235357.zip',
    'HM2_before_restart_20260917_221637.txt',
    'HM2_iteration_check_20260910_024756.txt',
    'HM2_quick_check_20260917_205100.txt',
    'hm2_ui_pass1.py', 'hm2_ui_pass2.py',
    'w1_diag_20260831_235412.txt']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def demand(ok, msg):
    if not ok:
        raise RuntimeError(msg)


def run(cmd, check=True):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=check)


def fetch(path, expected):
    url = BASE + path
    with urllib.request.urlopen(url, timeout=35) as resp:
        data = resp.read(2000000)
    demand(blob_sha(data) == expected, 'Git blob SHA mismatch: ' + path)
    return data


def patch_unified(old, patch):
    # Exact unified patch; all source-context lines must match the archived live file.
    src = old.decode('utf-8').splitlines(keepends=True)
    diff = patch.decode('utf-8').splitlines(keepends=True)
    pos, out, i = 0, [], 0
    import re
    while i < len(diff):
        header = re.match(r'^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', diff[i])
        if header is None:
            i += 1
            continue
        start = int(header.group(1)) - 1
        demand(pos <= start <= len(src), 'Invalid floor patch hunk position')
        out.extend(src[pos:start])
        pos = start
        i += 1
        while i < len(diff) and not diff[i].startswith('@@ '):
            line = diff[i]
            demand(line and line[0] in ' +-\\', 'Invalid patch line')
            if line.startswith('\\'):
                i += 1
                continue
            val = line[1:]
            if line[0] in ' -':
                demand(pos < len(src) and src[pos] == val, 'Floor baseline/patch context differs at line ' + str(pos + 1))
                pos += 1
            if line[0] in ' +':
                out.append(val)
            i += 1
    out.extend(src[pos:])
    return ''.join(out).encode('utf-8')


def main():
    ap = argparse.ArgumentParser(description='HM2 Iset #51: default CHECK; --apply explicitly installs')
    ap.add_argument('--apply', action='store_true', help='Stop service, install reviewed sources, start service; operator must be on site')
    ap.add_argument('--confirm', action='store_true', help='Confirm controlled restart and local archived cleanup')
    args = ap.parse_args()
    demand(os.geteuid() == 0, 'Run as root; check can run via sudo too')
    demand(not args.apply or args.confirm, '--apply requires --confirm (intentional service interruption)')
    demand(RULES.is_dir() and MODULES.is_dir() and DATA.is_dir(), 'Expected controller directories missing')
    demand(shutil.disk_usage(str(DATA)).free > 50 * 1024 * 1024, 'Less than 50 MiB free in /mnt/data')
    demand(run(['systemctl', 'is-active', 'wb-rules'], False).stdout.strip() == 'active', 'wb-rules must be active before work')
    original = {}
    for name, expected in zip(NAMES, BASE_SHA):
        p = RULES / name
        demand(p.is_file() and not p.is_symlink(), 'Missing/symlinked live source: ' + str(p))
        original[name] = p.read_bytes()
        demand(sha(original[name]) == expected, 'Live drift: ' + name + '; STOP: export fresh sources, no changes')
    for name, expected in MODULE_SHA.items():
        p = MODULES / name
        demand(p.is_file() and not p.is_symlink() and sha(p.read_bytes()) == expected,
               'Module differs from reviewed version: ' + name)
    demand(not (RULES / '28_heating_notifications.js').exists(), '28 notifications has become active; re-audit writers')
    print('PRECHECK: 8 live sources and 2 modules match reviewed SHA256; service active')
    staged = {}
    for name in [NAMES[0], NAMES[2], NAMES[3], NAMES[4]]:
        staged[name] = fetch('wb-rules/' + name, BLOBS[name])
    patch = fetch('release/21_floor_reliability.patch', BLOBS['21_floor_reliability.patch'])
    staged[NAMES[1]] = patch_unified(original[NAMES[1]], patch)
    demand(sha(staged[NAMES[1]]) == FLOOR_NEW_SHA, 'Unexpected assembled floor JS; STOP')
    for name in staged:
        text = staged[name].decode('utf-8')
        demand('require("HeatingCommon")' in text or 'require("HeatingConfig")' in text,
               'Unexpected JS content in ' + name)
    # Non-mutating syntax check if node exists on the WB.
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    stage = DATA / ('hm2_release_staging_' + stamp)
    stage.mkdir(mode=0o700)
    try:
        for name, data in staged.items():
            (stage / name).write_bytes(data)
        if shutil.which('node'):
            for name in staged:
                run(['node', '--check', str(stage / name)])
            print('SYNTAX: node --check PASS (5 files)')
        else:
            print('SYNTAX: node not installed here; developer-side model/syntax tests required')
        print('PACKAGE: pinned Git commit ' + COMMIT + ', Git blob hashes verified, floor SHA256 verified')
        if not args.apply:
            print('CHECK ONLY. No service or live files changed. For supervised installation: --apply --confirm')
            return
        # Back up complete rules and modules, not only edited files; no cleanup before backup.
        backups = DATA / 'hm2_backups'
        backups.mkdir(mode=0o700, exist_ok=True)
        backup = backups / ('before_51_' + stamp + '.tar.gz')
        with tarfile.open(str(backup), 'w:gz') as tf:
            tf.add(str(RULES), arcname='etc/wb-rules')
            tf.add(str(MODULES), arcname='etc/wb-rules-modules')
        with tarfile.open(str(backup), 'r:gz') as tf:
            for name in NAMES:
                demand('etc/wb-rules/' + name in tf.getnames(), 'Backup is incomplete: ' + name)
        print('BACKUP:', backup, 'SHA256:', sha(backup.read_bytes()))
        stopped = False
        try:
            run(['systemctl', 'stop', 'wb-rules'])
            stopped = True
            for name, data in staged.items():
                dest = RULES / name
                tmp = RULES / (name + '.hm2-new')
                tmp.write_bytes(data)
                os.chmod(str(tmp), dest.stat().st_mode & 0o777)
                os.replace(str(tmp), str(dest))
            run(['systemctl', 'start', 'wb-rules'])
            demand(run(['systemctl', 'is-active', 'wb-rules'], False).stdout.strip() == 'active',
                   'wb-rules did not become active')
            print('INSTALL: wb-rules active; this alone does NOT confirm physical heating')
        except Exception:
            if stopped:
                for name, data in original.items():
                    if name not in staged:
                        continue
                    dest = RULES / name
                    tmp = RULES / (name + '.hm2-rollback')
                    tmp.write_bytes(data)
                    os.chmod(str(tmp), 0o644)
                    os.replace(str(tmp), str(dest))
                run(['systemctl', 'start', 'wb-rules'], False)
                print('ROLLBACK: original five files restored; inspect wb-rules and heating immediately', file=sys.stderr)
            raise
        # Visual cleanup by moving only explicitly known diagnostics, NEVER backups or unreviewed files.
        archive = DATA / 'hm2_archive' / stamp
        moved = []
        for name in ARCHIVE_NAMES:
            src = DATA / name
            if src.is_file() and not src.is_symlink():
                try:
                    archive.mkdir(parents=True, exist_ok=True)
                    dst = archive / name
                    demand(not dst.exists(), 'Archive collision: ' + name)
                    shutil.move(str(src), str(dst))
                    moved.append(name)
                except Exception as err:
                    print('ARCHIVE WARNING: ' + name + ': ' + str(err))
        print('ARCHIVE:', archive, 'moved:', len(moved), 'old diagnostic files; no deletion and no disk saving')
        print('UNCHANGED: pre-HM2 backups, active source tarballs, other object scripts, legacy enable flags, modules')
        print('REQUIRED: inspect UI, source request, room demand, K3/K4 readback, temperatures, errors under supervision.')
        print('ROLLBACK BACKUP:', backup)
    finally:
        shutil.rmtree(str(stage), ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ABORT:', str(exc), file=sys.stderr)
        sys.exit(1)
