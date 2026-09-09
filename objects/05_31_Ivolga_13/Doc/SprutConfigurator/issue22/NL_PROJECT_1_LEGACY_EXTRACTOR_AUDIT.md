# Issue #22 — NL Project 1.0 legacy extractor audit

Дата: 2026-09-10

Источник: архив `NLP56.zip`, переданный пользователем. Архив содержит NL Project v0.20.8 и копию рабочей базы `data/nl_project.sqlite`.

## Безопасность анализа

База из архива анализировалась как отдельная копия в read-only режиме. Рабочий `D:\NLP\data\nl_project.sqlite` не открывался и не изменялся.

## Что подтверждено по объекту 05 31 Иволга

В базе найден объект:

```text
object_id     197
name          05 31 Иволга
project_folder D:/YandexDisk/05 NeiroLinks/05 31 Иволга/Проект/Беседка
layout_dwg_path D:/YandexDisk/05 NeiroLinks/05 31 Иволга/Проект/Беседка/working.dwg
```

Это подтверждает, что экземпляр NL Project 1.0 фактически содержит проектные данные беседки.

Основной рабочий проектный контекст беседки:

```text
controller_id 230
name          Проектный контекст WB-4
board_id      22862
```

Щиты, относящиеся к этим данным:

```text
WB-4  — Беседка
WB-5  — Беседка
СКС   — Гостиная
```

В объекте также присутствуют `ВРУ` и `WB-2`, но их наличие в legacy-базе не означает автоматически, что они относятся к Sprut.hub «Беседка». Для Sprut presentation их нельзя включать только по факту существования записи.

## Важный вывод по чтению NL Project 1.0

Нельзя просто выполнять `SELECT * FROM normalized_lines WHERE object_id=197` и считать результат актуальным: база хранит одновременно object-scope и рабочие controller-scope строки.

В исходном `core/repository.py` NL Project уже есть правильное правило объединения:

```text
key = (line_id, parent_line_id, record_kind)

сначала object-scope rows
затем controller-scope rows
controller-scope перезаписывает совпадающий key
```

Для Иволги:

```text
object-scope normalized rows     9
controller-scope normalized rows 62
итог после штатного merge        62
```

Именно это правило должен повторять legacy extractor. Благодаря ему, например, остаются актуальные назначения:

```text
351 → A47/Channel 1
352 → A47/Channel 2
353 → A47/Channel 3
354 → A48/Channel 1
355 → A48/Channel 2
356 → A48/Channel 3
```

а не более старые пустые назначения из object-scope snapshot.

## Подтверждённые пользовательские линии беседки

### Освещение / управляемые нагрузки

```text
301  Фасад      Свет фасад беседки          A41/K1
302  Прихожая   Свет прихожая                A41/K2
303  Санузел    Свет санузел                 A41/K3
304  Кухня      Свет кухня                   A42/K1
305  Кухня      Люстра кухня                 A42/K2
306  Гостиная   Люстра гостиная              A42/K3
307  Кухня      Бра мангала слева            A43/K1
308  Кухня      Бра мангала в центре         A43/K2
309  Кухня      Бра мангала справа           A43/K3
310  Гостиная   Бра гостиная                 A43/K4
311  Санузел    Подсветка зеркала            A43/K5
320  Фасад      Гирлянда                     A45/K1
351  Гостиная   Подсветка балки              A47/Channel 1
352  Гостиная   Подсветка балки              A47/Channel 2
353  Гостиная   Подсветка балки              A47/Channel 3
354  Кухня      Подсветка фартук             A48/Channel 1
355  Кухня      Подсветка мебели             A48/Channel 2
356  Кухня      LED над грилем               A48/Channel 3
501  Санузел    Вентилятор вытяжной          A43/K6
```

### Протечки

```text
441  Санузел  Датчик протечки  A44/F1
442  Кухня    Датчик протечки  A44/F2
```

### Датчики / RS-485 / периферия

```text
921.09  Прихожая   WB-MSW v.4      WB.02/RS-485 1
921.10  Прихожая   WB-M1W2 v.3     WB.02/RS-485 1
922.01  Прихожая   Датчик движения WB.02/RS-485 2
923.01  Гостиная   Карниз справа   WB.02/MOD1
923.02  Гостиная   Карниз слева    WB.02/MOD1
924.01  Фасад      Кондиционер     WB.02/MOD2
```

Для `921.09` в Project сохранён профиль WB-MSW:

```text
temperature_humidity = yes
motion               = yes
co2                   = none
voc                   = none
sound                 = no
```

То есть по проектным данным это профиль, эквивалентный нынешнему `MSW_THM` по функциональности T + RH + Motion. Перед генерацией SERIAL/MQTT имени нужно сверить фактический текущий alias на Wiren Board беседки; старый NL Project 1.0 не должен сам придумывать современный MQTT alias.

## Подтверждённые WB-модули

```text
A41  WB-MR3LV/S   Modbus 41  WB-4
A42  WB-MR3LV/S   Modbus 42  WB-4
A43  WB-MR6C v2   Modbus 43  WB-4
A44  WB-MWAC      Modbus 44  WB-4
A45  WB-MR6CU v2  Modbus 45  WB-4
A47  WB-LED       Modbus 47  WB-5
A48  WB-LED       Modbus 48  WB-5
921.06 WB-M1W2 v3 Modbus 100 WB-4
WB.02 WB8                   WB-4
UPS.02 WB-UPS v3 Modbus 200 WB-4
```

Modbus address — только диагностический/legacy факт. Он не должен становиться persistent Sprut identity.

## Что реально можно переиспользовать в NL Project 2.0

Legacy-specific часть должна быть узкой:

```text
NL Project 1.0 SQLite
→ read-only adapter
→ normalized Sprut source model
```

Переиспользуемая часть начинается после adapter:

```text
normalized Sprut source model
→ presentation policy
→ Sprut Plan YAML v2
→ Configurator
```

В NL Project 2.0 меняется только входной adapter:

```text
NL Project 2.0 model
→ тот же normalized Sprut source model
→ тот же YAML generator
```

## Что extractor НЕ должен делать

- не запускать `core.database.initialize()` и миграции NL Project 1.0;
- не открывать рабочую базу в write mode;
- не копировать внутренние `object_id`, `controller_id`, `board_id` в Sprut YAML как identity;
- не выводить Sprut runtime `aId/sId/cId`;
- не угадывать MQTT alias из Modbus address;
- не считать каждый физический capability обязательной сущностью Sprut;
- не смешивать данные разных Sprut.hub в один APPLY plan только потому, что они находятся в одном объекте Project.

## Следующий шаг

Сделать небольшой `nl_project_v1` adapter, который:

1. открывает указанную копию SQLite строго `mode=ro`;
2. находит объект по имени;
3. повторяет штатный merge `normalized_lines`;
4. извлекает boards/modules/field-device metadata;
5. отдаёт нейтральный normalized source model;
6. не создаёт конечный Sprut YAML, пока для конкретного устройства не подтверждена стабильная MQTT/SERIAL identity.

После этого общий YAML generator строится уже поверх neutral model и будет пригоден для будущего NL Project 2.0.