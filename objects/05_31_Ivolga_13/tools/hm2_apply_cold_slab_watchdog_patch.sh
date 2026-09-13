#!/bin/sh
# 05 31 Иволга 13 — HM2 cold slab watchdog patch.
#
# Назначение:
# - обновляет production managers 501/502 на живом WB;
# - добавляет штатный режим COLD_SLAB_WARMUP для ежегодного старта отопления
#   из холодной бетонной плиты;
# - не запускает отопление автоматически;
# - делает резервные копии перед правкой.

set -eu

BACKUP_DIR="/root/hm2/backups/cold_slab_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

python3 - <<'PY'
from pathlib import Path
import re
import shutil
from datetime import datetime

backup_dir = Path('/root/hm2/backups') / ('cold_slab_' + datetime.now().strftime('%Y%m%d_%H%M%S_py'))
backup_dir.mkdir(parents=True, exist_ok=True)

FILES = [
    ('/etc/wb-rules/501_tp_dom_manager.js', '413', '501'),
    ('/etc/wb-rules/502_gp_dom_manager.js', '415', '502'),
]

OLD_WD = "var WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0 };"
NEW_WD = "var WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0,\n    hydraulicBaseline: null, hydraulicSeen: false, coldWarmupSince: 0, lastWarmupLog: 0 };"

OLD_RESET = "function resetWatchdog() { WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0 }; }"
NEW_RESET = "function resetWatchdog() { WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0,\n    hydraulicBaseline: null, hydraulicSeen: false, coldWarmupSince: 0, lastWarmupLog: 0 }; }"

OLD_RESPONSE = """var RESPONSE = { graceS: 300, windowS: 600, stabilityS: 120,
    sampleS: 30, minSamples: 3, minRiseC: 1, minValvePct: 5, targetBandC: 1 };"""
NEW_RESPONSE = """var RESPONSE = { graceS: 300, windowS: 600, stabilityS: 120,
    sampleS: 30, minSamples: 3, minRiseC: 1, minValvePct: 5, targetBandC: 1,
    hydraulicDeltaC: 1,
    coldSlabSupplyBelowTargetC: 5,
    coldSlabMaxS: 86400,
    coldSlabLogIntervalS: 1800 };"""

COMMENT_MARKER = "// Hardened output contract: blocked operation actively writes three safe zeros."
NEW_COMMENT = """// Fix 2026-09-13:
// - ежегодный старт отопления из холодной бетонной плиты считается штатным режимом;
// - первичное падение температуры после включения насоса/клапана считается
//   гидравлическим откликом, а не отказом контура;
// - во время COLD_SLAB_WARMUP watchdog не защёлкивает RESPONSE_TIMEOUT,
//   пока сохраняется подтверждённый проток и нет перегрева/ошибок датчиков.

""" + COMMENT_MARKER


def build_response_watchdog(sensor_code: str) -> str:
    return f"""function responseWatchdog(now, running, pump, valveOn, position, supply, source, target)
{{
    if (!running) {{ resetWatchdog(); return 'IDLE'; }}
    if (!pump || !valveOn || position === null || position < RESPONSE.minValvePct) {{
        resetWatchdog(); return 'WAIT_OUTPUT_READBACK';
    }}
    if (source < target + CFG.tuning.sourceMarginC) {{
        resetWatchdog(); return 'WAIT_HOT_SOURCE';
    }}
    if (supply >= target - RESPONSE.targetBandC) {{
        resetWatchdog(); return 'AT_TARGET';
    }}
    if (!WD.since) {{
        WD.since = now;
        WD.baseline = supply;
        WD.hydraulicBaseline = supply;
        WD.hydraulicSeen = false;
        WD.coldWarmupSince = 0;
        WD.lastWarmupLog = 0;
    }}
    if (WD.hydraulicBaseline === null)
        WD.hydraulicBaseline = supply;

    if (!WD.hydraulicSeen && Math.abs(supply - WD.hydraulicBaseline) >= RESPONSE.hydraulicDeltaC) {{
        WD.hydraulicSeen = true;
        WD.coldWarmupSince = now;
        WD.badSince = 0;
        WD.samples = 0;
        logMsg('info', 'RESPONSE', 'COLD_SLAB_HYDRAULIC_RESPONSE; baseline=' +
            WD.hydraulicBaseline + '; supply=' + supply + '; target=' + target);
    }}

    if (supply - WD.baseline >= RESPONSE.minRiseC) {{
        WD.since = now;
        WD.baseline = supply;
        WD.hydraulicBaseline = supply;
        WD.hydraulicSeen = false;
        WD.coldWarmupSince = 0;
        WD.badSince = 0;
        WD.samples = 0;
        return 'RESPONSE_OK';
    }}

    if (WD.hydraulicSeen && supply < target - RESPONSE.coldSlabSupplyBelowTargetC) {{
        if (!WD.coldWarmupSince)
            WD.coldWarmupSince = now;
        if (now - WD.coldWarmupSince <= RESPONSE.coldSlabMaxS) {{
            WD.badSince = 0;
            WD.samples = 0;
            if (!WD.lastWarmupLog || now - WD.lastWarmupLog >= RESPONSE.coldSlabLogIntervalS) {{
                WD.lastWarmupLog = now;
                logMsg('info', 'RESPONSE', 'COLD_SLAB_WARMUP; elapsed_s=' +
                    (now - WD.coldWarmupSince) + '; supply=' + supply + '; target=' + target);
            }}
            return 'COLD_SLAB_WARMUP';
        }}
    }}

    if (now - WD.since < RESPONSE.graceS) return 'START_GRACE';
    if (now - WD.since < RESPONSE.graceS + RESPONSE.windowS) return 'OBSERVING';
    if (!WD.badSince) WD.badSince = now;
    if (!WD.lastSample || now - WD.lastSample >= RESPONSE.sampleS) {{
        WD.samples++;
        WD.lastSample = now;
    }}
    if (now - WD.badSince >= RESPONSE.stabilityS && WD.samples >= RESPONSE.minSamples) {{
        latchFault('RESPONSE_TIMEOUT_{sensor_code}'); return 'FAULT_LATCHED';
    }}
    return 'CONFIRMING_NO_RESPONSE';
}}
"""

for file_name, sensor_code, contour in FILES:
    path = Path(file_name)
    if not path.exists():
        raise SystemExit(f'ERROR: file not found: {path}')

    text = path.read_text(encoding='utf-8')
    original = text

    shutil.copy2(path, backup_dir / path.name)

    if 'COLD_SLAB_WARMUP' in text and 'coldSlabMaxS' in text:
        print(f'{contour}: already patched, backup saved: {backup_dir / path.name}')
        continue

    if COMMENT_MARKER in text and 'ежегодный старт отопления из холодной бетонной плиты' not in text:
        text = text.replace(COMMENT_MARKER, NEW_COMMENT, 1)

    if OLD_WD not in text:
        raise SystemExit(f'ERROR: WD block not found in {path}')
    text = text.replace(OLD_WD, NEW_WD, 1)

    if OLD_RESET not in text:
        raise SystemExit(f'ERROR: resetWatchdog block not found in {path}')
    text = text.replace(OLD_RESET, NEW_RESET, 1)

    if OLD_RESPONSE not in text:
        raise SystemExit(f'ERROR: RESPONSE block not found in {path}')
    text = text.replace(OLD_RESPONSE, NEW_RESPONSE, 1)

    pattern = re.compile(
        r"function responseWatchdog\(now, running, pump, valveOn, position, supply, source, target\)\n"
        r"\{\n.*?\n\}\n\nfunction temp\(path\)",
        re.DOTALL,
    )
    replacement = build_response_watchdog(sensor_code) + "\nfunction temp(path)"
    text, n = pattern.subn(replacement, text, count=1)
    if n != 1:
        raise SystemExit(f'ERROR: responseWatchdog block not replaced in {path}, replacements={n}')

    path.write_text(text, encoding='utf-8')
    print(f'{contour}: patched {path}')

print(f'BACKUP_DIR={backup_dir}')
PY

echo
printf '%s\n' '===== VERIFY PATCH MARKERS ====='
grep -n "COLD_SLAB" /etc/wb-rules/501_tp_dom_manager.js /etc/wb-rules/502_gp_dom_manager.js

echo
printf '%s\n' '===== RESTART WB-RULES ====='
systemctl restart wb-rules
sleep 6
systemctl status wb-rules --no-pager -l | head -40

echo
printf '%s\n' '===== RECENT HM2 START LOGS ====='
journalctl -u wb-rules --since "2 minutes ago" --no-pager | grep -Ei '501_tp_dom|502_gp_dom|HM2|error|exception|syntax|failed' || true

echo
printf '%s\n' 'cold slab watchdog patch complete'
