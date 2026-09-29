"""Conservative attribution of shared wb-rules errors; never execute JS."""
import re
from pathlib import PurePosixPath

ERROR = re.compile(r'SyntaxError|ReferenceError|TypeError|exception|ERROR|write ignored|cannot find module|failed to (?:load|compile)', re.I)
TECHNICAL = re.compile(r'SyntaxError|ReferenceError|TypeError|cannot find module|failed to (?:load|compile)|'
                       r'(?:load|compil|pars)\w* (?:error|exception)', re.I)
TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*|[^\s]')


def tokens(source):
    return [t for t in TOKEN.findall(source) if not t.startswith(('//', '/*'))]


def literal(token):
    return token[1:-1] if len(token) > 2 and token[0] in "\"'" and token[-1] == token[0] and '\\' not in token else None


def devices(source):
    """Only literal declarations / uniquely assigned literal variables.

    Dynamic expressions, escaped IDs, duplicate assignments and properties are
    deliberately not inferred. Unknown attribution remains fatal.
    """
    ts = tokens(source)
    depths, depth = [], 0
    for token in ts:
        depths.append(depth)
        depth += (token == '{') - (token == '}')
    found = set()
    for i in range(len(ts) - 3):
        if ts[i:i+2] != ['defineVirtualDevice', '('] or ts[i+3] != ',' or (i and ts[i-1] == '.'):
            continue
        value = literal(ts[i+2])
        if value is None:
            if depths[i] != 0:  # do not infer variables through JS scopes
                continue
            name = ts[i+2]
            uses = [j for j, t in enumerate(ts[:-2]) if t == name and (
                ts[j+1] == '=' or (ts[j+1] in '+-*/%&|^?' and ts[j+2] == '=')
                or ts[j+1:j+3] in (['+', '+'], ['-', '-'])
                or (j and ts[j-1] in ('+', '-')) or ts[j+1] in ('.', '['))]
            if len(uses) == 1:
                j = uses[0]
                if depths[j] == 0 and j + 3 < len(ts) and ts[j+1] == '=' and ts[j+3] in (',', ';'):
                    value = literal(ts[j+2])
        if value and re.fullmatch(r'[A-Za-z0-9_.-]+', value):
            found.add(value)
    return found


def mentions(text, name):
    return re.search(r'(?<![\w.-])' + re.escape(name) + r'(?![\w.-])', text) is not None


def classify(text, sources, owned, device_prefixes, post_restart):
    """sources maps logical path to verified current bytes decoded as UTF-8."""
    device_owners = {}
    for path, source in sources.items():
        for name in devices(source):
            device_owners.setdefault(name, set()).add(path)
    protected = set()
    for path in owned:
        protected.add(PurePosixPath(path).name)
        protected.add(PurePosixPath(path).stem)
        for name in devices(sources.get(path, '')):
            protected.add(name)
        # Errors in directly imported helper modules can affect this component.
        ts = tokens(sources.get(path, ''))
        for i in range(len(ts)-3):
            if ts[i:i+2] == ['require', '('] and ts[i+3] == ')':
                name = literal(ts[i+2])
                if name:
                    protected.add(PurePosixPath(name).name + '.js')
    result = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not ERROR.search(line):
            continue
        evidence = [line]
        # Keep stack continuations with their error, but not the next INFO event.
        for following in lines[i+1:]:
            if re.match(r'^\s+at\s', following):
                evidence.append(following)
            else:
                break
        block = '\n'.join(evidence)
        own = any(mentions(block, name) for name in protected) or any(
            re.search(r'(?<![\w.-])' + re.escape(prefix), block) for prefix in device_prefixes)
        paths = {path for path in sources if mentions(block, PurePosixPath(path).name)}
        # WB native device-create error supplies an explicit device identity.
        match = re.search(r'\bon device\s+[\"\']?([A-Za-z0-9_.-]+)', block)
        if match:
            paths.update(device_owners.get(match[1], set()))
        # Ambiguous owners and shared modules are not evidence of independence.
        foreign = (len(paths) == 1 and not own and not (paths & owned)
                   and all(path.startswith('/etc/wb-rules/') for path in paths))
        technical = bool(TECHNICAL.search(block))
        category = ('component_fatal' if technical else 'component_diagnostic') if own or paths & owned else (
            'shared_runtime' if foreign else 'unattributed')
        result.append(dict(message=block, category=category, sources=sorted(paths), technical=technical,
                           fatal=technical and bool(own or paths & owned)))
    return result
