# Типовой deployment / acceptance checklist

## 1. Project / model

- [ ] помещения определены;
- [ ] Project IDs определены;
- [ ] устройства имеют корректный functional/profile contract;
- [ ] relay outputs имеют функциональный тип;
- [ ] для каждой целевой Sprut entity известен stable SERIAL;
- [ ] display names проходят ограничения Sprut;
- [ ] duplicate SERIAL отсутствуют.

## 2. WB aliases

### MSW

- [ ] имя соответствует `9xx.yy_MSW_PROFILE`;
- [ ] PROFILE соответствует реальным capabilities.

### M1W2

- [ ] имя соответствует `9xx.yy_M1W2_W1_W2`;
- [ ] W1/W2 соответствуют роли физического порта.

### Relays

- [ ] device alias устойчив;
- [ ] control устойчив;
- [ ] user-facing type известен;
- [ ] технические outputs не попали в Lightbulb whitelist.

## 3. WB thermostat engine, если используется

- [ ] virtual device name соответствует contract;
- [ ] sensors существуют;
- [ ] physical outputs подтверждены;
- [ ] синхронные outputs принадлежат одной logical zone;
- [ ] нет второго runtime writer тех же outputs;
- [ ] virtual controls соответствуют Sprut template;
- [ ] ручная инженерная проверка выполнена.

## 4. Sprut templates

- [ ] нужные templates установлены;
- [ ] конфликтующие templates отсутствуют;
- [ ] model recognition корректен;
- [ ] Services минимальны;
- [ ] нет duplicate templates на один modelId;
- [ ] template status соответствует фактической степени проверки.

## 5. Rediscover

Для чистого acceptance по возможности:

1. удалить только target custom Accessory;
2. не удалять системные/нерелевантные сущности;
3. дождаться повторного создания template entities;
4. проверить базовый entity shape.

## 6. Configurator

### DISCOVER

- [ ] rooms прочитаны;
- [ ] accessories прочитаны;
- [ ] services прочитаны;
- [ ] target SERIAL присутствуют;
- [ ] duplicate SERIAL отсутствуют.

### YAML

- [ ] `format_version` поддерживается;
- [ ] target count ожидаемый;
- [ ] все обязательные поля есть;
- [ ] display names валидны;
- [ ] все комнаты существуют.

### DRY RUN

- [ ] `errors = 0`;
- [ ] просмотрено количество изменений;
- [ ] выборочно проверены разные типы entities;
- [ ] неоднозначные Service mappings отсутствуют.

### APPLY

- [ ] fresh preflight прошёл;
- [ ] пользователь явно подтвердил `APPLY`;
- [ ] нет RPC errors.

### VERIFY

- [ ] fresh DISCOVER выполнен;
- [ ] все targets PASSED;
- [ ] `FAILED = 0`.

## 7. Диагностика FAILED

Нельзя считать:

```text
RPC success = configuration success
```

Порядок:

1. fresh VERIFY;
2. DRY RUN;
3. проверить конкретный `CHANGE`/`ERROR`;
4. проверить round-trip display name;
5. проверить room;
6. проверить Service type;
7. проверить template;
8. только после этого повторять APPLY.

## 8. Запрещённые shortcuts

Не использовать как основной процесс:

- ручное массовое переименование;
- hardcode Sprut runtime ID;
- universal Lightbulb для всех relays;
- перенос критической инженерной логики в Sprut scenes;
- APPLY без DRY RUN;
- завершение без VERIFY.
