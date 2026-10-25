# NLP-255-C7F-PRAGMATIC-FILTERED-SYNC — intermediate 2026-10-26

status: PARTIAL — actual UI opt-in and explicit full fallback implemented; subset Apply remains disabled, no production speedup claimed.
start_sha: 916188e2b05eb7d10a08d05d87afdfc42105067f
base_sha: cd511d7d9b8ed588f17a1797aa1f4f189d37462f
branch: feature/nlp-255-c7f-pragmatic-filtered-sync

Approved pragmatic residual risk accepted: attributes/coordinates changing without Handle/Layer change and the interval between final census and commit are not detected. No CAD lock, lease or heavy reread used for freshness.

Implemented: fresh insert_census bridge command/client, session-local full-preview context, fresh census before Apply/write-back, project/binding checks inside SQLite apply, UI opt-in checkbox, visible full fallback question and actual explicit preview/Apply dialog. Default full/#148 remains unchanged. C7c candidate read cannot prove excluded untracked INSERT ownership; no partial flags/provenance are changed to create authority. All applicable new-mode proposals come from normal full read. Production acceleration is not claimed.

New service tests initially passed 10 cases; UI tests exposed missing cancel() in the synchronous controller test double (not production) and after correction all 4 real-dialog UI cases passed. Additional census/transport/moved/deleted/writeback tests now included; final regression pending. Ruff check passes for 8 changed Python files.

next_action: run final focused/UI, single full cad_sync, numeric CAD targets, compileall/Ruff/diff; finalize checkpoint, commit/push and report exact counts/SHA in existing Issue #255. No C7d, main merge or real data changes.
