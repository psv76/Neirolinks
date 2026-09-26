# HHM 3.1 — результаты проверки PR #73

Область: Issue #68 cold-start и сохранение fix #75 c35ddbd; база df484b8 после NLI #74/#79. Только offline simulation/source review. Версия 3.1, контракт m1w2-health-v1.

## HHM regression suite

| Suite (tests/) | Результат |
|---|---:|
| run.js | 67 groups PASS |
| sensor-health-regressions.js | 20 PASS |
| m1w2-recovery-regressions.js | 16 PASS / 0 FAIL |
| cold-start-proof-regressions.js | 7 PASS / 0 FAIL |
| field-startup-regressions.js | 4 historical passive-cache/receiver groups PASS |
| partial-ready-regressions.js | 10 PASS |
| persistent-storage-regressions.js | PASS |
| manifest.js --check | Проверка всех release hashes/dependencies в HHM CI |

FAIL-before/PASS-after:

- #75: `m1w2-recovery-regressions.js --baseline` загружает Wire/Runtime из 14354bcf1e0033c51f02f0b242bea8aa7fa29e4e: **4 PASS / 12 FAIL**; fixed **16 PASS**.
- Cold-start: `cold-start-proof-regressions.js --baseline` загружает Wire/Runtime из c35ddbdb99874111699d29116b03381f12daef08: **4 PASS / 3 FAIL**; fixed **7 PASS**. Ранее падавшие группы: healthy retained unchanged admission, штатное округление температуры, свежий proof нового boot/после clock rollback. Старые negative cases остаются PASS.

Новая suite использует настоящие 500/620/624/600 и отдельную hardware model. Проверяет 20 mapped sensors, оба restart ordering, unchanged retained state без numeric republish, non-retained correlated RPC, dead retained-only, неверные/запаздывающие replies, OK=0, #error, range/sentinel/missing controls, несовпадение local state и unsupported runtime metadata. После admission новые RPC не генерируются. Точные source pins и границы доказательства — FIELD_STARTUP_2026-09-25.md.

## NLI 0.1.9 и artifacts

NLI core и его installation-only policy сохранены из актуальной базы. `STARTUP_VALIDATION`, `NORMAL`, health controls и frames не являются install/rollback gate. Historical 14354bc fixture в package migration CI оставлен для проверки прежней установки, а не как target нового релиза. Recognition manifests вынесены в NLI/known с прежними hashes; builder упаковывает их независимо от новых NLI/releases. Проверка пакета против базы df484b8: **byte-identical**, SHA256 `11646db0e1c4366d1be32e576e087e2334bf93d864effd49485e599ba2e2de7c`. Migration suite 15 PASS; package regression дополнительно проверяет SHA упакованных recognition manifests.

`NLI/tests/test_hhm31_release.py` проверяет воспроизводимость обоих manifests из одного immutable runtime commit, exact Git blobs/SHA, совпадение deployed source с HEAD, version 3.1 и исключение 507. Manifests ссылаются на runtime commit, предшествующий отдельному artifact commit; это исключает циклический self-pin.

Локальный NLI sandbox обеих ролей: PASS (fake WB). Полный unittest на Windows: 168 tests, 35 platform skips, одна Linux-only import error `os.geteuid` в bootstrap; production code ради Windows не менялся. Окончательные full unittest, package build 0.1.9, Debian install/upgrade/reinstall/FIT и HHM выполняются штатным Linux NLI workflow. Точные итоговые CI run links/result привязываются к финальному HEAD в PR #73, а не к предыдущему релизу.

## Граница приёмки

Не выполнялись live SSH/deploy/restart, OT/physical commands или merge PR. Реально установленная serial capability и bus timing требуют controlled retry по INSTALL.md. Никакие offline tests не доказывают физическую циркуляцию, положение клапанов или гидравлическую приёмку #20. Receiver не изменялся: его историческое live наблюдение нельзя объявить исправленным без raw evidence; оба modeled restart ordering корректны.
