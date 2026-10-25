# NLP-255-C7C-SCAN-INTEGRATION

status: PARTIAL — staged safety implemented; production filtering disabled.
start_sha: ee1d1e2766b7d3b966b6c85b95a373608b7444c5
base_sha: 18babcb8861adecf74854e6dafdf89450856681a
branch: feature/nlp-255-c7c-scan-integration

Implemented pure census/observation assessment and synthetic tests, plus default fingerprint/fallback/incremental preservation tests. No runtime wiring and no scan speedup implemented. Current protocol has no complete lightweight census producer or fresh revision binding; normal LISP fingerprint still reads heavy data for every INSERT. C5 COM opt-in is unchanged and disabled in protocol.

Moved-off-layer tracked handles require heavy reads, never deletion. Absent handles remain unknown without explicit unfiltered per-handle proof tied to document/read/revision. Any failed/stale/duplicate evidence fails closed. Even internally consistent synthetic evidence is STAGED_ONLY and never creates an authoritative batch or bypasses C6.

Tests in progress: new safety, bridge client, STA bridge, C5 prefilter, C6 completeness, sync service and p0003 reconciliation. Initial pure suite: 51 passed / 1 failed due test calling nonexistent apply method; corrected test to apply_dwg_to_project. Combined run pending; one failure observed, investigate before final report.

next_action: finish regression run, investigate failures against unchanged start if needed, complete compileall/Ruff/diff checks, record tested/final SHA and precise gap, push this branch and report in Issue #255. Do not start C7d.
