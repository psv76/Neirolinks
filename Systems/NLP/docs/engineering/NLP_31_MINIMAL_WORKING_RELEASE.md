# NL Project 3.1 — минимальный рабочий выпуск (возобновление проектирования)

Issue coordinates: [#255](https://github.com/psv76/Neirolinks/issues/255), [#235](https://github.com/psv76/Neirolinks/issues/235), [#149](https://github.com/psv76/Neirolinks/issues/149).
Prepared 2026-10-26. **STATUS: PREPARATION ONLY, NOT DEPLOYED.**

## Product decision / release freeze

Priority: **restore usable electrical design in NL Project 3.1, not complete early AutoCAD scan optimization.**

**Release content** (candidate anchor `18babcb8861adecf74854e6dafdf89450856681a`, end of C7b):
- C1–C4 + C7a–C7b layer/parser/machine/catalog/validator: exactly nine numeric groups `100_*…900_*`; HVAC `600_*`; AV `700_*`, `BOARD_IN/BOARD_AV` on `700_*`, AV free `CABLE_ID`; `DALI_GROUP` on `300_*`/`400_*`; existing ordinary cable, legacy/DALI/passive/track rules.
- C5 internal COM filter **unused by default**; C6 fail-closed safety preserved. Default complete AutoLISP fingerprint / #148 cache/delta and COM fallback stay in service. Do not claim layer-based performance improvement in 3.1.
- Exclude all C7c, C7e, C7f user-facing / candidate scan/experimental partial Apply changes (branch pointers C7c `cbf557cc...`, C7e `cd511d7...`, C7f `9568b898...`). Preserve them as 3.2 engineering history / draft PRs; **do not expose the C7f checkbox** or ship a mode that always reverts to full scan.
- No mass DWG layer renames, no automatic cable renumbering, no change to user's active AutoCAD document, no automatic CAD close/save.

## Integration preflight (mandatory, bounded; don't start from C7f)

1. Source of truth remains `main/Systems/NLP`. Release candidate is only a staging branch until review. The accepted C7b ref is based directly on `integration/nlp-237-d23-stagec-d22-candidate` at `9366629eb8710de8985149e8bbc3a3e85a1823ea`. At preparation, GitHub `main` was `1a37f1a2281825ddca1bdda4d68011289c9963c9`, **43 commits divergent** relative to C7b candidate. Refresh both HEADs at execution. Do **not** blindly merge/cherry-pick/rebase the candidate over main and call it production: reconcile the already-staged #235 D23/#237 dependencies first, with a reviewed integration diff.
2. Inspect whether current release candidate already includes required #149 sync/apply diagnostic repairs from working tree branch. On 2026-10-26 user Windows checkout was clean on `fix/nlp-149-sync-apply-diagnostics`, not on main; do not reset/switch that active checkout while AutoCAD work is in progress. Use an isolated safe worktree per #145 or GitHub-only integration stage.
3. Validate that the actual application code/payload/storage/UI reads the nine group names and new accepted insertions; do not rely solely on the unit parser/validator tests. Check the existing 11 recorded `tests/cad_contract` failures, avoid blanket suppression. A release decision with waived historical failures needs documented reason/evidence and separate affirmative acceptance, not silence.
4. For versioning distinguish **product NLP 3.1** from `block_contract.json` authoring contract version `3.2.0`; do not rename catalog just to match the program version.

## Minimum gates before the user starts work in 3.1

- Integrate required code into a reviewed RC; leave `main` untouched until reviewed merge. Do not merge whole D stacks without dependency review. Run `cad_contract`, `cad_sync`, end-to-end preview/apply/roundtrip and release UI smoke on locked Windows Python **3.13** where supported; record exact successes/failures, issues and CI links. Critical tests: new 100/200/300/400/500/600/700/800/900 layers, BOARD_AV, DALI_GROUP, actual Bogdanovich-like synthetic project, first update + unchanged no-op, existing inserted handle changed/moved/removed and restoration, DALI/passive/tracks.
- Before touching **working database**: verify both local and cloud backup (restore sanity), inspect factual schema head and catalog release; if new schema/catalog required use official migration API and catalog successor per established policy; then startup smoke. A mere source checkout is not a live DB migration.
- Preserve canonical workstation paths (see #145): source/runtime `D:\GitHub_NEW\Neirolinks\Systems\NLP`; launcher `START_NL_PROJECT_3.vbs` / `NLP3.lnk`; DB `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite`; backups `D:\NLP_3_BACKUPS` and `D:\YandexDisk\05 NeiroLinks\NL Project 3.0\Backups`. Verify actual state before operations. Never overwrite user uncommitted work, kill AutoCAD or switch project automatically.
- **Separate explicit user authorization** before live DWG/SQLite modifications, migration, release activation or actual Bogdanovich DWG → Project Apply. Read-only AutoCAD / app smoke may be proposed first if access confirmed. A project designer renames Bogdanovich DWG layers manually under a separate controlled operation. Release acceptance includes explicit selected DWG/project binding, before/after snapshot, Update preview, confirmed Apply, repeat Update=no-op, and rollback path.
- Publish concise **how to start 3.1 and what is deferred to 3.2** note. Update #255/#235/#149 with evidence; source normative minimal parity and instructions should align with released behavior. Do not block work on full 3.2 TechDocs/optimization research.

## Status reporting

Use only `PREPARING`, `RC_READY_FOR_LOCAL_SMOKE`, `ACCEPTED_FOR_WORK` when evidence genuinely supports it. Current status **PREPARING**. Mark #255 release gate done only once 3.1 numeric rules are integrated and real Windows smoke is accepted; the scan acceleration criterion is explicitly deferred to 3.2 by user approval, not falsely passed. User-focused outcome is ability to resume Bogdanovich design safely.

No new Issues (record in #255 and #235). No C7c/C7f cherry-pick. No release claim from just a branch. No background promises.
