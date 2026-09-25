"""Approved GitHub release catalogs. No mutable branch payloads or implicit trust."""
import http.client
import re
import urllib.request
from urllib.parse import urlparse
from . import __version__
from .manifest import match, SHA, validate
from .util import Error, decode, digest, require, safe_relative

REPO = 'psv76/Neirolinks'
API = 'https://api.github.com/repos/' + REPO
RAW = 'https://raw.githubusercontent.com/' + REPO + '/'
MAX_METADATA = 2 * 1024 * 1024


class TransportError(Error):
    pass


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        require(parsed.scheme == 'https' and parsed.hostname == 'release-assets.githubusercontent.com',
                'Untrusted release redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=MAX_METADATA, binary=False):
    require(url.startswith((API + '/', RAW)), 'Release source must be ' + REPO)
    headers = {'User-Agent': 'neiro-nli/' + __version__,
               'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json'}
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.build_opener(Redirect).open(request, timeout=20) as response:
            data = response.read(limit + 1)
            require(len(data) <= limit, 'Oversize release data')
            size = response.headers.get('Content-Length')
            require(size is None or int(size) == len(data), 'Truncated release data')
            return data
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise TransportError('Нет связи с approved releases: ' + str(exc)) from exc


def version(value):
    match(value, r'\d+\.\d+(?:\.\d+)?(?:-[A-Za-z0-9_.-]+)?(?:\+[A-Za-z0-9_.-]+)?',
          'release version')
    numbers = re.match(r'\d+\.\d+(?:\.\d+)?', value)[0].split('.')
    return tuple(map(int, numbers)) + (0,) * (3 - len(numbers))


class Releases:
    def __init__(self, transport=fetch):
        self.fetch = transport

    def catalogs(self):
        """Publishing a stable nli-approved-* Release is the maintainer approval act."""
        catalogs = []
        for page in range(1, 11):
            releases = decode(self.fetch(API + '/releases?per_page=100&page=' + str(page)))
            require(type(releases) is list, 'Invalid GitHub releases response')
            for release in releases:
                require(type(release) is dict, 'Invalid GitHub release')
                if (release.get('draft') is not False or release.get('prerelease') is not False
                        or not release.get('published_at') or not release.get('tag_name', '').startswith('nli-approved-')):
                    continue
                require(type(release.get('assets')) is list and all(type(a) is dict for a in release['assets']),
                        'Invalid release assets')
                assets = [a for a in release['assets'] if a.get('name') == 'nli-catalog.json']
                require(len(catalogs) < 32, 'Approved catalog count bound exceeded; consolidate published catalogs')
                require(len(assets) == 1, 'Approved release requires one nli-catalog.json')
                data = self.asset(assets[0], MAX_METADATA)
                catalog = decode(data)
                require(type(catalog) is dict, 'Invalid catalog object')
                require(catalog.get('schema') == 1 and catalog.get('repository') == REPO
                        and catalog.get('approved') is True, 'Invalid approved catalog')
                require(type(catalog.get('components')) is list and len(catalog['components']) <= 100,
                        'Invalid catalog components')
                catalogs.append((catalog, release))
            if len(releases) < 100:
                return catalogs
        raise Error('Release catalog pagination bound exceeded')

    def asset(self, asset, limit):
        ident = asset.get('id')
        require(type(ident) is int and ident > 0, 'Invalid release asset ID')
        expected = asset.get('digest', '')
        require(expected.startswith('sha256:'), 'GitHub release asset must expose SHA256 digest')
        match(expected[7:], SHA, 'asset SHA256')
        data = self.fetch(API + '/releases/assets/' + str(ident), limit, True)
        require(digest(data) == expected[7:], 'Release asset checksum mismatch')
        return data

    def component(self, engine, component, installed):
        candidates = []
        for catalog, _ in self.catalogs():
            for entry in catalog['components']:
                require(type(entry) is dict, 'Invalid release entry')
                if (entry.get('component'), entry.get('object'), entry.get('role')) != (
                        component, engine.config['object'], engine.config['role']):
                    continue
                require(entry.get('approved') is True, 'Unapproved component entry')
                rank = version(entry['version'])
                candidates.append((rank, entry))
        if not candidates:
            return installed, {'source': 'approved-releases', 'update_available': False}
        candidates.sort(key=lambda item: item[0], reverse=True)
        rank, entry = candidates[0]
        require(all(e == entry for r, e in candidates if r == rank), 'Conflicting latest approved releases')
        if rank <= version(installed['version']):
            return installed, {'source': 'approved-releases', 'update_available': False}
        required = entry['minimum_nli']
        require(version(__version__) >= version(required), 'Требуется NLI ' + required + ': nli self-update')
        ref = entry['manifest']
        match(ref['commit'], r'[0-9a-f]{40}', 'immutable manifest commit')
        safe_relative(ref['path'])
        match(ref['sha256'], SHA, 'manifest SHA256')
        data = self.fetch(RAW + ref['commit'] + '/' + ref['path'])
        require(digest(data) == ref['sha256'], 'Manifest checksum mismatch')
        m = validate(decode(data))
        require(m['release']['repository'] == REPO and m['version'] == entry['version'], 'Release identity mismatch')
        engine.validate(m, component)
        return m, {'source': 'approved-releases', 'manifest_sha256': ref['sha256'],
                   'update_available': True, 'minimum_nli': required}

    def package(self):
        candidates = []
        for catalog, release in self.catalogs():
            package = catalog.get('nli')
            if package is None:
                continue
            require(type(package) is dict, 'Invalid NLI package metadata')
            require(package.get('approved') is True, 'Unapproved NLI package')
            rank = version(package['version'])
            match(package['sha256'], SHA, 'package SHA256')
            assets = [a for a in release['assets'] if a['name'] == 'neiro-nli_' + package['version'] + '_all.deb']
            require(len(assets) == 1 and assets[0].get('digest') == 'sha256:' + package['sha256'],
                    'Missing/mismatched NLI release package')
            candidates.append((rank, package, assets[0]))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        rank, package, asset = candidates[0]
        require(all(p == package for r, p, a in candidates if r == rank), 'Conflicting approved NLI packages')
        return dict(package, asset=asset)
