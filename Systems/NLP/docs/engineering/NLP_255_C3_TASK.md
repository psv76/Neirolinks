# NLP-255-C3 — staged AV identity and 700_* contract

TASK_ID: `NLP-255-C3-AV-IDENTITY`
ISSUE: `psv76/Neirolinks#255`
BASE_SHA: `8944943c709fcc005d9f18f703be76577717c69b` (accepted C2)
WORK_BRANCH: `feature/nlp-255-c3-av`
EXPECTED_START_SHA: See the current branch head from the C3 brief-only commit. Verify it before editing.
STATUS: READY FOR CODEX / NOT IMPLEMENTED

## Normative inputs

- `Systems/NLP/docs/product/24_AV_CABLE_SYSTEM.md`, especially §§2–6, 9, 12.
- Existing machine contract `Systems/NLP/resources/autocad/block_contract.json` version 3.2.0, `av_rules`; this file is **read-only in C3**.
- Issue #255: dynamic `700_<arbitrary valid suffix>` is AV; preserve free-text AV cable identity; never impose a 7YY numbering scheme.
- C1 `cad_contract/layer_names.py`; C2 `cad_contract/layer_groups.py` map valid 700_* to AV. Do not reimplement them.

## Result (one bounded coding task)

Introduce a **pure, staged AV helper** in new `src/nl_project_2/cad_contract/av_layer_identity.py` without runtime wiring:

1. `is_av_working_layer(layer: object) -> bool`: call the accepted C2 `function_group_for_working_layer`, true only for `AV` (700_*).
2. `normalize_av_cable_id(cable_id: str) -> str`: trim leading/trailing whitespace and uppercase, preserving all interior content and **never parsing or renumbering** as ordinary numeric lines. Empty/whitespace-only input becomes empty string. Do not silently turn nonstring inputs into identifiers: choose and document a clear explicit error contract for nonstring input, with tests.
3. `av_line_identity(board: str, cable_id: str) -> tuple[str, str] | None`: return normalized `(BOARD, CABLE_ID)` only when both fields are present (trim outer whitespace of board, uppercase-normalize cable ID); return `None` for incomplete fields. Do **not** require `BOARD` format, because AV board names are user-defined. Board matching case semantics: preserve the board's existing text case, do not force case conversion without evidence from existing runtime.
4. `duplicate_av_identities(items: Iterable[tuple[str, str]]) -> frozenset[tuple[str, str]]`: take valid board/id pairs, identify repeats of the **same normalized BOARD + CABLE_ID** within a board only; the same cable ID on different boards is permitted. Keep read-only/pure. Avoid turning incomplete rows into duplicates; document whether this function excludes them or requires normalized valid pairs.

The helpers only stage future integration. Do not implement write blocking, diagnostic persistence, catalog changes, or HDMI selection here.

## Mandatory tests

New `tests/cad_contract/test_av_layer_identity.py`, parameterized for:

- Valid `700_HDMI`, `700_Акустика`, `700_Living Room`, `700_A__B`; invalid `AV`, `700`, `700_`, `700_ HDMI`, `700_HDMI `, `701_HDMI`, `600_Отопление`, nonstring layer inputs.
- `CABLE_ID` normalization: `hdmi tv` → `HDMI TV`, ` Speaker Left ` → `SPEAKER LEFT`, `hdmi-1`, Cyrillic, numeric-looking text `701`, empty/only-spaces, case-insensitive identity after normalization. No required `7YY` format.
- Board + ID composite identity: duplicate within one `BOARD_AV` designation, different board same ID allowed, incomplete BOARD/ID remains distinguishable (no fabricated identity), preserve board spelling.
- Contract invariants from current read-only `block_contract` fixture: `av_rules.identity == ["BOARD", "CABLE_ID"]`, `normalize_cable_id == ["TRIM", "UPPERCASE"]`, `incomplete_is_scannable` true, `duplicate_identity_blocks_save` true; accepted `LOAD_TYPE` limited to `SPEAKER_CABLE` / `HDMI`. These tests are *contract inventory*, not implementation of write blocking.
- Assert AV classification does not depend on numeric ordinary `CABLE_ID` and no HDMI product selection or length quantity is performed by the helpers.

## Allowed file changes

Only new files:
- `Systems/NLP/src/nl_project_2/cad_contract/av_layer_identity.py`
- `Systems/NLP/tests/cad_contract/test_av_layer_identity.py`
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C3.md` (checkpoint).

## Forbidden changes

No edits to existing code/tests, `catalog.py`, `validator.py`, `layer_names.py`, `layer_groups.py`, contract JSON/schema, COM/scan, reconciliation, persistence, cable quantities, product selection/HDMI, norms, GitHub PR #262/#263, installed app, real DWG or SQLite. Do not connect helpers to runtime; do not start C4 or merge main. No new Issues.

## Verification (working directory Systems/NLP)

- `PYTHONPATH=src python -m pytest -q tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py tests/cad_contract/test_av_layer_identity.py`
- `python -m compileall -q src/nl_project_2/cad_contract`
- `python -m ruff check src/nl_project_2/cad_contract/av_layer_identity.py tests/cad_contract/test_av_layer_identity.py`
- `python -m ruff format --check src/nl_project_2/cad_contract/av_layer_identity.py tests/cad_contract/test_av_layer_identity.py`
- `git diff --check`; verify exactly allowed paths changed against expected start SHA.

## Stop, persistence, checkpoint

Follow process standard in Draft PR #264. If the work branch SHA differs from this brief's verified start SHA, stop and report, without silently resetting/rebasing. If time/limit is low, save a safe partial commit and checkpoint.

Commit to this work branch. Write checkpoint with `task_id, base_sha, start_sha, tested_commit_sha, final SHA in #255 comment, status, exact command results, changed paths, remaining risks, next_action`.

**NEXT ACTION:** independent coordinator review, not C4.

C3 is PASSED only for its limited pure helper scope; no claim that #255 AV runtime integration or Windows/live acceptance is done.
