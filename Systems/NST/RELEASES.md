# Публикация NST 2.0

Версия собственного ПО только `X.Y`; [нормативный стандарт](../../EIM/Standards/Software_naming_and_versioning_standard.md). Новые package/component catalogs используют `nst-catalog.json`; исторические `nli-catalog.json` читаются только для immutable component approvals и rollback.

## Package и components

`tools/build_deb.py` создаёт `dist/nst_2.0_all.deb` и SHA256. Проверяются package `nst`, version `2.0`, architecture `all`, отсутствие hooks и записи persistent данных.

`tools/release_catalog.py` готовит catalog из immutable manifest commit и пакета. Пример после принятия соответствующего commit в main:

```sh
python3 -B Systems/NST/tools/release_catalog.py --commit <COMMIT> --package Systems/NST/dist/nst_2.0_all.deb --package-version 2.0 --minimum-nst 2.0 --output nst-catalog.json
```

Maintainer отдельно проверяет и публикует stable `nst-approved-package-2.0` с catalog и `.deb`. Новые component approvals используют `nst-approved-components-*`. `install.py` и `nst self-update` выбирают только canonical NST package releases, никогда `neiro-nli` или исторический `neiro-nst 1.0.0`.

## Platform

`nst-approved-platform-<X.Y>` должен содержать registry и deployment для каждого active controller. Registry/profile/source, manifests и payload привязаны к immutable commit/SHA256.

```sh
python3 -B Systems/NST/tools/prepare_platform_release.py --commit <MAIN_COMMIT> --version 2.0 --output platform-assets
```

Инструмент проверяет принадлежность source commit истории `origin/main`, capabilities/desired components и все referenced bytes. Создаёт `nst-controller-registry.json`, `nst-deployment-<SERIAL>.json`, `nst-platform-metadata.json` с исходным commit и checksums.

Workflow **Prepare NST platform assets** запускается только вручную, имеет `contents: read` и загружает CI artifact. Он не создаёт tags/Releases и не выполняет deploy. Перед отдельной публикацией maintainer проверяет completeness и approved component provenance; `verify_approved_components.py` проверяет snapshot против опубликованных Releases.

ABF62SL разрешает `hhm: stable` и `pressure_makeup: stable`; опубликованный `nst-approved-components-pressure-makeup-1.0` зафиксирован в approved snapshot. Подготовка полного platform release теперь должна разрешать оба компонента, но сама публикация platform Release остаётся отдельным maintainer action.

Merge PR только обновляет код/проверки. Для установки на объект нужны отдельные package и platform Releases и явная команда оператора. Immutable historical Releases не удаляются и не переписываются.
