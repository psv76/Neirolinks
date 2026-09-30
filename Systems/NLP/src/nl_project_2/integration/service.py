"""Read-only validation center assembled from existing feature services."""

from __future__ import annotations

from dataclasses import dataclass

from nl_project_2.resource_labels import resource_user_label


@dataclass(frozen=True, slots=True)
class ValidationItem:
    severity: str
    code: str
    message: str
    section: str
    source_kind: str
    source_id: str


class IntegratedUiService:
    def __init__(self, *, constructor, cables, panels, specification) -> None:
        self.constructor = constructor
        self.cables = cables
        self.panels = panels
        self.specification = specification

    def validation_items(self, project_id: str) -> tuple[ValidationItem, ...]:
        items: list[ValidationItem] = []
        resources = {row["id"]: row for row in self.constructor.list_resources(project_id)}
        for result in self.constructor.validate_required_resources(project_id):
            if result.outcome == "PASS":
                continue
            source_id = result.entity_ids[0]
            resource = resources.get(source_id, {})
            label = _resource_label(resource)
            items.append(
                ValidationItem(
                    "WARNING",
                    "REQUIRED_RESOURCE_UNASSIGNED",
                    f"{label}: {result.message}",
                    "CONSTRUCTOR",
                    "RESOURCE",
                    source_id,
                )
            )
        for line in self.cables.line_cards(project_id):
            if line["effective_m"] is None:
                items.append(
                    ValidationItem(
                        "WARNING",
                        "CABLE_LENGTH_INCOMPLETE",
                        f"{line['designation']}: итоговая длина не определена",
                        "CABLES",
                        "CABLE_LINE",
                        line["id"],
                    )
                )
        for board in self.panels.list_boards(project_id):
            if board["board_kind"] == "BOARD_AV":
                continue
            layout = self.panels.board_layout(project_id=project_id, board_id=board["id"])
            for rail in layout["rails"]:
                for issue in rail["evaluation"].issues:
                    items.append(
                        ValidationItem(
                            "ERROR" if issue.blocking else "WARNING",
                            issue.code,
                            issue.message,
                            "PANELS",
                            "PANEL_RAIL",
                            rail["id"],
                        )
                    )
            for instance in layout["instances"]:
                if instance["layout_state"] == "READY":
                    continue
                items.append(
                    ValidationItem(
                        "WARNING",
                        instance["layout_state"],
                        f"{instance['designation']}: {instance['layout_state']}",
                        "PANELS",
                        "PROJECT_INSTANCE",
                        instance["id"],
                    )
                )
        specification = self.specification.build(project_id)
        for issue in specification["issues"]:
            items.append(
                ValidationItem(
                    "ERROR",
                    issue.code,
                    issue.message,
                    "SPECIFICATION",
                    issue.source_kind,
                    issue.source_id,
                )
            )
        for row in specification["rows"]:
            if row.budget_included and row.cost is None:
                source_kind, source_id = row.source_refs[0]
                items.append(
                    ValidationItem(
                        "WARNING",
                        "COST_UNKNOWN",
                        f"{row.name}: стоимость не определена",
                        "SPECIFICATION",
                        source_kind,
                        source_id,
                    )
                )
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    0 if item.severity == "ERROR" else 1,
                    item.section,
                    item.code,
                    item.source_id,
                ),
            )
        )


def _resource_label(row: dict) -> str:
    if not row:
        return "Ресурс"
    return resource_user_label(row)
