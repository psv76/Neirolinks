# NST — NEIROLINKS Service Tool

NST — общая сервисная система NEIROLINKS для контроллеров Wiren Board.

## Статус

На момент этой фиксации:

- принятый production baseline: **NLI 0.1.9**;
- approved Release baseline: `nli-approved-0.1.9`;
- immutable commit baseline: `df484b8bf22835001d69ddb2dd18e3eafd3792b0`;
- NST 1.0 развивается как эволюция NLI 0.1.9;
- общая задача: GitHub Issue #85;
- текущая cumulative development-ветка: `issue-93-nst-ivolga-pilot`;
- текущий cumulative PR: #105;
- #105 остаётся Draft и не является approved Release;
- live-пилот NST 1.0 на Иволге пока не выполнен.

Наличие более нового кода в development-ветке не делает его production baseline.

## Назначение NST

NST должен обеспечивать:

- hardware identity контроллера;
- controller registry;
- approved desired deployment;
- `status / check / sync`;
- backup / rollback / recovery;
- diagnostics bundle;
- firmware wrapper;
- cleanup;
- self-update.

NST не является runtime-зависимостью инженерной автоматики и не управляет отоплением, освещением или другими прикладными функциями как automation engine.

## Миграция NLI → NST

NST 1.0 сохраняет проверенный transaction engine NLI 0.1.9.

В текущей development-реализации:

- пакет переименован в `neiro-nst 1.0.0`;
- основной CLI: `nst`;
- временный compatibility CLI: `nli`;
- внутренний Python package пока остаётся `nli`;
- persistent paths NLI намеренно сохраняются, чтобы не ломать backup/rollback/pending/audit history.

Это migration-совместимость, а не признак того, что NLI остаётся отдельной новой системой.

## Что уже разработано в NST 1.0 branch stack

Цепочка development PR:

- #98 — controller identity, registry и lifecycle;
- #99 — approved deployment manifest;
- #100 — миграция NLI 0.1.9 → NST;
- #101 — status / check / sync;
- #102 — diagnostics;
- #103 — cleanup;
- #104 — firmware / self-update;
- #105 — пилот 05 31 Иволга / ABF62SL.

Эта цепочка исторически построена stacked branches и должна быть свернута в одну понятную development-ветку от актуального `main`.

До завершения consolidation ни один отдельный branch из этой цепочки не считается канонической production-версией NST.

## Проверенные текущие блокеры принятия NST 1.0

### 1. Object files

Текущий `nst sync` умеет сравнивать object files, но намеренно прекращает mutation, если object payload отличается:

```text
Object payload changes require reviewed object-file transaction support
```

То есть полный desired-state sync объекта ещё не реализован.

### 2. Deployment ABF62SL

Текущий generated deployment для Иволги:

- содержит HHM 3.3;
- имеет пустой `object_files`;
- использует default diagnostics profile.

При этом controller profile ABF62SL уже содержит четыре object files и специализированный Ivolga diagnostics profile.

Следовательно generated deployment и controller profile сейчас не синхронизированы.

### 3. Approved components

Текущий development catalog знает approved HHM 3.2 и 3.3.

При этом в репозитории уже существуют более новые approved Releases HHM 3.4 и 3.5.

Это должно быть нормализовано до публикации NST platform Release.

### 4. Pressure makeup

Controller profile ABF62SL заявляет capability `pressure_makeup`, но в новом approved component catalog этот компонент пока не опубликован как approved desired component.

Нельзя молча подменять его object file или придумывать release metadata.

### 5. Platform Release и live pilot

NST 1.0 platform Release для ABF62SL не опубликован.

Read-only pilot на live-контроллере ещё не выполнен.

До этого NST 1.0 не считается принятой production-системой.

## Источники истины

Для принятой версии NST:

1. `main/Systems/NST/`;
2. approved GitHub Release;
3. immutable tag/commit;
4. release assets/checksums.

Для незавершённой разработки:

- конкретный Issue;
- одна явно указанная development-ветка;
- один PR в `main`.

После consolidation stacked PR #98–#105 должны стать историей разработки, а не навигационным механизмом.

## Целевая development-модель

```text
main/Systems/NST/
        ↓
system/nst/<issue>-<topic>
        ↓
development
        ↓
PR → main
        ↓
merge
        ↓
конкретный commit main
        ↓
tag + approved Release
```

## Важное правило

NST не должен искать production payload в случайной рабочей ветке.

Production deployment должен разрешаться только через approved immutable Releases/manifests с точными commit и SHA256.
