# Одобренный выпуск HHM 3.2

Каталог предназначен для stable GitHub Release `nli-approved-hhm-3.2`.
Публикация этого выпуска является одобрением компонента для NLI 0.1.9.

Выпуск [опубликован](https://github.com/psv76/Neirolinks/releases/tag/nli-approved-hhm-3.2)
28.09.2026 в 16:05:33 UTC. Этап 9 завершён.

- Runtime commit R: `04f00b3bb44a8b9da83bcf42cfb2ef68b3090630`.
- Manifest commit M и точная цель тега: `0a08062ddcb6d0c8cee7e0c04817fefc32f8f598`.
- Asset: `nli-catalog.json` из этой папки, UTF-8, окончания строк LF.
- SHA256 asset: `99354364db644120867b64aaf120eae7924378341c284601e6ed5e5b9da29aa4`.
- `draft=false`, `prerelease=false`; GitHub должен показывать тот же SHA256 digest.
- Каталог содержит только HHM 3.2 для boiler/gazebo. Пакета NLI в нём нет.

## Выполненные проверки

На точном commit M завершились успешно:

- [Полный HHM3 CI](https://github.com/psv76/Neirolinks/actions/runs/36418674712).
- [Полный NLI CI](https://github.com/psv76/Neirolinks/actions/runs/36418674781).

Локально прошли полный набор HHM3, проверка синтаксиса 28 JS-файлов,
manifest/dependencies и пять тестов manifests 3.1/3.2. Полный NLI локально
на Windows не прошёл из-за отсутствия `os.geteuid`; итог полного набора
подтверждён указанным Linux CI, а не этим локальным запуском.

Каталог собран `NLI/tools/release_catalog.py` с `--commit M`, обоими
`NLI/releases/hhm-*-3.2.json` и `--minimum-nli 0.1.9`, без `--package`.
Окончания строк нормализованы в LF перед расчётом SHA256 и загрузкой.
Коммит сохранения каталога не является целью тега: цель остаётся M.

## Проверка после публикации

Через публичный GitHub API и неизменный `nli.releases.Releases` версии 0.1.9
выполнена проверка только чтением, без обращения к контроллерам:

- Release ID `398411484`: `draft=false`, `prerelease=false`.
- Git ref `refs/tags/nli-approved-hhm-3.2` указывает непосредственно на M.
  Поле API `target_commitish=main` осталось от формы создания выпуска на
  существующем теге; GitHub его не использует для уже существующего тега.
  Сам тег и ссылка Commit на странице выпуска подтверждают точный M.
- Единственный загруженный asset — `nli-catalog.json`, ID `595811786`, 902 байта.
  Два архива исходников GitHub формирует автоматически.
- GitHub digest совпал с SHA256 выше; скачанные через API байты совпали
  с сохранённым каталогом побайтово. Ключа `nli` в каталоге нет.
- Для boiler и gazebo при установленной версии 3.1 вызов `Releases.component`
  вернул `update_available=true`, версию 3.2, minimum_nli 0.1.9 и runtime R.
  Проверены реальные опубликованные manifests и их SHA256, а не подставной
  сетевой ответ. Использовался только объект проверки manifests без движка
  установки; `nli update hhm` не запускался.

Каталог сохранён отдельным commit `1220b5d11e2a2c785be3ec44910d0f5f7f4c455b`.
Новый пакет NLI не публиковался. Production-файлы NLI, его версия и
исторические manifests 3.1 остались неизменными.

## Публикация через GitHub UI при необходимости

1. В Releases выбрать создание нового выпуска и тег `nli-approved-hhm-3.2`
   на точном commit M выше.
2. Прикрепить этот `nli-catalog.json`; не отмечать pre-release.
3. Опубликовать выпуск, проверить commit тега, SHA256 asset и stable-статус.

После публикации пользователь сам выполняет `nli update hhm` на
зарегистрированном контроллере нужной роли. Подготовка выпуска не выполняет
эту команду, SSH, deploy, restart или merge. NLI 0.1.9 не изменён.
