# NLP 3.1 — D23 dependency integration preflight (draft only)

## Scope and source

This is an **evidence-only integration preparation**, not a merge authorization. Product source of truth: `main`, code root `Systems/NLP`. D21 PR #260 and D22 PR #261 are stacked and remain draft. The separate Stage C length candidate is PR #231 (on PR #218), NOT a parent of D22. Existing Issues #235 and #237 control the gates. #255 layer work is also unresolved.

## Git topology established 2026-10-24

| Ref | Relation to main at inspection | Status |
| --- | --- | --- |
| `fix/nlp-237-d22-shadow-integrity` / #261 | 315 commits ahead, 110 changed files | draft; no main merge |
| `fix/nlp-216-length-q04q05q08` / #231 | 10 commits ahead, 19 changed files | separate draft; not contained in D22 |
| main | merge-base `8f566f7a1eddb2c7eb4242dd275cdd775ca79a89` for both | authoritative |

Comparing both branches shows overlaps in `cables/service.py` and the cable tests. Work's previous read-only trial reported two merge conflicts (cable service and core-calculation tests) and byte-identical arithmetic core, but the latter two assertions MUST be reverified by independent CI before relied upon. Branch lists are not a proof of a successful future merge.

## Safe synthetic acceptance sequence

1. Fetch both candidate heads, record immutable SHAs and merge-bases; compare `main...D22` and `main...#231`. Fail when refs do not exist or move unexpectedly during a check.
2. Perform a **read-only** `git merge-tree` preflight on D22 and #231; report whether conflicts exist and list the affected files. A conflict is an expected **blocking result**, not license to auto-resolve.
3. Run D22 request-scoped shadow tests and the existing cable, BUS, CAD-sync and specification synthetic tests on the D22 candidate. Do not substitute these for the locked suite.
4. Run Stage C's arithmetic and Q06 tests on its **own** candidate with synthetic data; compare expected FLOOR/CEILING/CHANNEL semantics. Do not apply #231 service or calculation changes to D22.
5. Record evidence that ordinary current `effective_length`, manual overrides, normal specification, Conduit assignments and exports stay untouched after preview/revoke. A new preview may not change authoritative values.
6. Integration candidate remains blocked until owners decide how to reconcile service/tests and the combined 3.2.0/72-definition contract with #255; complete DB/Windows/live gates separately.

## Explicit non-goals

No production quantity activation, new ACTIVE/REVOKED persistent state, schema/catalog changes, automatic transfer of #231 recalculation, DWG modification, real SQLite access, AutoCAD, TechDocs updates, merges, release or tag. Do not normalize the old 3.0.0/71-definition assertions by silently deleting their compatibility coverage. This preflight does **not** declare D22 or #231 production-ready.

## Evidence to retain

Immutable head SHAs, exact test command and pass/fail summary, merge-tree conflict filenames, which branch each suite used, and unchanged authoritativeness of manual and canonical quantities. Any unresolved conflict remains a blocker in #235/#237 rather than an implicit implementation decision.

## Additional conflict classification (verified in CI)

The conflict in `tests/unit/test_length_policy.py` is a Git add/add conflict, but the
D22 and Stage C revisions have **identical Python AST** (formatting differs).
Verified using `tools/d23_test_ast_parity.py` in the D23 GitHub Actions merge-tree job.
Resolution can retain the D22 formatting without dropping Stage C test assertions.
The cable-service content conflict **is not proven safe** by this result: it
requires a purpose-built integrated candidate, separate tests and non-activation
checks. Do not use an automatic ours/theirs resolution for that module.

## CAD fixture correction checkpoint (2026-10-24)

The expanded CAD-sync shard exposed obsolete passive EL_BOX fixture attributes (`BUS_POINT_ID`), no longer legal under the 3.2.0 passive `BUS_ID` contract. The isolated integration Draft #263 updates blank legacy tags only in `test_issue142_working_journal.py` and `test_issue134_box_identity.py`, without production parser behavior changes. Run the full CAD shard before claiming remediation; `ROOM` resolution and selective import failures remain independently unverified. Persistence diagnostic assumptions were corrected separately.
