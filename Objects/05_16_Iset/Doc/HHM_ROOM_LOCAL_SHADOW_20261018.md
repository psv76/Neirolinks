> **Актуализация 29.10.2026:** документ сохраняет историческое состояние на дату составления. Насосный модуль `wb-mr6cu_37` (Modbus 37) заменён на `wb-mr6cu_12` (Modbus 12, S/N 353796). Ссылки на 37 ниже — исторические, для актуального управления и диагностики использовать 12. См. `objects/05_16_Iset/Doc/PHYSICAL_CHANNEL_MAP.md`.

# 05 16 Исеть — WB-local room settings and shadow bridge (Issue #204)

**Status 2026-10-18: offline tested, Draft only. No live controller install,
no WB config edits, no physical output write, no merge or NST release.**

## What is implemented

- `Objects/05_16_Iset/HHM/simple_room_thermostat.js` — the approved
  simplified thermostat: direct WB-MSW temperature + setpoint + hysteresis,
  no poll-sequence/freshness validation and no sensor timeout.
  A real, explicit MSW error may stop **only its own** room.
- `Objects/05_16_Iset/HHM/room_settings_store.js` — one JSON record per
  room in an injected WB `PersistentStorage` object, with revision and
  a synchronous write/read-back check. No invented setpoints.
  `proposeInitial()` generates a *candidate string*, does not persist it;
  initial installation of approved settings must be explicitly authorised.
  A read-back is not proof of power-fail disk durability; acceptance
  on real WB is still required.
- `Objects/05_16_Iset/HHM/room_local_runtime.js` — creates up to eight
  configured room controllers, keeps missing/corrupt/out-of-bounds
  records as `NOT_COMMISSIONED` **without stopping other rooms**,
  calculates individual demand and passes it to the existing
  `HHMRoomPathGate` for **logical output intents only**. Result always
  reports `physicalWriteAllowed=false`.
- `Objects/05_16_Iset/Wirenboard/wb-rules/28_hhm_rooms_shadow.js` —
  shadow-only WB rule candidate. Watches real eight WB-MSW Temperature
  controls by `defineRule.whenChanged` and their device
  `/devices/<device>/meta/error` by `trackMqtt`. Exposes eight
  read-only virtual diagnostics + a global shadow status. Logs only
  state/demand changes. Writes **only** virtual controls under
  `iset_hhm_..._shadow`, NEVER physical `wb-mio-gpio_195:2/K1..K11`
  or `wb-mr6cu_37/K4`. It has no HA heartbeat requirement.

## Required WB module packaging (NOT YET DELIVERED/DEPLOYED)

The candidate shadow rule loads modules from `/etc/wb-rules-modules`
via WB's `require("Name")` API. These name-to-file aliases must be
provided by NST packaging when the separate shadow test is approved:

| WB require name | Source in this PR |
|---|---|
| `IsetRoomSimpleThermostat` | `Objects/05_16_Iset/HHM/simple_room_thermostat.js` |
| `IsetRoomSettingsStore` | `Objects/05_16_Iset/HHM/room_settings_store.js` |
| `IsetRoomLocalRuntime` | `Objects/05_16_Iset/HHM/room_local_runtime.js` |
| `IsetRoomZones` | `Objects/05_16_Iset/HHM/room_zones.js` |
| `HHMRoomPathGate` | `Systems/HHM/core/HHMRoomPathGate.js` |

No corresponding module files are installed on WB by this PR.
**Do not copy this single rule to live without the entire module set
and a separate approval.** `PersistentStorage("iset_hhm_rooms_v1",
{global:true})` is only instantiated in the candidate rule.

## Actual commissioning blockers (not discarded safety)

1. **Eight approved setpoints/modes/hysteresis:** current
   `room_zones.js` still has `approvedSetpoint:null` for every room.
   No defaults are silently provisioned, and `commissioned=false`.
2. **Live read-only verification of MSW error topic payloads:** the
   `meta/error` normalization presently accepts `0`, `false`,
   empty as no explicit error; any other nonempty payload means
   explicit error for **that room only**. It is an object-level
   candidate compatible with prior WB `trackMqtt` examples, not
   yet an on-site acceptance.
3. **Actual persistent storage acceptance:** update one approved
   stored room setpoint in a supervised shadow acceptance; confirm
   survives a controlled rules/service restart and power cycle.
   Preserve existing HM2 ownership throughout.
4. **Physical single writer cutover:** the live
   `23_heating_living_manager.js` still owns living NO K1..K11 and
   pump K4, and uses HA heartbeat. No second writer may be installed
   alongside it. Cutover/rollback must be separately approved and
   tested, along with the physical open delay (180 s as-built),
   valid independent equipment protections and pump control.
5. **UI bridge:** shadow virtual values are intentionally read-only.
   Writable setpoint, mode, Sprut.hub thermostat names/templates,
   status reconciliation and authorization are later integration
   tasks; don't guess project equipment numbers.
6. The old experiment modules for complex WB-MSW health remain in
   Draft PR #206 as research only and MUST NOT be included in
   Iset's runtime dependency set.

## Regressions

```sh
node Systems/HHM/tests/iset-simple-room-thermostat.js
node Systems/HHM/tests/iset-room-local-runtime.js
node Systems/HHM/tests/iset-wb-shadow-bridge.js
```

Direct offline tests cover:
- one room explicit sensor failure does not prevent another room's heat;
- unchanged low temperature continues to request heat normally;
- missing or invalid reading does not propose forced closing;
- no default setpoints / not commissioned state, incorrect stored
  data isolation, revision-based local settings update;
- WB-rule mocked `trackMqtt`, `defineRule`,
  `defineVirtualDevice`, `PersistentStorage`, with assertions that
  no physical output writes are issued.

**Not field acceptance:** tests mock the WB APIs and do not prove module
loading, `PersistentStorage` flushing, broker event payloads, actuator
opening or pump start under a live `wb-rules` process.

See also `Objects/05_16_Iset/Doc/HHM_ROOM_SIMPLE_POLICY.md`.

## Update 18.10.2026 — timers

For new Iset HHM, actuator-open wait is **120 seconds**, while the
currently live HM2 continues its prior 180-second policy until the
approved cutover. The shadow panel must expose per-actuator remaining
open-wait time, the K4 pump start-wait countdown, pump readback running
elapsed time and pending-stop confirmation elapsed time. These are
operator diagnostics, not additional safety interlocks or physical
movement measurements. There is no approved K4 postrun interval;
never invent a countdown for it. Other HHM pumps require verified
object mappings before creating analogous timer fields.

## Видимые таймеры новой HHM

Новая выдержка открытия NO — 120 с, текущий HM2 остаётся на 180 с.
Каждая комнатная панель показывает отдельные servo_kN_timer для
каждого из 11 приводов, плюс общий opening_timer зоны. Общая панель
K4 показывает три разных времени: до возможного пуска, наблюдаемой
работы ON и ожидания readback OFF после расчётного STOP. Цикл 1 с.

Все таймеры оценивают наблюдаемое состояние релейных выходов и
расчёт новой HHM. Это не доказательство механического положения
сервопривода, гидравлического протока или выполнения рассчитанной
физической команды. Для остальных насосов будущей HHM действует
тот же принцип визуализации после проверки их реальных каналов.
