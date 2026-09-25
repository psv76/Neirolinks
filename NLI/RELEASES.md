# Публикация approved releases для NLI 0.1.8

Это maintainer workflow, не инструкция оператору WB. Полевая сторона выполняет
`nli check/update` и `nli self-update`; никаких path/SHA copy-paste в object config.

1. Проверить компонент, выбрать immutable runtime commit, подготовить manifest с
   exact files SHA и повышенной числовой version. Функциональное одобрение release
   принадлежит автору компонента/ПНР; NLI не определяет готовность алгоритмов.
2. После code review/green CI зафиксировать immutable commit самого manifest.
3. Собрать каталог (команда только читает Git blobs и создаёт metadata):

   ```sh
   python3 -B NLI/tools/release_catalog.py --commit <40-char-manifest-commit> \
     --manifest <repo-path-to-approved-manifest> \
     --package NLI/dist/neiro-nli_0.1.8_all.deb --package-version 0.1.8 \
     --minimum-nli 0.1.8 --output nli-catalog.json
   ```

   --manifest можно повторять для разных object/role/component; для release только
   NLI package его можно не указывать. Для component-only release не указывать package.
4. Создать **draft** GitHub Release в psv76/Neirolinks с tag nli-approved-<unique-id>,
   приложить nli-catalog.json, deb с указанным именем и его .sha256. Проверить GitHub
   asset digest SHA256 (API должен предоставлять digest, иначе NLI fails closed).
5. После review явно publish stable release. Только этот шаг разрешает discovery.
   Draft/prerelease не выбираются. Release metadata immutable по соглашению:
   не заменять approved asset/manifest, новый release получает новую version/tag.

Catalog schema=1: repository, approved=true, components[]; каждый entry имеет
component/object/role/version/approved/minimum_nli и manifest {commit,path,sha256}.
Optional nli={version,approved,sha256}; deb asset name neiro-nli_<version>_all.deb.
Поля application readiness в каталоге отсутствуют. Manifest schema 1 сохранён;
verify.controls/runtime_version/health_contract — legacy metadata без install gates.

NLI ограничивает чтение 1000 GitHub releases / 32 approved catalogs; maintainer
консолидирует старые каталоги, если достигнут bound. Failed request/invalid metadata
не обходится fallback на mutable main. Контроллер использует public GitHub API;
private/rate-limited endpoint даст явную transport ошибку.

**Этот PR не публикует approved release и не делает draft #73 deployable.**
Known 3.1 manifests в package нужны для распознавания уже вручную установленных bytes
согласно #74, а не для автоматической установки заблокированного runtime.
