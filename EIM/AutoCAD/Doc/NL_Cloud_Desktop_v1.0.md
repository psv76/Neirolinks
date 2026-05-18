# 1️⃣ Структура проекта на диске

Минимально и строго:

```JSON
/Проект/
   /ЭОМ/
       working.dwg
       working.dxf        ← временный экспорт
       /_nlcloud/
           project_meta.json
           /versions/
               /v01/
               /v02/
               /v08/
```

Важно:

- working.dwg — всегда один

- working.dxf — перезаписывается

- версии неизменяемые

- `_nlcloud` — служебная зона

---

# 2️⃣ Структура ядра (модули Desktop)

```JSON
core/
    project_manager.py
    section_manager.py
    release_manager.py
    snapshot_manager.py
    state_manager.py

modules/
    dxf_parser.py
    journal_generator.py
    spec_generator.py
    estimate_generator.py
    pdf_packager.py

ui/
    main_window.py
```

---

# 3️⃣ Логика работы ядра

## ProjectManager

- открыть проект

- создать проект

- загрузить meta

- сохранить meta

---

## SectionManager

- проверить статус (draft / released)

- начать новую версию

- удалить релиз

---

## ReleaseManager

- сформировать PDF пакет

- собрать артефакты

- вызвать snapshot_manager

- обновить meta

---

## SnapshotManager

- создать папку версии

- скопировать dxf

- сохранить snapshot.json

- зафиксировать hash

---

# 4️⃣ Реальный жизненный цикл в Desktop

## 🔹 Открытие проекта

Система:

- ищет `_nlcloud/project_meta.json`

- если нет → создаёт

- определяет:

    - current_version

    - next_version

    - статус

UI показывает:

```JSON
Проект: ПСВ.05.28
Раздел: ЭОМ
Статус: Draft
Текущая версия: 8
Следующая версия: 9
```

---

## 🔹 Работа над проектом

Автор:

- работает в AutoCAD

- экспортирует в DXF

- нажимает "Сканировать"

- генерирует журнал / спецификацию

- повторяет сколько нужно

Система ничего не фиксирует.

Это Draft.

---

## 🔹 Нажатие "Release"

ReleaseManager делает:

1. Проверяет существование working.dxf

2. Формирует PDF пакет

3. Создаёт `/versions/v08/`

4. Копирует:

    - dxf_snapshot.dxf

    - journal.xlsx

    - spec.xlsx

    - estimate.xlsx (если есть)

    - pdf_package.pdf

1. Создаёт snapshot.json

2. Обновляет project_meta.json:

    - current_version = 8

    - next_version = 9

    - status = released

---

## 🔹 После Release

UI показывает:

```JSON
Статус: Released
Текущая версия: 8
```

---

## 🔹 Начать новую версию

Кнопка "Start New Version":

1. Проверяет статус = released

2. Переводит статус → draft

3. Ничего не копирует

4. Просто сообщает:

```JSON
Работа над версией 9 начата.
```

Автор продолжает работать в working.dwg.

---

## 🔹 Удаление релиза

Кнопка "Delete Release":

1. Удаляет папку `/versions/v08/`

2. Удаляет запись из meta

3. Возвращает status = draft

4. next_version откатывается

---

# 5️⃣ UI — минимальный экран

Главное окно:

```JSON
---------------------------------------
Проект: ПСВ.05.28
Раздел: ЭОМ
Автор: Иванов И.И.

Статус: Draft
Текущая версия: 8
Следующая версия: 9

[Сканировать]
[Сформировать журнал]
[Сформировать спецификацию]
[Сформировать PDF пакет]
---------------------------------------
[Release]
[Start New Version]
[Delete Release]
---------------------------------------
Лог:
...
```

Никакой магии.
Только управление состоянием.

---

# 6️⃣ Что уже готово для будущего SaaS

- Version — объект

- Snapshot — объект

- Release — событие

- Role-based модель уже заложена

- Meta хранится структурировано

- Hash позволяет проверять целостность

Когда пойдём в онлайн:

- project_meta.json → таблица Projects

- snapshot.json → таблица Versions

- files → S3 storage

Архитектура уже совместима.

---

# 7️⃣ Инструкция эксплуатации (для тебя)

## Как работать:

1. Открыл проект

2. Работаешь в AutoCAD

3. Экспорт в DXF

4. Сканируешь сколько нужно

5. Когда готов → Release

6. Проверил PDF

7. Если всё ок → отправил клиенту

8. Если нужно продолжать → Start New Version

Всё.

---

# 8️⃣ Что мы НЕ делаем в v1

- Не трогаем юридические процессы

- Не трогаем финансы

- Не строим облако

- Не делаем multi-user

- Не делаем блокировку версий

Это Desktop v1.

Файлов working.dwl или working.dwl2 не было

## Открыл dwg вручную - то же самое:

## Команда: _DWGNAME
DWGNAME = "working.dwg" (только чтение)

Поэтому переходим к плану "импорт в открытый dwg".

Текущая файловая система NL Cloude

```JSON
C:\NL
    main.py

C:\NL\assets
    help.pdf
    logo.ico
    logo.png

C:\NL\debug
    check_cable_type.py

C:\NL\modules
    __init__.py - пустой
    dwg_importer.py
    dxf_parser.py
    journal_generator.py
    spec_generator.py
    estimate_generator.py - еще не создан
    pdf_packager.py - еще не создан

C:\NL\ui
    __init__.py
    main_window.py

C:\NL\Шаблоны
    Кабельный журнал.xlsx
    Спецификация.xlsx

И сейчас еще появился
C:\NL\.venv - там много разных папок и файлов


Следующий каталог еще не создан (заготовка на развитие):

core/ 
    project_manager.py
    section_manager.py
    release_manager.py
    snapshot_manager.py
    state_manager.py

```



