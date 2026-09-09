# Reference implementation — Sprut Configurator v0.2.2

Здесь хранится зафиксированный standalone baseline, прошедший реальное end-to-end применение.

Файлы:

```text
sprut_configurator.py
requirements.txt
setup.bat
run.bat
```

## Запуск на Windows

1. Установить Python 3.11+.
2. Выполнить:

```text
setup.bat
```

3. Запустить:

```text
run.bat
```

Зависимости:

```text
websockets>=15.0,<17
PyYAML>=6.0.2,<7
```

## Почему здесь нет объектовых fixtures

Original v0.2.2 package содержал regression data первого reference объекта. Они сознательно отделены от общей разработки.

Object-specific plan/acceptance snapshot находится в:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/
```

Большой DISCOVER JSON из исходного рабочего пакета не включён в общую папку Configurator, чтобы не смешивать runtime snapshot конкретного объекта с общим механизмом.

## Security

Не добавлять в репозиторий:

```text
Sprut token
cid/session payload
cookies
прочие secrets
```

Reference source рассчитан на локальную вставку WebUI WebSocket frame и хранит session credentials только в RAM.
