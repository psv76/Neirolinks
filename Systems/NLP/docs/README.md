# Документация NL Project 3.0

`docs/product/` содержит действующие продуктовые правила NL Project 3.0. История 1.0/2.0, recovery-задач и build reports сохраняется Git/Issue/PR и не является параллельной нормативной документацией.

Для быстрого восстановления разработки используется GitHub Issue `#145`. Он является маршрутизатором, а не заменой нормативных документов.

Для AutoCAD physical topology и точного block/ATTDEF contract используются:

- [CURRENT_TOPOLOGY_ARCHITECTURE.md](autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md);
- [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md);
- machine projection `../resources/autocad/block_contract.json`.

Правила оформления документации находятся в [DOCUMENTATION_REGULATION.md](DOCUMENTATION_REGULATION.md).

`engineering/` содержит техническую архитектуру, модель данных, тестовую стратегию, критерии приёмки и рабочие UI-сценарии. Статус разработки определяется [STATUS.md](STATUS.md).

Программный контур разработки описан в [DEVELOPMENT.md](DEVELOPMENT.md). Историческая миграция 2.0 source tree остаётся в [MIGRATION.md](MIGRATION.md).
