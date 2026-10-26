# NL Project — реестр незавершённых работ и release coverage

**Входной маршрут:** [Issue #145](https://github.com/psv76/Neirolinks/issues/145).
**Source of truth runtime:** `psv76/Neirolinks:main/Systems/NLP`.
**Документация проектировщика:** [psv76/NEIROLINKS-TechDocs](https://github.com/psv76/NEIROLINKS-TechDocs) — отдельный источник, проверять его Issues/PR/ветки тоже.
**Базовая версия на 26.10.2026:** установлен NL Project **3.1**, commit `de9b0bb1f75d3d64e5f729399b566ab96ae1a3bb`; ускоренное сканирование оставлено на 3.2.

> **Владелец реестра — ChatGPT-координатор, НЕ Codex.** Координатор проводит GitHub inventory, фиксирует решения, готовит задачи и release coverage. Codex читает готовое узкое задание, пишет код, выполняет тесты и отчитывается. Codex **не** выполняет поиск всех веток, восстановление общего контекста и систематизацию backlog.
>
> **Регистр = навигация и реестр обязательств, НЕ доказательство принятия кода.**
> Дата среза ниже 2026-10-26; перечни быстро устаревают. Перед **каждым** новым чатом, постановкой задачи, интеграцией и релизом заново получать весь GitHub inventory, а не доверять только этому снимку.

## Q07 working patch — согласованный scope 2026-10-26

**User decision 2026-10-26:** после визуальной проверки второго варианта Q07 разрешено
использовать его в установленной NL Project 3.1, исправив только дублированную
иконку предупреждения «⚠ нет длины». Это **scoped working patch**, а не
полный релиз всей очереди #286 и не приёмка остальных направлений.

| Пункт | Issue / кандидаты | Scope Q07 patch | Статус после начала интеграции |
| --- | --- | --- | --- |
| Q07 физическое дерево «Линий», удобный источник и состав длины | #216, #286, PR #287; `work/nlp-286-q07-v2-preview` | **ВКЛЮЧАЕТСЯ** в рабочий patch 3.1 | User-approved working candidate; Windows copied DB GUI preview; 147 tests; production install требует отдельного verified checkpoint |
| «Трассы» B — UI + принятый документ | #216, #286, PR #219/#220/#221 | **НЕ ВКЛЮЧЕНО** | Остаётся отдельной принятой работой для 3.1; перенос в 3.2 не согласован |
| Ethernet: 18 новых 8xx линий и Apply blockers | #149, #286, PR #190 | **НЕ ВКЛЮЧЕНО** | Дефект открыт; реальный DWG и production Apply в scope патча Q07 не затрагивать |
| C7c/e/f ускоренное filtered сканирование | #255, PR #277/#278/#281 | **НЕ ВКЛЮЧЕНО** | Отдельно согласован перенос на 3.2; в 3.1 полный скан |

Установочный checkpoint и фактический runtime SHA должны фиксироваться в #286
после установки. Пока этого нет, **не писать SHIPPED_VERIFIED**.
Согласование Q07 не означает принятия release completeness по #145:
остальные принятые ветки/PR сохраняют открытые статусы без скрытого переноса.

---

## Обязательный алгоритм полной инвентаризации

1. Считать [#145](https://github.com/psv76/Neirolinks/issues/145), текущие открытые Issues и **все открытые NLP PR** (включая Draft). Прочитать принятые решения и acceptance отдельно от статуса PR; пользовательский выбор, зафиксированный в docs-only PR, обязателен и без production-кода.
2. Получить **все remote branches** для репозитория, не только ветки, связанные с открытым PR. Классифицировать `fix/*`, `feat/*`, `feature/*`, `system/nlp/*`, `integration/*`, `release/*`, **`docs/*`**, **`spike/*`**, `audit/*` и нетипичные ветки. Отдельно проверять orphan branches: может не существовать Issue/PR, но уже принятое требование в коммите/документе.
3. Проверить зависимые и контекстные репозитории, в том числе **TechDocs** (`main`, Issues, PR и все branches с CAD/обучением). Сопоставить норматив с машинным контрактом и фактическим кодом.
4. Для каждого предметного обещания записать: **направление / Issue / PR + head branch + base / тип (runtime, UI, docs, tests, spike, audit) / принятое решение / состояние в релизном main / статус интеграции / target release / блокер или явное согласованное исключение**. Статусы: `SHIPPED_VERIFIED`, `PARTIAL`, `DRAFT_UNMERGED`, `DOC_ONLY_ACCEPTED`, `SPIKE_ACCEPTED`, `DEFERRED_APPROVED`, `UNKNOWN_UNTRIAGED`, `HISTORICAL_VERIFIED`. **Unknown нельзя считать Done.**
5. Каждая принятая UX/предметная идея создаёт persistent item, даже если работа пока только в Issue, Figma, docs-only PR или прототипе без merge. Запись обновляется немедленно после решения пользователя; новая ветка не должна начинать с «вспомнить, что обсуждали».
6. Перед выпуском составить **release coverage matrix**: все `SHIPPED_VERIFIED` с фактическим путём/тестом/экраном в кандидате; все остальные с `НЕ ВКЛЮЧЕНО`, причиной и одобренным переносом. Проверять runtime присутствие, а не git-parent/CI-green/наличие PR. Когда принятое UI отсутствует — **доложить до выпуска и получить решение**. Пока хоть одна принятая вещь не классифицирована, **release completeness gate BLOCKED**.
7. После merge/непринятия: обновить реестр, Issue #145, дочернюю Issue, release note. Отложенный проект не теряет ветку/PR и не переносится в следующий релиз автоматически без отдельного решения.

## Инвентаризационные команды / API

- GitHub open PR: `repo:psv76/Neirolinks is:pr is:open`; query не ограничивать словом `codex` или номером последнего Issue. Для GitHub CLI: `gh pr list -R psv76/Neirolinks --state open --limit 300 --json number,title,headRefName,baseRefName,isDraft,url`.
- Git refs: `git fetch origin --prune` и `git branch -r` (если нет локального git — GitHub branch search с пагинацией **до конца cursor**). Для подтверждения: `git merge-base`, `git diff --stat`, `git log --oneline`, `git branch --contains` и inspection реального source/GUI.
- Open Issues: `repo:psv76/Neirolinks is:issue is:open`, затем по product scope и без привязки к последнему активному PR. Отдельно `repo:psv76/NEIROLINKS-TechDocs`: branches, PR, open Issues #2/#3 и будущие.
- **Нельзя** считать `git merge-base --is-ancestor` достаточным доказательством готовности UI; техническая ветка может стать предком `main`, а user-facing модуль так и не оказаться установлен.

## Срез открытых NLP PR (26.10.2026, не заменяет live GitHub search)

Таблица группирует реальную открытым PR историю. **Список PR полон для обнаруженных открытых NLP PR на дату среза**, но ветки без PR и исторические ветки проверяются отдельно. Следующий читатель обязан актуализировать.

| Поток и принятый смысл | Issue / PR | Git head / документы | В релизе 3.1 и что делать |
|---|---|---|---|
| Q07 физическое дерево «Линий» | [#216](https://github.com/psv76/Neirolinks/issues/216), [PR #217](https://github.com/psv76/Neirolinks/pull/217) | `fix/nlp-216-lines-physical-tree`; `presentation/physical_tree.py` | **НЕ ВКЛЮЧЕНО**: в установленном main модуля нет. Принятое UI, интегрировать/принимать в 3.1 patch |
| UX «Трассы» B, согласован 20.10.2026 | [#216](https://github.com/psv76/Neirolinks/issues/216), [PR #219](https://github.com/psv76/Neirolinks/pull/219) | `spike/nlp-216-routes-qt-ab`, Qt A/B screenshots | **SPIKE_ACCEPTED** вариант B; не production код |
| **Норматив выбранного UI B** | [PR #220](https://github.com/psv76/Neirolinks/pull/220) | **`docs/nlp-216-routes-b-accepted`**, docs/product/14 | **DOC_ONLY_ACCEPTED**, не терять; нужно перенести норматив при выпуске |
| Production read-only вкладка «Трассы» B | [PR #221](https://github.com/psv76/Neirolinks/pull/221) | `system/nlp/216-routes-b-production` / `RoutesWorkspace` | **НЕ ВКЛЮЧЕНО**: в main только переходная кнопка «Открыть трассы и трубы» |
| Физические идентичности/назначения труб | [PR #222](https://github.com/psv76/Neirolinks/pull/222), [#224](https://github.com/psv76/Neirolinks/pull/224), [#228](https://github.com/psv76/Neirolinks/pull/228), [#229](https://github.com/psv76/Neirolinks/pull/229) | `system/nlp/216-physical-bounds-plan`, `system/nlp/216-atomic-conduit-command`, `system/nlp/216-transactional-route-mirror`, `audit/nlp-216-safety` | DRAFT/stacked; не включать без проверки зависимостей |
| Спецификация и геометрия длин | [PR #230](https://github.com/psv76/Neirolinks/pull/230), [#231](https://github.com/psv76/Neirolinks/pull/231) | `fix/nlp-216-physical-conduit-spec`, `fix/nlp-216-length-q04q05q08` | Статус конкретных исправлений в интеграции проверить по diff и тестам; не считать весь UI #216 готовым |
| Дизайнерская документация / проектировщик | [PR #233](https://github.com/psv76/Neirolinks/pull/233), [#232](https://github.com/psv76/Neirolinks/issues/232) | **`docs/232-nlp3-cad-designer-guide`**, также `psv76/NEIROLINKS-TechDocs` | DOC/DRAFT; учитывать принятые инструкции отдельно от runtime |
| DALI/физические коробки/транзит D1–D23 | [#237](https://github.com/psv76/Neirolinks/issues/237), [PR #238–#263](https://github.com/psv76/Neirolinks/pulls?q=is%3Apr+is%3Aopen+237) | `feat/nlp-237-*`, `fix/nlp-237-*`, `integration/nlp-237-d23-stagec-d22-candidate`, `chore/nlp-237-d23-integration-evidence` | Stacked draft / integration: часть оказалась предком релиза; проверить каждую пользовательскую возможность и safety gate, **не** объявлять весь стек введённым |
| Отдельный универсальный кабельный вывод шины | [PR #227](https://github.com/psv76/Neirolinks/pull/227), [#225](https://github.com/psv76/Neirolinks/issues/225) | `system/nlp/225-cable-outlet-bus` | Требует проверки machine/runtime и валидатора на фактическом DWG |
| CAD слой/AV/HVAC/DALI 3.1 | [#255](https://github.com/psv76/Neirolinks/issues/255), [PR #265–#269](https://github.com/psv76/Neirolinks/pulls?q=is%3Apr+255), [#272](https://github.com/psv76/Neirolinks/pull/272), [#273](https://github.com/psv76/Neirolinks/pull/273), [#274](https://github.com/psv76/Neirolinks/pull/274) | `feature/nlp-255-c1-*`…`feature/nlp-255-c7b-*` | Принятый numeric contract включён через [merged PR #283](https://github.com/psv76/Neirolinks/pull/283); не путать open stacked PR с невыпуском |
| Быстрое сканирование — **отложено** | [#255](https://github.com/psv76/Neirolinks/issues/255), [PR #277](https://github.com/psv76/Neirolinks/pull/277), [#278](https://github.com/psv76/Neirolinks/pull/278), [#281](https://github.com/psv76/Neirolinks/pull/281) | `feature/nlp-255-c7c-*`, `feature/nlp-255-c7e-*`, `feature/nlp-255-c7f-*` | **DEFERRED_APPROVED 3.2**; не включать UI switch/unsafe filtered Apply в 3.1 |
| Документирование коротких Codex сессий | [PR #264](https://github.com/psv76/Neirolinks/pull/264) | **`docs/nlp-codex-session-standard`** | DOC/DRAFT; при следующих Codex сессиях не терять |
| Старый 3.1 RC кандидат | [PR #282](https://github.com/psv76/Neirolinks/pull/282) | `release/nlp-3-1-working-rc` | **HISTORICAL CANDIDATE**: вместо него реально установлен [PR #283](https://github.com/psv76/Neirolinks/pull/283); не повторять merge |
| Синхронизация/ошибки на Богдановиче | [#149](https://github.com/psv76/Neirolinks/issues/149), [PR #190](https://github.com/psv76/Neirolinks/pull/190) | `fix/nlp-149-sync-apply-diagnostics`; множество `system/nlp/149-*` | #149 OPEN; проверять конкретные defects и точный effective commit, не считать всю приемку закрытой |
| MOUNT_WAY «В брусе» | [PR #131](https://github.com/psv76/Neirolinks/pull/131) | `system/nlp/130-mount-way-timber-implementation` и родственные ветки | Отдельный migration/release check; статус в 3.1 уточнять |

### DALI/транзит — явный перечень открытых дочерних PR, чтобы не потерять стек

`#238, #239, #240, #241, #242, #243, #244, #245, #246, #247, #248, #249, #250, #251, #252, #253, #254, #256, #257, #258, #259, #260, #261, #262, #263`. Каждый содержит самостоятельные ограничения, базу и checkpoint; их нельзя заменять резюме «D23 готов».

### #255 — явный перечень открытых PR и сопутствующих doc-веток

`#264, #265, #266, #267, #268, #269, #272, #273, #274, #277, #278, #281, #282`. Итоговый рабочий релиз через [PR #283](https://github.com/psv76/Neirolinks/pull/283); оставшиеся draft — контекст или отложенный backlog, не повторная установка.

### Дополнительные ветки, которые нельзя игнорировать только из-за отсутствия PR

- **Docs:** `docs/nlp-235-track-dali-transit-architecture`, `docs/nlp-216-routes-b-accepted`, `docs/232-nlp3-cad-designer-guide`, `docs/nlp-codex-session-standard`, `system/nlp/124-doc-status-refresh`; плюс все найденные в TechDocs. Классифицировать `MERGED / ACCEPTED DOC ONLY / DRAFT / HISTORICAL` и проверять фактический норматив в `main`.
- **UI/feature:** `spike/nlp-216-routes-qt-ab`, `fix/nlp-216-lines-physical-tree`, `system/nlp/216-routes-b-production`, `feat/nlp-216-geometry-length-policy`. Даже `spike` может хранить принятое решение.
- **Repair/release:** `fix/nlp-134-selective-endpoints`, `fix/nlp-140-room-canonicalization`, `fix/nlp-142-working-cable-journal`, `fix/nlp-149-sync-apply-diagnostics`, `system/nlp/149-*`, `release/nlp31-main-integration`, `release/nlp-3-1-working-rc`. Проверять статус, не устанавливать ветки напрямую.
- **TechDocs:** отдельные repository Issues/PR, contract and designer materials. Требуется точная ссылка на документ и SHA при принятии или переносе норматива.

## Release coverage, обязательная форма перед выпуском

| Принятое требование | Issue / docs PR / code PR | Файл/экран в точном release SHA | Проверено | Решение пользователя при отсутствии |
|---|---|---|---|---|
| Дерево «Линий» | #216/#217 | **Отсутствует** в 3.1 `main` | NO | **Нет согласованного исключения** — 3.1 patch |
| «Трассы» B | #219/#220/#221 | **Отсутствует** в 3.1 `main` | NO | **Нет согласованного исключения** — 3.1 patch |
| Num 100..900 / HVAC / AV | #255/PR #283 | Проверенный runtime 3.1 | YES | Не требуется |
| Ускоренный AutoCAD early subset Apply | #255/C7c-e-f | Нет в 3.1 | N/A | **Явно согласован перенос в 3.2** |

**Главный практический принцип:** ни один забытый draft, docs-only PR, прототип или принятая пользовательская функция не должны исчезать из следующего чата и не должны быть молча исключены при релизе.
