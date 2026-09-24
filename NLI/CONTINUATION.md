# Continuation checkpoint — pressure_makeup component

User explicitly requested saving progress while continuing until usage blocks.
Branch: codex/nli-v0.1; existing draft PR #71, base unchanged.
Latest requirements: https://github.com/psv76/Neirolinks/pull/71#issuecomment-5809381674
No live WB/SSH/restarts/firmware/merge. Local object source 507 stays unchanged.

Implemented so far (not yet final CI validated): pressure_makeup plugin, strict
cross-component ownership/hash inventory, standalone immutable baseline 1.0,
boiler two-component config, package bump 0.1.2, config-only registration helper,
component and canonical-WB tests, Node VM exact-baseline restart tests, installed
container smoke updated for both components.

Baseline commit 728f5c4aa708c5040da2dce39b01adf68a1bfdc1; exact source
NLI/releases/pressure_makeup/1.0/507_Pressure_makeup.js equals PR65 blob minus
ONE final LF, per reviewed live evidence. Original object file unmodified.
JS SHA256 767739a1358381297605fb598c38dfd6925e976121dfcfef2d9a77ea9ec4dafd.
Manifest SHA256 4a606a8b4e52f76576e08c54266e240b18144ca2cc4bce7a2ef3b10c169aae6e.

Last completed local suite: 105 tests, 71 PASS, 34 symlink skips on Windows.
After that added bootstrap/probe tests; rerun complete suite. Node runtime tests
PASS (3 groups). Full HHM regressions still required for final changes.

Remaining work:
1. Finish README/SECURITY/WB_SMOKE/TEST_RESULTS updates. README and WB_SMOKE
   versions bumped 0.1.2, but old statements saying 507 always unmanaged remain:
   replace with HHM exclusion + pressure_makeup ownership. WB_SMOKE fresh config
   must install BOTH manifests; existing config migration goes through
   PRESSURE_MAKEUP.md and installed register_pressure_makeup.py. The last
   attempted multi-file documentation patch FAILED ATOMICALLY, so its content
   changes did not apply (version string replacement did apply).
2. Add installed upgrade 0.1.1 -> 0.1.2 CI stage (current workflow builds old
   0.1.0 package and upgrades directly to 0.1.2; retain old coverage).
3. Run all tests, fix actual failures, inspect diff, commit/push same branch.
4. Await green Linux CI on final full SHA, read job logs for .deb SHA256 and
   workflow artifact. Update existing PR description and add final comment
   with HEAD, package0.1.2, artifact neiro-nli-0.1.2-deb, exact SHA256 and next
   read-only smoke: nli check hhm THEN nli check pressure_makeup. No live actions.
5. Remove this checkpoint or replace with completed results once finished.

Python: C:/Users/psv76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe
Commands: -B -m unittest discover -s NLI/tests -q; -B NLI/tests/sandbox.py;
node NLI/tests/pressure_makeup_runtime.js; existing HHM tests listed in workflow.
Git metadata is outside writable root; git add/commit/push needs escalated
exec (already user-authorized). gh absent; use GitHub connector tools discovered
via ALL_TOOLS. fetch_commit_workflow_runs requires full40SHA; get jobs/logs and
artifacts from returned run. Do not dump entire logs; filter relevant evidence.
