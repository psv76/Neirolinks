# Публикация NST 2.2 (пакет; Platform 2.0 остаётся без изменений)

Версия собственного ПО только `X.Y`; [нормативный стандарт](../../EIM/Standards/Software_naming_and_versioning_standard.md). Новые package/component catalogs используют `nst-catalog.json`; исторические `nli-catalog.json` читаются только для immutable component approvals и rollback.

## Package и components

`tools/build_deb.py` создаёт `dist/nst_2.2_all.deb` и SHA256. Проверяются package `nst`, version `2.2`, architecture `all`, отсутствие hooks и записи persistent данных.

`tools/release_catalog.py` готовит catalog из immutable manifest commit и пакета. Пример после принятия соответствующего commit в main:

```sh
python3 -B Systems/NST/tools/release_catalog.py --commit <COMMIT> --package Systems/NST/dist/nst_2.2_all.deb --package-version 2.2 --minimum-nst 2.0 --output nst-catalog.json
```

Maintainer отдельно проверяет и публикует stable `nst-approved-package-2.2` с catalog и `.deb`. Новые component approvals используют `nst-approved-components-*`. `install.py` и `nst self-update` выбирают только canonical NST package releases, никогда `neiro-nli` или исторический `neiro-nst 1.0.0`.

Исторические stable Releases `nst-approved-package-2.0` и `nst-approved-package-2.1` сохраняются неизменными. Перед публикацией 2.2 обязательно обновить commit на принятый `main`, собрать пакет и каталог из того же immutable commit, проверить GitHub release assets и SHA256. Обновление 2.2 через штатную установку `.deb` само по себе не вызывает `nst sync` и не меняет HHM.

## Platform

`nst-approved-platform-<X.Y>` должен содержать registry и deployment для каждого active controller. Registry/profile/source, manifests и payload привязаны к immutable commit/SHA256.

```sh
python3 -B Systems/NST/tools/prepare_platform_release.py --commit <MAIN_COMMIT> --version 2.0 --output platform-assets
```

Инструмент проверяет принадлежность source commit истории `origin/main`, capabilities/desired components и все referenced bytes. Создаёт `nst-controller-registry.json`, `nst-deployment-<SERIAL>.json`, `nst-platform-metadata.json` с исходным commit и checksums.

Workflow **Prepare NST platform assets** запускается только вручную, имеет `contents: read` и загружает CI artifact. Проверка опубликованных Releases использует только ephemeral `github.token` текущего Actions run, чтобы не зависеть от anonymous API rate limit; token не сохраняется в assets. Workflow не создаёт tags/Releases и не выполняет deploy. Перед отдельной публикацией maintainer проверяет completeness и approved component provenance; `verify_approved_components.py` проверяет snapshot против опубликованных Releases.

ABF62SL разрешает `hhm: stable` и `pressure_makeup: stable`; опубликованный `nst-approved-components-pressure-makeup-1.0` зафиксирован в approved snapshot. Подготовка полного platform release теперь должна разрешать оба компонента, но сама публикация platform Release остаётся отдельным maintainer action.

Merge PR только обновляет код/проверки. Для установки на объект нужны отдельные package и platform Releases и явная команда оператора. Immutable historical Releases не удаляются и не переписываются.
