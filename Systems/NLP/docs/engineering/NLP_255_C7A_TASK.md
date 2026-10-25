# NLP #255 — C7 integration program and first bounded task

**Issue:** #255. **Baseline:** accepted C6 SHA `1b3d79de5e216e4254eea1ecc488a58802b8b6d2`.
**Working branch:** `feature/nlp-255-c7a-contract-integration`.
**Status:** prepared only, no C7 production implementation yet.

## Substages (separate Codex sessions and independent reviews)

- **C7a — contract/catalog migration:** machine functional groups 100..900, HVAC union, group rules and catalog resolver with focused tests. Do not touch COM or reconciliation. Validate special TRACK_DALI overlap and metadata invariant. See execution task below.
- **C7b — runtime validator:** connect numeric group semantics including ordinary CABLE_ID prefix, permitted device types, special HVAC blocks, AV free-text identity, and DALI_GROUP placement; preserve existing DALI ID/uniqueness/dynamic rules. Tests.
- **C7c — scan integration:** reconcile C5 fast filter with C6 non-authoritative safety: must either establish and prove correct handling of filtered-out existing inserts or keep filter opt-in/disabled; never bypass safety flags merely to enable performance. Preserve incremental #148. Tests.
- **C7d — normative docs, schema/parity and expanded synthetic/locked regression:** updates in canonical product contract, controlled release gates, CI evidence and separate Windows/AutoCAD acceptance plan; no client DWG migration, production activation, live database migration or main merge without authorization.

Completion of any one substage is **NOT** release approval and does not close Issue #255.

## Task C7a — execute only this

**TASK_ID:** NLP-255-C7A-CONTRACT-MAPPING.
**BASE_SHA:** `1b3d79de5e216e4254eea1ecc488a58802b8b6d2`.
**WORK_BRANCH:** `feature/nlp-255-c7a-contract-integration`. Before edits check exact current HEAD equals brief commit recorded in Issue #255.
**SOURCE:** Issue #255, existing product/20 contract and product/24 AV; accepted C1-C4 modules in `cad_contract/`, current machine `resources/autocad/block_contract.json` (3.2.0), catalog and catalog tests.

**Result:**
1. Introduce the approved numeric functional group mapping into the canonical *machine* contract and catalog reading layer: POWER=100, SWITCHES=200, LIGHTING_230V=300, LIGHTING_LED=400, SENSORS=500, HVAC=600 (preserve union of legacy HEATING and VENTILATION device types and their special contracts), AV=700 (preserve free CABLE_ID / BOARD_AV contract), NETWORK=800, BUS=900.
2. `BlockContractCatalog.groups_for_layer` should resolve valid numeric working layer names via C1/C2. For two different valid suffixes of the same numeric group return the same group. Invalid/foreign layers must not accidentally match a group. If legacy named-layer compatibility is required by existing fixtures/tests, document the boundary and make it explicit; do not silently weaken the new contract or rewrite old fixtures indiscriminately.
3. Update the machine block allowed_groups mappings needed to make HVAC effective; preserve device type allowances, TRACK_DALI and special BOARD/DALI/AV behavior. This task may uncover ambiguity: **stop with BLOCKED + evidence rather than guessing** if board layer placement, GROUP overlap or other existing special contracts cannot be resolved from #255.
4. Add targeted tests and run relevant existing catalog, contract, validator checks to expose breaks. The C7a task is not complete if catalog/contract inconsistency is left hidden; report known validator failures for C7b as blockers and do not claim total #255 PASSED.

**Allowed changes:** `Systems/NLP/resources/autocad/block_contract.json`, `Systems/NLP/src/nl_project_2/cad_contract/catalog.py`, targeted new/updated `Systems/NLP/tests/cad_contract/*` tests, checkpoint `Systems/NLP/docs/engineering/checkpoints/NLP_255_C7A.md`. If strict machine schema/parity test requires another file, stop and document exact additional scope before changing it.

**Forbidden:** `validator.py`, COM/scan/bridge, reconciliation, runtime activation, SQL schema/migration, other accepted C1-C6 code, production quantities/AutoCAD client DWG, product norms/TechDocs, main, D23 PRs. No C7b/C7c/C7d. No new Issues.

**Verification:** from `Systems/NLP`:
- Run C1–C4 focused tests plus appropriate existing catalog/contract tests; enumerate exact commands and results in checkpoint.
- `python -m compileall -q src/nl_project_2/cad_contract`
- `python -m ruff check src/nl_project_2/cad_contract/catalog.py`
- `git diff --check`
- Identify any legacy fixtures or existing validator tests failing because runtime validator is not yet migrated; do not mask failures. Do not claim locked Python 3.13/full CI or Windows live if not actually run.

**Checkpoint:** after implementation/tests, safe commit, final head SHA in Issue #255, concise `NLP_255_C7A.md` with start SHA, changed paths, exact tests, status PASSED/PARTIAL/BLOCKED, impact on existing validators and **one next action**. If remaining token/time budget low, persist partial and stop.

**Next action:** independent coordinator C7a review. **C7b not started.**


## Approved C7A resumption decision — 2026-10-25 (supersedes earlier BOARD_AV ambiguity)

**Decision reference:** Issue #255 architectural approval comment 6393840510. BOARD_AV placement has been explicitly resolved. Resume after checkpoint at `2bc4ca6275c5119b609e9a5cab12510558a2e371`; **start from the current brief-update HEAD**, not the original `54452f5d...`.

1. `BOARD_IN` with `DEVICE_TYPE=BOARD`, `LOAD_TYPE=BOARD_AV`, `BOARD_ID` is the AV destination board and must be accepted on **any valid `700_*` working layer**. AV `CABLE_OUTLET` also uses `700_*`. No need or permission to put BOARD_AV on `100_*`.
2. This is a **narrow exception based on block name + LOAD_TYPE + layer together**, not blanket permission for all BOARD blocks or ordinary power boards on `700_*`. Other BOARD roles follow their existing group restrictions. Prevent generic `BOARD_IN` on `700_*` with non-AV LOAD_TYPE; ensure a BOARD_AV on other numeric group is rejected.
3. Preserve the exact normative AV model: `docs/product/24_AV_CABLE_SYSTEM.md` §§2–5, `BOARD + CABLE_ID` free-text identity, allowed HDMI/SPEAKER_CABLE and duplicate rules. Machine JSON has a pre-existing inconsistency: `load_types.BOARD` lacks BOARD_AV and `board_rules.av_role` / `av_block_name` are empty. **Restore** `BOARD_AV`, `BOARD_IN` in those fields and verify tests.
4. The authoring exact reference `docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md` must be updated **narrowly** for the approved BOARD_AV role and placement; this reference is explicitly added to C7A allowed scope. The canonical product document `docs/product/20_AUTOCAD_BLOCK_CONTRACT.md` may receive a narrowly scoped approved BOARD_AV layer rule for parity. Do **not** rewrite unrelated blocks/ATTDEF hashes/physical DALI contract.
5. Preserve unchanged existing BOARD_IN semantics and explicit negative tests for ordinary BOARD on `700_*`; if the contract serializer cannot represent role-conditional layer placement without extending validator semantics, stage the intended role restriction in machine metadata + targeted tests **but do not claim runtime acceptance** before C7b. Never broaden allowed_groups for all BOARD types without a demonstrated role check.
6. **Baseline tests before edits:** 251 C1-C4 passed. Selected catalog/exact reference/validator tests had 125 passed, **7 pre-existing failures**: contract version 3.0.0 vs 3.2.0; 72nd CABLE_OUTLET_BUS definition; four existing ATTDEF hashes; blanket BUS_ID assertion. Do not disguise or change those expectations automatically. Document changes introduced by C7A distinctly from those existing baseline failures. No test-skipping to force green.

### Updated allowed paths

In addition to original C7A allowed machine JSON, `cad_contract/catalog.py`, targeted CAD-contract tests and C7A checkpoint, **allow only narrowly relevant** updates to:
- `Systems/NLP/docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md` (BOARD_AV role + layer placement, without unrelated canonical changes);
- `Systems/NLP/docs/product/20_AUTOCAD_BLOCK_CONTRACT.md` (only short approved BOARD_AV layer contract clarification).

Do NOT edit `validator.py` or COM/reconciliation. Record what validator cannot yet enforce, for C7b.

### Required negative and positive evidence

- valid `700_Аудио`/ `700_AV boards` with `BOARD_IN / BOARD_AV`; different free valid 700 suffixes may coexist;
- ordinary `BOARD_IN` roles (e.g. BOARD_DISTRIBUTION) on 700 rejected; BOARD_AV on 100 rejected; arbitrary BOARD-family entries not granted 700 permission;
- AV `CABLE_OUTLET` and identity remain correct, BOARD_AV source role resolved;
- existing TRACK_DALI overlap, HVAC union and non-AV group matching preserved;
- test and checkpoint clearly distinguish **staged machine/catalog allowance** from still-unmigrated runtime validator; if not enforceable without C7b changes, stop or mark PARTIAL rather than claim PASSED.

### Resume checkpoint

Do not redo C1-C6 or the C7A baseline investigation. Read `docs/engineering/checkpoints/NLP_255_C7A.md` only to understand prior blocker, then this addendum. The prior BLOCKED checkpoint is historical evidence; append a new result section or a new `NLP_255_C7A_RESUME.md` checkpoint and post final SHA/status to existing #255. Do not rewrite history. Next step remains independent coordinator review; **no C7b**.


## C7A resumed again — approved schema scope correction (2026-10-25)

**Confirmed blocker:** `resources/autocad/block_contract.schema.json`, `functional_groups.minProperties=10` (line 129 at checkpoint `a465c7d9d1c444b8fd45cf280bbaffceb79d4f68`), contradicts the normative **exactly nine groups** after joining HEATING and VENTILATION into HVAC.

**Expanded allowed file scope, narrowly:** `Systems/NLP/resources/autocad/block_contract.schema.json`. Codex is authorized to change **only** `functional_groups.minProperties` from `10` to `9`, and add/update appropriate focused tests for schema acceptance of exactly nine groups and rejection of fewer than nine. Preserve all other schema validation requirements; do not add dummy/tenth groups to silence schema. Do not modify schema `contract_version` or unrelated validation properties. If another schema conflict appears, report it with evidence before expanding scope.

This approval supplements prior C7A scope and BOARD_AV / `700_*` approval; they remain unchanged. Existing C7A checkpoint files are historical evidence and must be kept, including `NLP_255_C7A_RESUME.md` (BLOCKED at `a465c7d9d1c444b8fd45cf280bbaffceb79d4f68`). Create a new checkpoint `NLP_255_C7A_RESUME2.md` rather than rewriting old evidence.

**Resume from:** HEAD of this brief-update commit (pin SHA in #255), not the preceding checkpoint SHA. Re-use the 376 passing tests and seven **pre-existing** failing tests as baseline evidence; do not repeat broad investigation merely to establish the same blocker. After changes run schema validation and targeted catalog/contract tests. Report baseline failures separately from newly introduced failures, and do not alter existing tests simply to force a PASS. C7b not started.
