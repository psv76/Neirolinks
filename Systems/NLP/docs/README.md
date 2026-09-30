# Документация NL Project 2.0

`docs/product/` содержит действующие продуктовые правила NL Project 2.0. История обсуждений, recovery-задач и build reports не является параллельной нормативной документацией и сохраняется историей Git/Issue/PR.

Для AutoCAD physical topology и точного block/ATTDEF contract используются:

- `autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md`;
- `autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md`;
- machine projection `../resources/autocad/block_contract.json`.

Правила оформления документации находятся в `DOCUMENTATION_REGULATION.md`.

`engineering/` содержит техническую архитектуру, модель данных, тестовую стратегию, критерии приёмки, рабочие UI-сценарии и LED test cases. Статус реализации и приёмки определяется `STATUS.md`, а не прежними номерами build-задач.

Программный контур разработки описан в `DEVELOPMENT.md`. Machine contract сохраняет исходные provenance-имена документов; соответствие новым путям указано в `MIGRATION.md`.

Перед изменением продуктового правила необходимо проверить, что оно имеет один источник истины и не дублируется в нескольких документах.
