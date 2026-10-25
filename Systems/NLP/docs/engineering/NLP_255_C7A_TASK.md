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
