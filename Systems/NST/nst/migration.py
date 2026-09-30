"""Explicit, restartable NLI 0.1.9 migration; originals remain recovery evidence."""
import copy
import os
from pathlib import Path
import shutil
import stat

from .layout import CONFIG_DIR, STATE_DIR, LOG_DIR, target
from .util import Lock, atomic, digest, read_json, require, sync_dir, write_json

LEGACY = ('/mnt/data/etc/neiro/nli', '/mnt/data/var/lib/neiro/nli',
          '/mnt/data/var/log/neiro/nli')
CANONICAL = (CONFIG_DIR, STATE_DIR, LOG_DIR)
MARKER = '/mnt/data/var/lib/neirolinks/nst-migration.json'


def inventory(folder):
    result = {}
    if not folder.exists():
        return result
    require(folder.is_dir(), 'Migration source is not a directory')
    for path in sorted(folder.rglob('*')):
        if path == folder / 'mutation.lock':
            continue  # Kernel coordination file; never copy a live lock to a new store.
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                'Migration links/junctions are forbidden')
        meta = path.stat()
        require(path.is_dir() or (stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1),
                'Migration special/hardlinked file is forbidden')
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = {
                'sha256': digest(path.read_bytes()), 'mode': stat.S_IMODE(meta.st_mode),
                'uid': meta.st_uid, 'gid': meta.st_gid}
    return result


def present(root='/'):
    return any(target(root, p).exists() for p in LEGACY)


def complete(root='/'):
    p = target(root, MARKER)
    return p.is_file() and read_json(p).get('phase') == 'complete'


def rewrite_config(value):
    if isinstance(value, dict):
        return {k: rewrite_config(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_config(v) for v in value]
    if isinstance(value, str):
        for old, new in zip(LEGACY, CANONICAL):
            if value == old or value.startswith(old + '/'):
                return new + value[len(old):]
        if value == '/usr/share/neiro-nli/payload':
            return '/usr/share/nst/payload'
    return value


def migrate(root='/', legacy_version=None):
    """No service actions. Every original byte and backup reference is retained.

    Caller must attest the installed NLI version before replacing its package;
    standalone migration additionally accepts the package's reviewed 0.1.9 config
    and backup schema, never an earlier nonpersistent layout.
    """
    marker = target(root, MARKER)
    with Lock(target(root, '/mnt/data/var/lib/neirolinks/nst-migration.lock')):
        if complete(root):
            return read_json(marker)
        require(present(root), 'No persistent NLI data to migrate')
        if legacy_version is None:
            status = target(root, '/var/lib/dpkg/status')
            if status.is_file():
                for paragraph in status.read_text().split('\n\n'):
                    fields = dict(line.split(': ', 1) for line in paragraph.splitlines() if ': ' in line)
                    if fields.get('Package') == 'neiro-nli':
                        legacy_version = fields.get('Version')
            if legacy_version is None:
                records = [read_json(p) for p in target(root, LEGACY[2]).glob('*.json')]
                records = [r for r in records if r.get('nli')]
                if records:
                    legacy_version = max(records, key=lambda r: r.get('time', ''))['nli']
        require(legacy_version == '0.1.9', 'Only attested NLI 0.1.9 migration is supported')
        config_path = target(root, LEGACY[0] + '/config.json')
        require(config_path.is_file(), 'Legacy config missing; refusing partial migration')
        config = read_json(config_path)
        require(all(k in config for k in ('object', 'role', 'hostname', 'components'))
                and isinstance(config['components'], dict), 'Invalid legacy config')
        # Locks are outside destinations; old engine mutations use this lock too.
        with Lock(target(root, LEGACY[1] + '/mutation.lock')):
            sources = [inventory(target(root, p)) for p in LEGACY]
            if marker.exists():
                journal = read_json(marker)
                require(journal['sources'] == sources, 'Legacy data changed during migration')
            else:
                require(not any(target(root, p).exists() for p in CANONICAL),
                        'Canonical NST data already exists; refusing to merge stores')
                journal = {'schema': 1, 'phase': 'copying', 'sources': sources,
                           'source_version': '0.1.9', 'installed': []}
                write_json(marker, journal)
            for index, (old, new) in enumerate(zip(LEGACY, CANONICAL)):
                dst = target(root, new)
                if index in journal['installed']:
                    continue
                # A crash after rename but before journal update is recognized by hashes.
                if dst.exists():
                    require(inventory(dst) == sources[index], 'Conflicting migration destination')
                else:
                    staging = target(root, new + '-migration-staging')
                    staging.mkdir(parents=True, exist_ok=True)
                    require(set(inventory(staging)) <= set(sources[index]), 'Foreign migration staging data')
                    for name, meta in sources[index].items():
                        src = target(root, old + '/' + name)
                        out = target(root, new + '-migration-staging/' + name)
                        atomic(out, src.read_bytes(), meta['mode'], (meta['uid'], meta['gid']))
                    require(inventory(staging) == sources[index], 'Migration copy verification failed')
                    os.replace(staging, dst)
                    sync_dir(dst.parent)
                journal['installed'].append(index)
                write_json(marker, journal)
            # Config only: keep byte-exact original, rewrite operational path references.
            original = config_path.read_bytes()
            atomic(target(root, CONFIG_DIR + '/legacy-nli-0.1.9-config.json'), original)
            write_json(target(root, CONFIG_DIR + '/config.json'), rewrite_config(config))
            journal['phase'] = 'complete'
            journal['original_config_sha256'] = digest(original)
            write_json(marker, journal)
            return journal
