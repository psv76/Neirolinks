"""Whole-deployment transaction: durable rollback before the first service action."""
import copy
import re
import shutil
import stat

from .core import Engine, MAX_ARTIFACT, now
from .layout import CONFIG_DIR, DEFAULT_CONFIG, STATE_DIR
from .platform import PLATFORM_STATE, default_platform_state
from .plugins import PLUGINS
from .releases import RAW
from .util import Error, Lock, atomic, decode, digest, read_json, require, sync_dir, write_json


def object_target(path):
    require(path.startswith(('/etc/wb-rules/', '/etc/wb-rules-modules/'))
            and path.endswith('.js') and 'PersistentStorage' not in path
            and '507' not in path, 'Object target outside reviewed rule namespace')


class DeploymentTransaction:
    def __init__(self, engine):
        self.engine = engine

    def inventory(self, config, manifests, objects, previous):
        """Reject unknown writers and drift, including files absent from the next plan."""
        e = self.engine
        managed = {f['target']: f['sha256'] for m in manifests.values() for f in m['files']}
        approved = dict(objects)
        for r in config['components'].values():
            for path, sha in r.get('unmanaged_rules', {}).items():
                require(path not in managed, 'Managed/unmanaged ownership conflict')
                require(path not in approved or approved[path] == sha, 'Conflicting unmanaged hash')
                approved[path] = sha
        sources = {}
        for directory in ('/etc/wb-rules', '/etc/wb-rules-modules'):
            folder = e.target(directory)
            for p in folder.rglob('*') if folder.exists() else []:
                logical = directory + '/' + p.relative_to(folder).as_posix()
                e.target(logical)
                if p.is_dir() or p.suffix != '.js':
                    continue
                require(logical in managed or logical in approved, 'Unknown possible writer: ' + logical)
                sha = digest(p.read_bytes())
                require(sha == previous.get(logical, managed.get(logical, approved.get(logical))),
                        'Unknown file drift: ' + logical)
                sources[logical] = p.read_text(encoding='utf-8')
        return sources

    def prepare(self, deployment, source):
        e = self.engine
        config = copy.deepcopy(e.config)
        config.update(object=deployment['object'], role=deployment['role'],
                      hostname=e.system.hostname(), release_source='approved')
        manifests, payload, previous = {}, {}, {}
        for name in e.config['components']:
            m = e.current(name)
            e.files_match(m)
            previous.update({f['target']: f['sha256'] for f in m['files']})
        old_platform = read_json(e.target(PLATFORM_STATE)) if e.target(PLATFORM_STATE).exists() else {}
        old_deployment = (old_platform.get('deployment') or {}).get('manifest') or {}
        previous.update({f['target']: f['sha256'] for f in old_deployment.get('object_files', [])})
        objects = {f['target']: f['sha256'] for f in deployment['object_files']}
        for item in deployment['object_files']:
            object_target(item['target'])
            e.target(item['target'])
            raw = e.releases.fetch(RAW + deployment['source']['commit'] + '/' + item['source'], MAX_ARTIFACT)
            require(digest(raw) == item['sha256'], 'Object payload checksum mismatch')
            payload[item['target']] = raw
        outputs = set()
        for desired in deployment['components']:
            raw, m = source.component_manifest(desired)
            name = m['component']
            plugin = name if name in ('hhm', 'pressure_makeup') else 'files'
            r = config['components'].setdefault(name, {'plugin': plugin})
            require(r['plugin'] == plugin, 'Component plugin changed')
            r['allowed_targets'] = [f['target'] for f in m['files']]
            r['remote_payload'] = True
            r.pop('payload_dir', None)
            r.setdefault('unmanaged_rules', {}).update(objects)
            policy = PLUGINS[plugin]
            require(not outputs.intersection(policy.outputs), 'Conflicting physical output owner')
            outputs.update(policy.outputs)
            manifests[name] = m
        require(set(config['components']) == set(manifests),
                'Component removal requires a reviewed decommissioning plan')
        child = Engine(config, e.root, e.system, e.releases, e.controller)
        for name, m in manifests.items():
            child.validate(m, name)
            payload.update(child.payload(m, remote=True))
        require(sum(map(len, payload.values())) <= 64 * 1024 * 1024, 'Deployment exceeds 64 MiB')
        # Every previously managed target must remain represented; no implicit deletion.
        require(set(previous) <= set(payload), 'Managed file removal requires reviewed migration')
        for path, data in payload.items():
            p = e.target(path)
            if p.exists():
                meta = p.stat()
                require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, 'Non-regular/hardlinked target')
                require(digest(p.read_bytes()) == previous.get(path, digest(data)), 'Unknown file drift: ' + path)
            else:
                require(path not in previous, 'Missing previously managed target: ' + path)
        self.inventory(config, manifests, objects, previous)
        # Policy checks use the complete staged ownership set, before any write.
        child.rules_inventory = lambda m: self.inventory(config, manifests, objects, previous)
        for name, m in manifests.items():
            PLUGINS[config['components'][name]['plugin']].preflight(child, m)
        return config, manifests, payload, previous

    def snapshot(self, paths, folder):
        files = []
        for index, path in enumerate(sorted(set(paths))):
            p = self.engine.target(path)
            item = {'target': path, 'exists': p.exists()}
            if p.exists():
                meta = p.stat()
                require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, 'Nonregular backup target')
                raw = p.read_bytes()
                item.update(blob=str(index) + '.bin', sha256=digest(raw),
                            mode=stat.S_IMODE(meta.st_mode), uid=meta.st_uid, gid=meta.st_gid)
                atomic(self.engine.target(folder + '/' + item['blob']), raw)
            files.append(item)
        return files

    def apply(self, deployment, source, approved):
        e = self.engine
        record = e.record('sync', 'deployment')
        with Lock(e.target(STATE_DIR + '/mutation.lock')):
            try:
                require(not e.pending(), 'Recovery required before deployment')
                require(not e.target(STATE_DIR + '/self-update.json').exists(), 'Package recovery required')
                config, manifests, payload, previous = self.prepare(deployment, source)
                require(shutil.disk_usage(e.state_dir).free >= sum(map(len, payload.values())) * 3 + 1024*1024,
                        'Insufficient storage before deployment')
                paths = list(payload) + [DEFAULT_CONFIG, PLATFORM_STATE, CONFIG_DIR + '/controller-registry.json']
                paths += [STATE_DIR + '/' + name + '.json' for name in manifests]
                folder = STATE_DIR + '/deployment-backups/' + record['id']
                meta = {'files': self.snapshot(paths, folder), 'services': deployment['services'],
                        'config': copy.deepcopy(e.config)}
                write_json(e.target(folder + '/metadata.json'), meta)
                record['deployment_backup'] = {'path': folder,
                    'sha256': digest(e.target(folder + '/metadata.json').read_bytes())}
                # Recheck identity, interlocks and drift after staging/backup, under lock.
                self.prepare(deployment, source)
                e.checkpoint(record)
                e.services(deployment, 'stop', record)
                for path, raw in payload.items():
                    p = e.target(path)
                    owner = (p.stat().st_uid, p.stat().st_gid) if p.exists() else None
                    atomic(p, raw, 0o644, owner)
                write_json(e.target(DEFAULT_CONFIG), config)
                write_json(e.target(CONFIG_DIR + '/controller-registry.json'), approved['registry'])
                for name, m in manifests.items():
                    state = dict(e.state(name) or {}) if name in e.config['components'] else {}
                    # Old component rollback references are preserved; the whole-deployment
                    # backup covers new installs and all object/config changes together.
                    state.update(manifest=m, last_result='sync_ok')
                    write_json(e.target(STATE_DIR + '/' + name + '.json'), state)
                child = Engine(config, e.root, e.system, e.releases, e.controller)
                since = now()
                e.services(deployment, 'start', record)
                for m in manifests.values():
                    child.verify(m, since, record)
                if deployment['object_files']:
                    from .journal import classify
                    sources = self.inventory(config, manifests,
                        {f['target']: f['sha256'] for f in deployment['object_files']}, {})
                    events = classify(e.system.journal(since), sources, set(payload), (), True)
                    require(not any(x['fatal'] for x in events), 'Deployment journal reports errors')
                    e.system.active('wb-rules')
                for path, raw in payload.items():
                    require(e.target(path).read_bytes() == raw, 'Deployment changed during verification')
                platform = default_platform_state()
                platform.update(controller={k: deployment[k] for k in ('object', 'node', 'role')},
                    registry={'tag': approved['tag'], 'sha256': approved['registry_sha256']},
                    deployment={'tag': approved['tag'], 'sha256': approved['deployment_sha256'], 'manifest': deployment},
                    desired_state={'status': 'exact', 'checked_at': now()})
                platform['controller']['serial'] = deployment['controller_serial']
                write_json(e.target(PLATFORM_STATE), platform)
                record.update(final_status='ok', install='ok', verify='ok')
                e.audit(record)
                e.clear_pending()
                e.config = config
                return record
            except BaseException as exc:
                record.update(final_status='failed', error=str(exc) or type(exc).__name__)
                if e.pending() and e.pending().get('id') == record['id']:
                    try:
                        self._restore(record)
                        record['final_status'] = 'rolled_back'
                    except BaseException as recovery_error:
                        record.update(final_status='recovery_required', rollback_error=str(recovery_error))
                        e.checkpoint(record)
                e.audit(record)
                return record

    def _restore(self, record):
        e = self.engine
        ref = record['deployment_backup']
        require(re.fullmatch(re.escape(STATE_DIR) + r'/deployment-backups/[0-9a-f]{32}', ref['path']),
                'Invalid deployment backup path')
        raw = e.target(ref['path'] + '/metadata.json').read_bytes()
        require(digest(raw) == ref['sha256'], 'Corrupted deployment backup')
        meta = decode(raw)
        blobs = {}
        for f in meta['files']:
            e.target(f['target'])
            if f['exists']:
                data = e.target(ref['path'] + '/' + f['blob']).read_bytes()
                require(digest(data) == f['sha256'], 'Corrupted deployment backup blob')
                blobs[f['target']] = data
        # Retain pending intent until all files, state and service verification succeed.
        e.services(meta, 'stop', record)
        for f in meta['files']:
            p = e.target(f['target'])
            if f['exists']:
                atomic(p, blobs[f['target']], f['mode'], (f['uid'], f['gid']))
            elif p.exists():
                p.unlink()
                sync_dir(p.parent)
        since = now()
        e.services(meta, 'start', record)
        for f in meta['files']:
            p = e.target(f['target'])
            require((p.is_file() and digest(p.read_bytes()) == f['sha256']) if f['exists'] else not p.exists(),
                    'Deployment restoration mismatch')
        child = Engine(meta['config'], e.root, e.system, e.releases, e.controller)
        for name in meta['config']['components']:
            child.verify(child.current(name), since, record)
        e.config = meta['config']
        record['rollback'] = 'ok'
        e.audit(record)
        e.clear_pending()

    def recover(self):
        e = self.engine
        require(e.controller and e.controller.get('mutation_allowed'), 'Controller recovery blocked')
        with Lock(e.target(STATE_DIR + '/mutation.lock')):
            record = e.pending()
            require(record and record.get('component') == 'deployment', 'No deployment recovery pending')
            require((record.get('controller') or {}).get('identity', {}).get('serial') ==
                    e.controller['identity']['serial'], 'Recovery controller mismatch')
            self._restore(record)
            record['final_status'] = 'ok'
            e.audit(record)
            return record
