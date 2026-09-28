# Одобренный выпуск HHM 3.2

Каталог предназначен для stable GitHub Release `nli-approved-hhm-3.2`.
Публикация этого выпуска является одобрением компонента для NLI 0.1.9.

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

## Публикация через GitHub UI при необходимости

1. В Releases выбрать создание нового выпуска и тег `nli-approved-hhm-3.2`
   на точном commit M выше.
2. Прикрепить этот `nli-catalog.json`; не отмечать pre-release.
3. Опубликовать выпуск, проверить commit тега, SHA256 asset и stable-статус.

После публикации пользователь сам выполняет `nli update hhm` на
зарегистрированном контроллере нужной роли. Подготовка выпуска не выполняет
эту команду, SSH, deploy, restart или merge. NLI 0.1.9 не изменён.
