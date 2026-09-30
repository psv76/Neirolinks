"""Transactional panel, section, rail, placement, and material service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, and_, delete, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    assembly_material_fact,
    board,
    panel_placement,
    panel_rail,
    panel_section,
    passport_definition,
    passport_rule_definition,
    product_definition,
    project,
    project_instance,
)
from nl_project_2.persistence.uow import UnitOfWork

from .domain import PlacementInput, evaluate_rail

DIN_MODULE_MM = Decimal("18")


class PanelError(RuntimeError):
    pass


class PanelBlockingViolation(PanelError):
    pass


class PanelService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_boards(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(board)
                    .where(board.c.project_id == project_id, board.c.lifecycle == "ACTIVE")
                    .order_by(board.c.designation)
                ).mappings()
            ]

    def create_board(
        self,
        *,
        project_id: str,
        designation: str,
        title: str = "",
        board_kind: str = "ELECTRICAL",
        room_id: str | None = None,
    ) -> str:
        designation = designation.strip()
        board_kind = board_kind.strip().upper()
        if not designation:
            raise PanelError("Board designation is required")
        if board_kind == "BOARD_AV":
            raise PanelBlockingViolation("BOARD_AV is excluded from DIN panel layout")
        board_id = new_id()
        now = datetime.now(UTC)
        try:
            with UnitOfWork(self._engine) as uow:
                uow.execute(
                    board.insert().values(
                        id=board_id,
                        project_id=project_id,
                        designation=designation,
                        board_kind=board_kind,
                        room_id=room_id,
                        title=title.strip(),
                        lifecycle="ACTIVE",
                    )
                )
                self._touch_project(uow, project_id, now)
                uow.commit()
        except IntegrityError as exc:
            raise PanelBlockingViolation("Board designation must be unique") from exc
        return board_id

    def create_section(
        self,
        *,
        project_id: str,
        board_id: str,
        section_key: str,
        section_order: int,
    ) -> str:
        section_key = section_key.strip()
        if not section_key:
            raise PanelError("Section key is required")
        if section_order < 0:
            raise PanelError("Section order must be non-negative")
        section_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._panel_board(uow, project_id, board_id)
            try:
                uow.execute(
                    panel_section.insert().values(
                        id=section_id,
                        project_id=project_id,
                        board_id=board_id,
                        section_key=section_key,
                        section_order=section_order,
                    )
                )
                self._touch_project(uow, project_id, datetime.now(UTC))
                uow.commit()
            except IntegrityError as exc:
                raise PanelBlockingViolation("Section key must be unique within the board") from exc
        return section_id

    def delete_section(self, *, project_id: str, section_id: str) -> None:
        with UnitOfWork(self._engine) as uow:
            section = self._section(uow, project_id, section_id)
            occupied = uow.execute(
                select(panel_placement.c.id)
                .select_from(
                    panel_placement.join(
                        panel_rail, panel_rail.c.id == panel_placement.c.panel_rail_id
                    )
                )
                .where(panel_rail.c.panel_section_id == section_id)
                .limit(1)
            ).first()
            if occupied:
                raise PanelBlockingViolation(
                    f"Section {section['section_key']} contains placed instances"
                )
            uow.execute(delete(panel_section).where(panel_section.c.id == section_id))
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def create_rail(
        self,
        *,
        project_id: str,
        section_id: str,
        rail_order: int,
        usable_width_mm,
    ) -> str:
        if rail_order < 0:
            raise PanelError("Rail order must be non-negative")
        width = _decimal(usable_width_mm, allow_none=True)
        if width is not None and width <= 0:
            raise PanelError("Usable rail width must be positive")
        rail_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._section(uow, project_id, section_id)
            try:
                uow.execute(
                    panel_rail.insert().values(
                        id=rail_id,
                        project_id=project_id,
                        panel_section_id=section_id,
                        rail_order=rail_order,
                        usable_width_mm_decimal=None if width is None else str(width),
                    )
                )
                self._touch_project(uow, project_id, datetime.now(UTC))
                uow.commit()
            except IntegrityError as exc:
                raise PanelBlockingViolation(
                    "Rail order must be unique within the section"
                ) from exc
        return rail_id

    def assign_instance_to_board(self, *, project_id: str, instance_id: str, board_id: str) -> None:
        with UnitOfWork(self._engine) as uow:
            self._panel_board(uow, project_id, board_id)
            instance = self._instance(uow, project_id, instance_id)
            placed = uow.execute(
                select(panel_placement.c.id).where(
                    panel_placement.c.project_instance_id == instance_id,
                    panel_placement.c.project_id == project_id,
                )
            ).first()
            if placed and instance["board_id"] != board_id:
                raise PanelBlockingViolation("Remove the existing placement before changing board")
            uow.execute(
                update(project_instance)
                .where(project_instance.c.id == instance_id)
                .values(board_id=board_id, row_version=project_instance.c.row_version + 1)
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def place_instance(
        self,
        *,
        project_id: str,
        rail_id: str,
        instance_id: str,
        start_mm,
        orientation: str = "NORMAL",
    ) -> str:
        start = _decimal(start_mm)
        if start < 0:
            raise PanelBlockingViolation("Placement cannot start before the rail origin")
        orientation = _orientation(orientation)
        placement_id = new_id()
        with UnitOfWork(self._engine) as uow:
            rail = self._rail(uow, project_id, rail_id)
            section = self._section(uow, project_id, rail["panel_section_id"])
            instance = self._instance(uow, project_id, instance_id)
            if instance["board_id"] != section["board_id"]:
                raise PanelBlockingViolation(
                    "Instance must be explicitly assigned to the selected electrical board"
                )
            if uow.execute(
                select(panel_placement.c.id).where(
                    panel_placement.c.project_id == project_id,
                    panel_placement.c.project_instance_id == instance_id,
                )
            ).first():
                raise PanelBlockingViolation("A ProjectInstance may appear in DIN layout only once")
            facts = self._instance_facts(uow, project_id, instance_id)
            self._require_placeable(facts)
            candidate = PlacementInput(
                placement_id=placement_id,
                instance_id=instance_id,
                start_mm=start,
                width_mm=facts["width_mm"],
                mounting_compatible=facts["mounting_compatible"],
            )
            evaluation = self._evaluate_with(uow, project_id, rail, candidate)
            _raise_blocking(evaluation)
            uow.execute(
                panel_placement.insert().values(
                    id=placement_id,
                    project_id=project_id,
                    panel_rail_id=rail_id,
                    project_instance_id=instance_id,
                    start_mm_decimal=str(start),
                    width_mm_decimal=str(facts["width_mm"]),
                    orientation=orientation,
                    status="PLACED",
                )
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()
        return placement_id

    def move_placement(
        self,
        *,
        project_id: str,
        placement_id: str,
        rail_id: str,
        start_mm,
        orientation: str = "NORMAL",
    ) -> None:
        start = _decimal(start_mm)
        if start < 0:
            raise PanelBlockingViolation("Placement cannot start before the rail origin")
        orientation = _orientation(orientation)
        with UnitOfWork(self._engine) as uow:
            current = (
                uow.execute(
                    select(panel_placement).where(
                        panel_placement.c.id == placement_id,
                        panel_placement.c.project_id == project_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                raise PanelError("Placement not found")
            rail = self._rail(uow, project_id, rail_id)
            section = self._section(uow, project_id, rail["panel_section_id"])
            instance = self._instance(uow, project_id, current["project_instance_id"])
            if instance["board_id"] != section["board_id"]:
                raise PanelBlockingViolation("Target rail belongs to another board")
            facts = self._instance_facts(uow, project_id, instance["id"])
            self._require_placeable(facts)
            candidate = PlacementInput(
                placement_id=placement_id,
                instance_id=instance["id"],
                start_mm=start,
                width_mm=facts["width_mm"],
                mounting_compatible=facts["mounting_compatible"],
            )
            evaluation = self._evaluate_with(
                uow, project_id, rail, candidate, exclude_placement_id=placement_id
            )
            _raise_blocking(evaluation)
            uow.execute(
                update(panel_placement)
                .where(panel_placement.c.id == placement_id)
                .values(
                    panel_rail_id=rail_id,
                    start_mm_decimal=str(start),
                    width_mm_decimal=str(facts["width_mm"]),
                    orientation=orientation,
                    status="PLACED",
                    row_version=panel_placement.c.row_version + 1,
                )
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def remove_placement(self, *, project_id: str, placement_id: str) -> None:
        with UnitOfWork(self._engine) as uow:
            result = uow.execute(
                delete(panel_placement).where(
                    panel_placement.c.id == placement_id,
                    panel_placement.c.project_id == project_id,
                )
            )
            if result.rowcount != 1:
                raise PanelError("Placement not found")
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def record_material_fact(
        self,
        *,
        project_id: str,
        board_id: str,
        material_kind: str,
        quantity,
        unit: str,
        reason: str,
        source_kind: str = "MANUAL_CORRECTION",
    ) -> str:
        self._validate_material_text(material_kind, unit, reason, source_kind)
        value = _decimal(quantity)
        if value < 0:
            raise PanelError("Material quantity cannot be negative")
        fact_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._panel_board(uow, project_id, board_id)
            uow.execute(
                assembly_material_fact.insert().values(
                    id=fact_id,
                    project_id=project_id,
                    board_id=board_id,
                    material_kind=material_kind.strip().upper(),
                    quantity_decimal=str(value),
                    unit=unit.strip(),
                    reason=reason.strip(),
                    source_kind=source_kind.strip().upper(),
                )
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()
        return fact_id

    def board_layout(self, *, project_id: str, board_id: str) -> dict:
        with self._engine.connect() as connection:
            selected_board = self._panel_board(connection, project_id, board_id)
            sections = [
                dict(row)
                for row in connection.execute(
                    select(panel_section)
                    .where(
                        panel_section.c.project_id == project_id,
                        panel_section.c.board_id == board_id,
                    )
                    .order_by(panel_section.c.section_order, panel_section.c.section_key)
                ).mappings()
            ]
            section_ids = [row["id"] for row in sections]
            rails = (
                [
                    dict(row)
                    for row in connection.execute(
                        select(panel_rail)
                        .where(panel_rail.c.panel_section_id.in_(section_ids))
                        .order_by(panel_rail.c.panel_section_id, panel_rail.c.rail_order)
                    ).mappings()
                ]
                if section_ids
                else []
            )
            placements = self._placement_rows(connection, project_id)
            candidates = self._instance_candidates(connection, project_id, board_id)
            candidates_by_id = {row["id"]: row for row in candidates}
            rail_ids = {rail["id"] for rail in rails}
            placement_by_rail: dict[str, list[dict]] = {}
            for placement in placements:
                if placement["panel_rail_id"] not in rail_ids:
                    continue
                facts = candidates_by_id[placement["project_instance_id"]]
                current_width = facts["width_mm"]
                stored_width = _decimal(placement["width_mm_decimal"], allow_none=True)
                placement.update(
                    current_width_mm=current_width,
                    stored_width_mm=stored_width,
                    width_changed=(
                        current_width is not None
                        and stored_width is not None
                        and current_width != stored_width
                    ),
                    mounting_compatible=facts["mounting_compatible"],
                    designation=facts["designation"],
                    product_key=facts["product_key"],
                )
                placement_by_rail.setdefault(placement["panel_rail_id"], []).append(placement)
            rail_rows = []
            for rail in rails:
                rail_placements = placement_by_rail.get(rail["id"], [])
                evaluation = evaluate_rail(
                    _decimal(rail["usable_width_mm_decimal"], allow_none=True),
                    tuple(
                        PlacementInput(
                            placement_id=row["id"],
                            instance_id=row["project_instance_id"],
                            start_mm=_decimal(row["start_mm_decimal"]),
                            width_mm=row["current_width_mm"],
                            mounting_compatible=row["mounting_compatible"],
                        )
                        for row in rail_placements
                    ),
                )
                order = {
                    item_id: index for index, item_id in enumerate(evaluation.ordered_placement_ids)
                }
                rail_placements.sort(key=lambda row: order[row["id"]])
                rail_rows.append({**rail, "placements": rail_placements, "evaluation": evaluation})
            materials = [
                {**dict(row), "occupies_din": False}
                for row in connection.execute(
                    select(assembly_material_fact)
                    .where(
                        assembly_material_fact.c.project_id == project_id,
                        assembly_material_fact.c.board_id == board_id,
                    )
                    .order_by(assembly_material_fact.c.material_kind)
                ).mappings()
            ]
        return {
            "board": dict(selected_board),
            "sections": sections,
            "rails": rail_rows,
            "instances": candidates,
            "materials": materials,
        }

    def _evaluate_with(
        self,
        connection,
        project_id: str,
        rail: dict,
        candidate: PlacementInput,
        exclude_placement_id: str | None = None,
    ):
        placements = []
        for row in self._placement_rows(connection, project_id, rail["id"]):
            if row["id"] == exclude_placement_id:
                continue
            facts = self._instance_facts(connection, project_id, row["project_instance_id"])
            placements.append(
                PlacementInput(
                    placement_id=row["id"],
                    instance_id=row["project_instance_id"],
                    start_mm=_decimal(row["start_mm_decimal"]),
                    width_mm=facts["width_mm"],
                    mounting_compatible=facts["mounting_compatible"],
                )
            )
        placements.append(candidate)
        return evaluate_rail(
            _decimal(rail["usable_width_mm_decimal"], allow_none=True), tuple(placements)
        )

    @staticmethod
    def _placement_rows(connection, project_id: str, rail_id: str | None = None) -> list[dict]:
        statement = select(panel_placement).where(panel_placement.c.project_id == project_id)
        if rail_id is not None:
            statement = statement.where(panel_placement.c.panel_rail_id == rail_id)
        return [dict(row) for row in connection.execute(statement).mappings()]

    def _instance_candidates(self, connection, project_id: str, board_id: str) -> list[dict]:
        rows = connection.execute(self._instance_statement(project_id)).mappings()
        placements = {
            row[0]
            for row in connection.execute(
                select(panel_placement.c.project_instance_id).where(
                    panel_placement.c.project_id == project_id
                )
            )
        }
        result = []
        for row in rows:
            facts = _facts(dict(row))
            board_state = (
                "ASSIGNED"
                if row["board_id"] == board_id
                else "UNASSIGNED"
                if row["board_id"] is None
                else "OTHER_BOARD"
            )
            if row["product_definition_id"] is None:
                completeness = "PRODUCT_NOT_SELECTED"
            elif not facts["mounting_compatible"]:
                completeness = "MOUNTING_NOT_DIN"
            elif facts["width_mm"] is None:
                completeness = "WIDTH_UNKNOWN"
            else:
                completeness = "READY"
            result.append(
                {
                    **dict(row),
                    **facts,
                    "board_state": board_state,
                    "layout_state": completeness,
                    "placed": row["id"] in placements,
                }
            )
        return result

    def _instance_facts(self, connection, project_id: str, instance_id: str) -> dict:
        row = (
            connection.execute(
                self._instance_statement(project_id).where(project_instance.c.id == instance_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PanelError("Project instance not found")
        return {**dict(row), **_facts(dict(row))}

    @staticmethod
    def _instance_statement(project_id: str):
        return (
            select(
                project_instance,
                passport_definition.c.passport_key,
                product_definition.c.product_key,
                product_definition.c.name.label("product_name"),
                product_definition.c.width_mm_decimal,
                product_definition.c.din_width_decimal,
                product_definition.c.project_parameters_json,
                passport_rule_definition.c.parameters_json.label("din_layout_rule_json"),
            )
            .join(
                passport_definition,
                passport_definition.c.id == project_instance.c.passport_definition_id,
            )
            .outerjoin(
                product_definition,
                product_definition.c.id == project_instance.c.product_definition_id,
            )
            .outerjoin(
                passport_rule_definition,
                and_(
                    passport_rule_definition.c.passport_definition_id == passport_definition.c.id,
                    passport_rule_definition.c.rule_kind == "DIN_LAYOUT",
                ),
            )
            .where(
                project_instance.c.project_id == project_id,
                project_instance.c.lifecycle == "ACTIVE",
            )
            .order_by(project_instance.c.designation)
        )

    @staticmethod
    def _panel_board(connection, project_id: str, board_id: str) -> dict:
        row = (
            connection.execute(
                select(board).where(
                    board.c.id == board_id,
                    board.c.project_id == project_id,
                    board.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PanelError("Board not found")
        if row["board_kind"] == "BOARD_AV":
            raise PanelBlockingViolation("BOARD_AV is excluded from DIN panel layout")
        return dict(row)

    @staticmethod
    def _section(connection, project_id: str, section_id: str) -> dict:
        row = (
            connection.execute(
                select(panel_section).where(
                    panel_section.c.id == section_id,
                    panel_section.c.project_id == project_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PanelError("Panel section not found")
        return dict(row)

    @staticmethod
    def _rail(connection, project_id: str, rail_id: str) -> dict:
        row = (
            connection.execute(
                select(panel_rail).where(
                    panel_rail.c.id == rail_id,
                    panel_rail.c.project_id == project_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PanelError("Panel rail not found")
        return dict(row)

    @staticmethod
    def _instance(connection, project_id: str, instance_id: str) -> dict:
        row = (
            connection.execute(
                select(project_instance).where(
                    project_instance.c.id == instance_id,
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PanelError("Project instance not found")
        return dict(row)

    @staticmethod
    def _require_placeable(facts: dict) -> None:
        if facts["product_definition_id"] is None:
            raise PanelBlockingViolation(
                "Product is not selected; layout remains incomplete and no width is assumed"
            )
        if not facts["mounting_compatible"]:
            raise PanelBlockingViolation("Selected product is not compatible with DIN mounting")
        if facts["width_mm"] is None:
            raise PanelBlockingViolation(
                "Selected product width is unknown; no fallback width is allowed"
            )

    @staticmethod
    def _validate_material_text(*values: str) -> None:
        if any(not value.strip() for value in values):
            raise PanelError("Material kind, unit, reason and source are required")

    @staticmethod
    def _touch_project(uow, project_id: str, now: datetime) -> None:
        uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(project_revision=project.c.project_revision + 1, updated_at_utc=now)
        )


def _facts(row: dict) -> dict:
    product_parameters = row.get("project_parameters_json") or {}
    rule = (row.get("din_layout_rule_json") or {}).get("value") or {}
    mounting = product_parameters.get("mounting", rule.get("mounting"))
    mounting_values = mounting if isinstance(mounting, list) else [mounting]
    mounting_compatible = any(
        value is not None
        and any(token in str(value).upper() for token in ("DIN_RAIL", "TS35", "TH35"))
        for value in mounting_values
    )
    modules = _decimal(row.get("din_width_decimal"), allow_none=True)
    physical_width = _decimal(row.get("width_mm_decimal"), allow_none=True)
    width = modules * DIN_MODULE_MM if modules is not None and modules > 0 else physical_width
    return {
        "mounting": mounting,
        "mounting_compatible": mounting_compatible,
        "width_mm": width if width is not None and width > 0 else None,
        "width_source": (
            "PRODUCT_DIN_MODULES"
            if modules is not None and modules > 0
            else "PRODUCT_DIMENSION_MM"
            if physical_width is not None and physical_width > 0
            else "UNKNOWN"
        ),
    }


def _decimal(value, *, allow_none: bool = False) -> Decimal | None:
    if value is None or str(value).strip() == "":
        if allow_none:
            return None
        raise PanelError("Numeric value is required")
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise PanelError(f"Invalid numeric value: {value}") from exc
    if not result.is_finite():
        raise PanelError("Numeric value must be finite")
    return result


def _orientation(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"NORMAL", "REVERSED"}:
        raise PanelError("Orientation must be NORMAL or REVERSED")
    return normalized


def _raise_blocking(evaluation) -> None:
    blocking = [issue for issue in evaluation.issues if issue.blocking]
    if blocking:
        raise PanelBlockingViolation("; ".join(f"{item.code}: {item.message}" for item in blocking))
