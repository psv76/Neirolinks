"""Canonical NST persistent layout; old NLI stores require explicit migration."""
import os
from .util import beneath, read_json, require, safe_relative

CONFIG_DIR = "/mnt/data/etc/neirolinks/nst"
DEFAULT_CONFIG = CONFIG_DIR + "/config.json"
STATE_DIR = "/mnt/data/var/lib/neirolinks/nst"
LOG_DIR = "/mnt/data/var/log/neirolinks/nst"
DATA_DIR = "/usr/share/nst"
BOOTSTRAP_STATE = STATE_DIR + '/bootstrap.json'
WB_ROOTS = {
    "/etc/wb-rules": "/mnt/data/etc/wb-rules",
    "/etc/wb-rules-modules": "/mnt/data/etc/wb-rules-modules",
}


def target(root, logical):
    require(isinstance(logical, str) and logical.startswith("/"), "Expected absolute path")
    safe_relative(logical[1:])  # validate before matching/remapping, including the suffix
    for alias, persistent in WB_ROOTS.items():
        if logical == alias or logical.startswith(alias + "/"):
            parent = beneath(root, "etc")
            link = parent / alias.rsplit("/", 1)[1]
            require(not getattr(link, "is_junction", lambda: False)(), "WB junction rejected")
            if link.is_symlink():
                # Inspect the link text, NOT resolve(): chained/relative/alternative
                # destinations are not canonical. Rebase only inside a sandbox root.
                require(os.readlink(link) == persistent, "Wrong canonical WB symlink: " + alias)
                real = beneath(root, persistent[1:])
                require(real.is_dir(), "Missing canonical WB persistent directory: " + persistent)
                return beneath(root, (persistent + logical[len(alias):])[1:])
            break  # plain directories remain supported on non-WB test installations
    return beneath(root, logical[1:])


def legacy_data_present(root):
    for path in ("/var/lib/neiro/nli", "/var/log/neiro/nli"):
        folder = target(root, path)
        if folder.exists() and any(folder.iterdir()):
            return True
    config = target(root, "/etc/neiro/nli/config.json")
    if config.exists():
        value = read_json(config)
        # Only the exact unconfigured 0.1.0 profile may be ignored.
        return value != dict(object="unconfigured", role="unconfigured", hostname="unconfigured", components={})
    return False


def load_config(path=None, root="/"):
    """Read-only. Never bootstrap or silently discard legacy/partially lost data."""
    from .migration import present, complete
    require(not present(root) or complete(root), 'LEGACY_MIGRATION_REQUIRED: run nst migrate-nli')
    path = path or DEFAULT_CONFIG
    require(path.startswith(CONFIG_DIR + "/"), "Config must be under " + CONFIG_DIR)
    config = target(root, path)
    if config.exists():
        return read_json(config)
    require(path == DEFAULT_CONFIG, "Explicit config does not exist: " + path)
    require(not legacy_data_present(root), "LEGACY_MIGRATION_REQUIRED: reviewed persistent config migration is required")
    bootstrap = target(root, BOOTSTRAP_STATE)
    if bootstrap.exists():
        initial = read_json(bootstrap)
        require(initial == dict(object='unconfigured', role='unconfigured', hostname='unconfigured', components={}),
                'Invalid bootstrap marker')
        pending = target(root, STATE_DIR + '/pending.json')
        if pending.exists():
            require(read_json(pending).get('component') == 'deployment', 'Unexpected pending without config')
        else:
            require(not any(p.name not in ('bootstrap.json',) for p in target(root, STATE_DIR).glob('*.json')),
                    'Installed NST state exists but config is missing')
        return initial
    for folder in (CONFIG_DIR, STATE_DIR, LOG_DIR):
        p = target(root, folder)
        require(not p.exists() or not any(p.iterdir()), "Persistent data exists but config is missing: " + folder)
    return read_json(target(root, DATA_DIR + "/default-config.json"))
