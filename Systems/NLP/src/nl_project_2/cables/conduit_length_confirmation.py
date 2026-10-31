"""Q216: operator-confirmed FINAL length of one existing physical Conduit.

A confirmed physical tube can have several independent CABLE/BUS members.
This is a narrowly scoped operator override, not inferred from their lengths,
their terminal proximity or a FRAME. No DWG edit, schema/catalog migration,
electrical topology edit, or automatic BUS length publication is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update

from nl_project_2.persistence.schema import (
    bus_segment,
    bus_segment_conduit_assignment,
    cable_segment,
    conduit,
    conduit_segment_assignment,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork


class ConduitLengthConfirmationError(ValueError):
    """A manual Conduit quantity cannot be accepted safely."""


@dataclass(frozen=True, slots=True)
class ConduitLengthConfirmationPlan:
    project_id: str
    conduit_id: str
    designation: str
    project_revision: int
    conduit_row_version: int
    former_length_m: str | None
    former_path: dict
    # Complete membership snapshot; preserve both ordinary and BUS identities.
    members: tuple[tuple[str, str, int], ...]


def _quantity(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ConduitLengthConfirmationError("Некорректная длина трубы") from exc
    if not number.is_finite() or number <= 0:
        raise ConduitLengthConfirmationError("Длина физической трубы должна быть больше нуля")
    return number


class ConduitLengthConfirmation:
    """Approve one *entered final physical quantity*, with optimistic recheck."""

    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _plan(uow, project_id: str, conduit_id: str) -> ConduitLengthConfirmationPlan:
        revision = uow.execute(
            select(project.c.project_revision).where(project.c.id == project_id)
        ).scalar_one_or_none()
        if revision is None:
            raise ConduitLengthConfirmationError("Проект не найден")
        tube = (
            uow.execute(
                select(conduit).where(
                    conduit.c.id == conduit_id,
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if tube is None:
            raise ConduitLengthConfirmationError("Активная труба не найдена")
        members: list[tuple[str, str, int]] = []
        for kind, assignment, segment, segment_column in (
            (
                "CABLE",
                conduit_segment_assignment,
                cable_segment,
                conduit_segment_assignment.c.cable_segment_id,
            ),
            (
                "BUS",
                bus_segment_conduit_assignment,
                bus_segment,
                bus_segment_conduit_assignment.c.bus_segment_id,
            ),
        ):
            for sid, version, state, segment_project in uow.execute(
                select(
                    segment.c.id,
                    assignment.c.row_version,
                    segment.c.migration_state,
                    segment.c.project_id,
                )
                .select_from(assignment)
                .join(segment, segment.c.id == segment_column)
                .where(
                    assignment.c.project_id == project_id,
                    assignment.c.conduit_id == conduit_id,
                )
            ):
                if segment_project != project_id or state != "CONFIRMED":
                    raise ConduitLengthConfirmationError(
                        "Сегмент трубы не имеет подтверждённой топологии"
                    )
                members.append((kind, str(sid), int(version)))
        if not members:
            raise ConduitLengthConfirmationError(
                "У пустой трубы нельзя подтвердить физическую длину"
            )
        return ConduitLengthConfirmationPlan(
            project_id=project_id,
            conduit_id=conduit_id,
            designation=str(tube["designation"]),
            project_revision=int(revision),
            conduit_row_version=int(tube["row_version"]),
            former_length_m=(
                None if tube["length_m_decimal"] is None else str(tube["length_m_decimal"])
            ),
            former_path=dict(tube["path_json"] or {}),
            members=tuple(sorted(members)),
        )

    def preview(self, project_id: str, conduit_id: str) -> ConduitLengthConfirmationPlan:
        with UnitOfWork(self.engine) as uow:
            return self._plan(uow, project_id, conduit_id)

    def apply(
        self,
        plan: ConduitLengthConfirmationPlan,
        *,
        final_length_m: object,
        justification: str,
        confirmed_physical_length: bool = False,
    ) -> None:
        if not confirmed_physical_length:
            raise ConduitLengthConfirmationError(
                "Требуется явное подтверждение итоговой длины физической трубы"
            )
        length = _quantity(final_length_m)
        note = str(justification or "").strip()
        if not note or len(note) > 500:
            raise ConduitLengthConfirmationError(
                "Укажите основание измерения физической длины (до 500 символов)"
            )
        with UnitOfWork(self.engine) as uow:
            current = self._plan(uow, plan.project_id, plan.conduit_id)
            if current != plan:
                raise ConduitLengthConfirmationError(
                    "Данные трубы изменились после предпросмотра. Обновите список."
                )
            now = datetime.now(UTC)
            path = dict(current.former_path)
            path.update(
                length_source="USER_CONFIRMED",
                manual_length_basis="OPERATOR_FINAL_PHYSICAL_CONDUIT",
                manual_length_note=note,
                manual_length_member_keys=[
                    f"{kind}:{sid}" for kind, sid, _version in current.members
                ],
            )
            changed = uow.execute(
                update(conduit)
                .where(
                    conduit.c.id == plan.conduit_id,
                    conduit.c.project_id == plan.project_id,
                    conduit.c.row_version == plan.conduit_row_version,
                    conduit.c.lifecycle == "ACTIVE",
                )
                .values(
                    length_m_decimal=str(length),
                    path_json=path,
                    updated_at_utc=now,
                    row_version=conduit.c.row_version + 1,
                )
            )
            if changed.rowcount != 1:
                raise ConduitLengthConfirmationError("Труба изменилась; запись отменена")
            changed_revision = uow.execute(
                update(project)
                .where(
                    project.c.id == plan.project_id,
                    project.c.project_revision == plan.project_revision,
                )
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=now,
                )
            )
            if changed_revision.rowcount != 1:
                raise ConduitLengthConfirmationError("Ревизия проекта изменилась; запись отменена")
            uow.commit()
