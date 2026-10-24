# Подготовка NST 2.4 (пакет диагностики Иволги; выпуск требует отдельного утверждения)

Версия собственного ПО только `X.Y`; [нормативный стандарт](../../EIM/Standards/Software_naming_and_versioning_standard.md). Новые package/component catalogs используют `nst-catalog.json`; исторические `nli-catalog.json` читаются только для immutable component approvals и rollback.

## Package и components

`tools/build_deb.py` создаёт `dist/nst_2.4_all.deb` и SHA256. Проверяются package `nst`, version `2.4`, architecture `all`, отсутствие hooks и записи persistent данных.

`tools/release_catalog.py` готовит catalog из immutable manifest commit и пакета. Пример после принятия соответствующего commit в main:

```sh
python3 -B Systems/NST/tools/release_catalog.py --commit <COMMIT> --package Systems/NST/dist/nst_2.4_all.deb --package-version 2.4 --minimum-nst 2.0 --output nst-catalog.json
```

Maintainer отдельно проверяет и публикует stable `nst-approved-package-2.4` с catalog и `.deb`. Новые component approvals используют `nst-approved-components-*`. `install.py` и `nst self-update` выбирают только canonical NST package releases, никогда `neiro-nli` или исторический `neiro-nst 1.0.0`.

Исторические stable Releases `nst-approved-package-2.0`, `nst-approved-package-2.1` и `nst-approved-package-2.2` сохраняются неизменными. Перед публикацией 2.4 обязательно обновить commit на принятый `main`, собрать пакет и каталог из того же immutable commit, проверить GitHub release assets и SHA256. Обновление 2.4 через штатную установку `.deb` само по себе не вызывает `nst sync` и не меняет HHM.

## Platform

`nst-approved-platform-<X.Y>` должен содержать registry и deployment для каждого active controller. Registry/profile/source, manifests и payload привязаны к immutable commit/SHA256.

```sh
python3 -B Systems/NST/tools/prepare_platform_release.py --commit <MAIN_COMMIT> --version 2.0 --output platform-assets
```

Инструмент проверяет принадлежность source commit истории `origin/main`, capabilities/desired components и все referenced bytes. Создаёт `nst-controller-registry.json`, `nst-deployment-<SERIAL>.json`, `nst-platform-metadata.json` с исходным commit и checksums.

Workflow **Prepare NST platform assets** запускается только вручную, имеет `contents: read` и загружает CI artifact. Проверка опубликованных Releases использует только ephemeral `github.token` текущего Actions run, чтобы не зависеть от anonymous API rate limit; token не сохраняется в assets. Workflow не создаёт tags/Releases и не выполняет deploy. Перед отдельной публикацией maintainer проверяет completeness и approved component provenance; `verify_approved_components.py` проверяет snapshot против опубликованных Releases.

ABF62SL разрешает `hhm: stable` и `pressure_makeup: stable`; опубликованный `nst-approved-components-pressure-makeup-1.0` зафиксирован в approved snapshot. Подготовка полного platform release теперь должна разрешать оба компонента, но сама публикация platform Release остаётся отдельным maintainer action.

Merge PR только обновляет код/проверки. Для установки на объект нужны отдельные package и platform Releases и явная команда оператора. Immutable historical Releases не удаляются и не переписываются.

## NST 2.4: ограничение обновления профиля Иволги

Изменены только данные профиля диагностики и регистрация ABF62SL в пакете; команда `nst diagnostics collect hhm --since 6h` остаётся read-only. Пакет не перезапускает `wb-rules`.

Обязательная проверка: отсутствует ли старый `/mnt/data/etc/neirolinks/nst/controller-registry.json`; он имеет приоритет над пакетным реестром. Нельзя удалять или заменять его вручную без отдельной проверки. Обновление package отдельно от согласованного immutable Platform release не переводит установленный deployment в exact. Не выполнять `nst sync`, пока у ABF62SL сохраняются расхождения трёх объектовых JS и нет отдельного плана безопасной установки.

После принятия PR в main и успешной проверки package+platform assets maintainer отдельно публикует `nst-approved-package-2.4` и следующий `nst-approved-platform-*`. Только после этого отдельно согласовать `nst self-update` или установку reviewed пакета на Иволге. Не менять исторические immutable releases.
