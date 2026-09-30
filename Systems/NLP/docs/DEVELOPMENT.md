# Контур разработки NL Project 2.0

Runtime зафиксирован в runtime.lock.json, зависимости — в requirements.lock.

    & .\tools\bootstrap.ps1
    & .\tools\check.ps1
    & .\tools\format-check.ps1
    & .\tools\test.ps1
    & .\tools\run.ps1
    & .\tools\build.ps1

Все wrappers используют только .venv\Scripts\python.exe, созданный из CPython
3.13.14 x64 внутри рабочего каталога версии 2.0. Запуск с -AutoCloseMilliseconds
предназначен для smoke-проверки развёртывания.
