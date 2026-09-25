"""Explicit package upgrade. No component service actions or config rewriting."""
from pathlib import Path
import tempfile
from . import __version__
from .layout import STATE_DIR
from .releases import TransportError, version
from .util import Error, Lock, atomic, digest, require, write_json

MAX_PACKAGE = 32 * 1024 * 1024


class SelfUpdate:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, check=False):
        e = self.engine
        record = e.record('self-update check' if check else 'self-update', 'nli')
        record['from_version'] = __version__
        if check:
            try:
                package = e.releases.package()
                record.update(to_version=package['version'] if package else __version__, final_status='ok',
                              update_available=bool(package and version(package['version']) > version(__version__)))
            except (Error, OSError, ValueError, KeyError) as exc:
                record.update(final_status='unavailable' if isinstance(exc, TransportError) else 'failed', error=str(exc))
            return record
        with Lock(e.target(STATE_DIR + '/mutation.lock')):
            marker = e.target(STATE_DIR + '/self-update.json')
            try:
                package = e.releases.package()
                record['to_version'] = package['version'] if package else __version__
                if not marker.exists() and (not package or version(package['version']) <= version(__version__)):
                    record.update(final_status='ok', install='not_needed')
                    e.audit(record)
                    return record
                require(package is not None and version(package['version']) >= version(__version__),
                        'Cannot repair pending package without approved same/newer release')
                data = e.releases.asset(package['asset'], MAX_PACKAGE)
                require(digest(data) == package['sha256'], 'Package checksum mismatch')
                # Temp directory is removed on all ordinary success/failure paths.
                with tempfile.TemporaryDirectory(prefix='nli-package-', dir=e.state_dir) as tmp:
                    path = Path(tmp) / 'neiro-nli.deb'
                    atomic(path, data)
                    fields = e.system.run(['/usr/bin/dpkg-deb', '-f', str(path), 'Package', 'Version', 'Architecture'])
                    require(fields.splitlines() == ['Package: neiro-nli', 'Version: ' + package['version'], 'Architecture: all'],
                            'Wrong Debian package identity')
                    # Require runtime package without maintainer scripts/triggers/conffiles.
                    self.validate_deb(data)
                    record.update(install='running', package_sha256=package['sha256'])
                    write_json(marker, record)  # separate intent preserves component pending byte-for-byte
                    e.audit(record)
                    e.system.run(['/usr/bin/dpkg', '--install', str(path)], timeout=180)
                installed = e.system.run(['/usr/bin/dpkg-query', '-W', '-f=${Version}', 'neiro-nli'])
                require(installed == package['version'], 'Installed NLI version mismatch')
                require(e.system.run(['/usr/bin/nli', '--json', '--version']) == '{"version": "' + installed + '"}',
                        'NLI executable version mismatch')
                record.update(install='ok', verify='ok', final_status='ok')
                e.audit(record)
                marker.unlink()
                e.cleanup(record)
            except BaseException as exc:
                record.update(final_status='partial_failure' if marker.exists() else 'failed', error=str(exc))
                if marker.exists():
                    write_json(marker, record)
                e.audit(record)
            return record

    @staticmethod
    def validate_deb(data):
        """Reject executable package hooks and writes outside NLI runtime namespaces."""
        import io
        import tarfile
        require(data[:8] == b'!<arch>\n', 'Invalid deb archive')
        offset, members = 8, {}
        while offset < len(data):
            header = data[offset:offset+60]
            require(len(header) == 60 and header[58:] == b'`\n', 'Invalid deb header')
            name = header[:16].decode().strip().rstrip('/')
            size = int(header[48:58])
            require(0 <= size <= MAX_PACKAGE and name not in members, 'Invalid deb member')
            members[name] = data[offset+60:offset+60+size]
            require(len(members[name]) == size, 'Truncated deb member')
            offset += 60 + size + size % 2
        require(set(members) == {'debian-binary', 'control.tar.gz', 'data.tar.gz'}
                and members['debian-binary'] == b'2.0\n', 'Unsupported deb format')
        for key in ('control.tar.gz', 'data.tar.gz'):
            with tarfile.open(fileobj=io.BytesIO(members[key]), mode='r:gz') as archive:
                total = 0
                for item in archive:
                    name = item.name.removeprefix('./').rstrip('/')
                    require(not name.startswith('/') and '..' not in name.split('/') and '\\' not in name,
                            'Unsafe package path')
                    require(item.isfile() or item.isdir(), 'Package links/devices rejected')
                    total += item.size
                    require(total <= 128 * 1024 * 1024, 'Oversize expanded package')
                    if key == 'control.tar.gz':
                        require(item.isdir() or name == 'control', 'Package maintainer hooks/config forbidden')
                    elif item.isfile():
                        require(name == 'usr/bin/nli' or name.startswith(('usr/lib/neiro-nli/', 'usr/share/neiro-nli/',
                                                                                    'usr/share/doc/neiro-nli/')),
                                'Package would modify persistent/system data')
                    else:
                        roots = ('usr/bin', 'usr/lib/neiro-nli', 'usr/share/neiro-nli', 'usr/share/doc/neiro-nli')
                        require(any(root == name or root.startswith(name + '/') or name.startswith(root + '/') for root in roots),
                                'Package directory outside NLI namespaces')
