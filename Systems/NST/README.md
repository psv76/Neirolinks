# NST — NEIROLINKS Service Tool

NST — общая сервисная система NEIROLINKS для контроллеров Wiren Board.

## Статус

На момент этой фиксации:

- принятый production baseline: **NLI 0.1.9**;
- approved Release baseline: `nli-approved-0.1.9`;
- immutable commit baseline: `df484b8bf22835001d69ddb2dd18e3eafd3792b0`;
- NST 1.0 развивается как эволюция NLI 0.1.9;
- общая задача: GitHub Issue #85;
- текущая development-ветка: `system/nst/85-consolidation`;
- текущий development PR: #113 → `main`;
- исторический stack #98–#105 закрыт как superseded и больше не используется для разработки;
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

Generated deployment ABF62SL пересобран от нового immutable source commit после relocation:

- HHM 3.5;
- четыре object files из controller profile;
- специализированный `Systems/NST/diagnostics/ivolga-boiler-hhm-v1.json`.

CI проверяет deterministic rebuild и offline verification.

### 3. Approved components

Approved component snapshot синхронизирован с опубликованными HHM Releases 3.2–3.5. Для ABF62SL stable resolver выбирает HHM 3.5.

### 4. Pressure makeup

Controller profile ABF62SL заявляет capability `pressure_makeup`, но в новом approved component catalog этот компонент пока не опубликован как approved desired component.

Нельзя молча подменять его object file или придумывать release metadata.

### 5. Platform Release и live pilot

NST 1.0 platform Release для ABF62SL не опубликован.

Read-only pilot на live-контроллере ещё не выполнен.

До этого NST 1.0 не считается принятой production-системой.

## Consolidation #85

Stacked PR #98–#105 свёрнут в единственную development-ветку:

`system/nst/85-consolidation`

Ветка создана от актуального `main`. В неё перенесён cumulative snapshot head #105 без подтягивания всей старой `fix/...`-базы:

- полный каталог `NLI/` из head #105 как технический migration baseline;
- `.github/workflows/nli-check.yml` из head #105;
- `objects/05_31_Ivolga_13/controllers/ABF62SL.json` из head #105.

Первый consolidation commit сохраняет эти bytes без смысловой переработки. Это контрольная точка против потери накопленного результата.

Исторический корневой каталог `NLI/` удалён из development-ветки. Реализация перенесена в `Systems/NST/`; repo-relative paths и CI переведены на каноническую структуру. Исторический implementation README NLI сохранён отдельно в `docs/NLI_IMPLEMENTATION_README.md`.

Старые stacked PR после создания единого PR считаются superseded и не являются местом дальнейшей разработки.

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
