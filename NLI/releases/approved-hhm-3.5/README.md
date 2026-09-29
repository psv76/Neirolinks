# HHM 3.5 approved-catalog candidate

Основание: live audit operator journal после approved HHM 3.4, #69/#81.

- Runtime commit: `48408e6f1649ad17d0b3253f1b7cade258cd4fb3`
- Manifest commit: `05bdaec7d0bd82615b7c0247df0d0737c59df71e`
- Boiler manifest SHA256: `12d7946643ca2307bf0cf92fd582d33de19e83fa60c9a3c0c6b79c1f7e1f4be9`
- Gazebo manifest SHA256: `e638452c01d732b4b50f5e610a2c83f1fddbee73f7d338c46114dd240b859a8d`

3.5 изменяет operator logging, не алгоритм отопления:
- duplicate boiler-mode command подавлен;
- одно поле причины в pump/hot-port commands;
- normal source warm-up = INFO SOURCE_WARMING;
- конкретные названия timer events.

Наличие файлов candidate в репозитории не означает публикацию stable release.
До отдельной публикации тег `nli-approved-hhm-3.5` отсутствует, live WB остаётся на 3.4.
