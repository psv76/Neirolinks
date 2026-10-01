"""Prune only NLI-owned successful history after transaction commit, under lock."""
from .layout import STATE_DIR
from .util import beneath, read_json, require

KEEP_AUDIT = 20
KEEP_BACKUPS = 3


def remove_tree(folder):
    # Validate the entire tree before deleting anything. Never follow links.
    paths = [beneath(folder, p.relative_to(folder).as_posix()) for p in folder.rglob('*')]
    for p in sorted(paths, key=lambda p: len(p.parts), reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    folder.rmdir()


def cleanup(engine):
    if engine.pending():
        return {'status': 'deferred', 'reason': 'pending recovery'}
    records = []
    if engine.log_dir.exists():
        for p in engine.log_dir.glob('*.json'):
            records.append((beneath(engine.log_dir, p.name), read_json(p)))
    protected = set()
    for component in engine.config['components']:
        ref = (engine.state(component) or {}).get('previous_backup')
        if ref:
            protected.add(ref['id'])
    keep = set()
    groups = {}
    for path, record in records:
        if record.get('final_status') != 'ok':
            keep.add(record['id'])  # failed/partial/interrupted/unverified evidence never pruned
            if record.get('backup'):
                protected.add(record['backup']['id'])
        else:
            groups.setdefault(record.get('component'), []).append(record)
    for group in groups.values():
        group.sort(key=lambda r: (r['time'], r['id']), reverse=True)
        keep.update(r['id'] for r in group[:KEEP_AUDIT])
        backups = [r['backup']['id'] for r in group if r.get('backup')]
        protected.update(backups[:KEEP_BACKUPS])
    removed = []
    for path, record in records:
        ident = record['id']
        # Only delete a backup with a successful audit proving its ownership.
        ref = record.get('backup')
        if record.get('final_status') == 'ok' and ref and ref['id'] not in protected:
            folder = engine.target(STATE_DIR + '/backups/' + ref['id'])
            if folder.is_dir():
                remove_tree(folder)
                removed.append('backup:' + ref['id'])
        if ident not in keep and ident not in protected:
            transcript = beneath(engine.log_dir, ident + '.firmware.log')
            if transcript.exists():
                transcript.unlink()
            path.unlink()
            removed.append('audit:' + ident)
    return {'status': 'ok', 'removed': removed, 'keep_successful_audits_per_component': KEEP_AUDIT,
            'keep_recent_backups_per_component': KEEP_BACKUPS}
