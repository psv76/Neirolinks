# HHM 3.6 approved-catalog candidate

Основание: #81 / #69, live HHM 3.5 и полевое уточнение по выбегу насосов.

- Runtime commit R: `f4673abbe52f1a89db5c84dd4c8cd391bc9ee0ef`
- Manifest/test commit M: `12e5805d22e365bdbe049245fefccdc005e960fa`
- Boiler manifest SHA256: `9469bf5c4d62555b62adcc033fde62a151156392cd64004ebaaae075f6eb37ab`
- Gazebo manifest SHA256: `df1efa30c6eb5e289af8acc369a930c83e2da541a1cee9a9fa989f4701d93614`
- HHM3 FSE checks on M: run 36621102903 — SUCCESS
- NLI v0.1 WB compatibility on M: run 36621102930 — SUCCESS

## 3.6

- 501/502/503/504: pump postrun 120 s;
- 505: 0 s до отдельного решения;
- неизменный Heating Setpoint не создаёт operator event при техническом reassert;
- persistent last setpoint не теряется при reload/restart;
- новый подтверждённый Winter session снова разрешает одну запись setpoint;
- Current Boiler Mode command/readback semantics 3.5 сохранены.

Наличие candidate-файлов не означает публикацию stable GitHub Release.
До отдельного Publish release тег `nli-approved-hhm-3.6` отсутствует.
