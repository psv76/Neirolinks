"""Atomic operator-approved physical conduit reassignments (Issue #286).

No DWG writes. Preview/revalidate before any DB mutation. The operator must
confirm that the selected conduit assignments describe the SAME physical run;
logical length equality alone never establishes that fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus_segment,
    bus_segment_conduit_assignment,
    cable_segment,
    conduit,
    conduit_segment_assignment,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork

from .domain import ConduitContractError, validate_line_conduit_fields
from .recalculation import refresh_conduit_length
from .service import CableService


class RouteMutationError(ValueError):
    """An operation was invalid or stale; no modifications were committed."""


@dataclass(frozen=True)
class RoutePlan:
    project_id: str
    mode: str
    target_id: str
    sources: tuple[str, ...]
    selected: tuple[tuple[str, str], ...]
    members: tuple[tuple[str, str, str | None, int], ...]
    conduits: tuple[tuple[str, str, int, str, str, str, str], ...]
    revision: int
    warnings: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.members)


class RouteConduitCommands:
    """One transaction for ordinary cable segments AND physical BUS segments."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def preview_merge(
        self, project_id: str, conduit_ids: tuple[str, ...], target_id: str
    ) -> RoutePlan:
        ids = tuple(sorted(set(conduit_ids)))
        if len(ids) < 2 or target_id not in ids:
            raise RouteMutationError("Выберите минимум две трубы и основную трубу среди них.")
        with UnitOfWork(self.engine) as uow:
            return self._plan(uow, project_id, "MERGE", target_id, ids, ())

    def preview_move(
        self,
        project_id: str,
        selected: tuple[tuple[str, str], ...],
        target_id: str,
    ) -> RoutePlan:
        if not selected:
            raise RouteMutationError("Не выбраны физические сегменты.")
        if any(kind not in {"CABLE", "BUS"} for kind, _id in selected):
            raise RouteMutationError("Допустимы только физические сегменты CABLE/BUS.")
        if len(set(selected)) != len(selected):
            raise RouteMutationError("Повторяется идентификатор физического сегмента.")
        with UnitOfWork(self.engine) as uow:
            return self._plan(uow, project_id, "MOVE", target_id, (), tuple(sorted(selected)))

    def _plan(self, uow, project_id, mode, target_id, sources, selected):
        revision = uow.execute(
            select(project.c.project_revision).where(project.c.id == project_id)
        ).scalar_one_or_none()
        if revision is None:
            raise RouteMutationError("Проект не найден.")
        active = {
            row["id"]: dict(row)
            for row in uow.execute(
                select(conduit).where(
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
            ).mappings()
        }
        if target_id not in active or any(source not in active for source in sources):
            raise RouteMutationError("Труба удалена или относится к другому проекту.")
        target = active[target_id]
        rows = []
        for kind, segment, assignment, key in (
            ("CABLE", cable_segment, conduit_segment_assignment, "cable_segment_id"),
            ("BUS", bus_segment, bus_segment_conduit_assignment, "bus_segment_id"),
        ):
            records = {
                row["id"]: row
                for row in uow.execute(
                    select(segment).where(segment.c.project_id == project_id)
                ).mappings()
            }
            assignments = list(
                uow.execute(
                    select(assignment.c[key], assignment.c.conduit_id).where(
                        assignment.c.project_id == project_id
                    )
                ).all()
            )
            owners = {}
            for segment_id, owner_id in assignments:
                if segment_id in owners:
                    raise RouteMutationError("Обнаружены дубли назначений сегмента.")
                owners[segment_id] = owner_id
            if mode == "MERGE":
                candidates = [
                    (sid, owner)
                    for sid, owner in owners.items()
                    if owner in sources and owner != target_id
                ]
            else:
                candidates = [(sid, owners.get(sid)) for k, sid in selected if k == kind]
            for sid, owner_id in candidates:
                record = records.get(sid)
                if record is None:
                    raise RouteMutationError(f"Физический сегмент {sid} отсутствует.")
                if owner_id == target_id:
                    if mode == "MOVE":
                        raise RouteMutationError("Сегмент уже находится в выбранной трубе.")
                    continue
                if owner_id and owner_id not in active:
                    raise RouteMutationError("Назначение ссылается на неактивную трубу.")
                if record.get("migration_state") != "CONFIRMED":
                    raise RouteMutationError(
                        "Сегмент без подтверждённой топологии нельзя переносить."
                    )
                if kind == "BUS" and record["connection_kind"] != "CABLE":
                    raise RouteMutationError("TRACK-соединение BUS не является физическим кабелем.")
                # Q03/Q06 physical conduit contract applies equally to
                # ordinary segments and the physical CABLE edges of BUS.
                if not record.get("mount_way"):
                    raise RouteMutationError("У сегмента не задан способ прокладки.")
                try:
                    valid = validate_line_conduit_fields(
                        mount_way=record["mount_way"],
                        conduit_type=target["conduit_type"],
                        conduit_color=target["color"] or "",
                        conduit_id=target["designation"],
                    )
                except ConduitContractError as exc:
                    raise RouteMutationError(f"Сегмент {sid}: {exc}") from exc
                if not valid:
                    raise RouteMutationError("?????? ????????? ?? ????????? ?????.")
                rows.append((kind, sid, owner_id, int(record["row_version"])))
        rows.sort()
        if not rows:
            raise RouteMutationError("Нет физических сегментов для операции.")
        if mode == "MERGE":
            for sid in sources:
                if sid == target_id:
                    continue
                candidate = active[sid]
                for attr in ("conduit_type", "diameter_mm_decimal", "color"):
                    left = str(target.get(attr) or "").strip().casefold()
                    right = str(candidate.get(attr) or "").strip().casefold()
                    if left != right:
                        raise RouteMutationError(
                            f"Трубы {target['designation']} и {candidate['designation']} "
                            f"различаются по {attr}; сначала согласуйте характеристики."
                        )
                # A manual route may be shared. Its length is not the sum of
                # member lengths; uncertain length is explicitly invalidated.
        touched = {target_id, *sources, *(row[2] for row in rows if row[2])}
        signatures = tuple(
            sorted(
                (
                    cid,
                    str(active[cid]["designation"]),
                    int(active[cid]["row_version"]),
                    str(active[cid].get("conduit_type") or ""),
                    str(active[cid].get("color") or ""),
                    str(active[cid].get("diameter_mm_decimal") or ""),
                    str(active[cid].get("length_m_decimal") or ""),
                )
                for cid in touched
            )
        )
        lengths = {
            str(active[cid].get("length_m_decimal"))
            for cid in touched
            if active[cid].get("length_m_decimal") not in (None, "")
        }
        warnings = [
            "Совпадение физических участков не может быть доказано по обозначениям. "
            "Подтвердите на плане, что кабели действительно проходят в общей трубе.",
            "Изменения выполняются только в Project; DWG автоматически не меняется.",
        ]
        if len(lengths) > 1:
            warnings.append(
                "Исходные длины труб различаются. Длина общей трубы будет помечена "
                "как требующая уточнения, а не сложена автоматически."
            )
        return RoutePlan(
            project_id,
            mode,
            target_id,
            tuple(sources),
            tuple(selected),
            tuple(rows),
            signatures,
            int(revision),
            tuple(warnings),
        )

    def apply(self, plan: RoutePlan, *, confirmed_same_physical_run: bool = False):
        if not confirmed_same_physical_run:
            raise RouteMutationError("Требуется подтверждение общего физического участка.")
        with UnitOfWork(self.engine) as uow:
            actual = self._plan(
                uow, plan.project_id, plan.mode, plan.target_id, plan.sources, plan.selected
            )
            if actual != plan:
                raise RouteMutationError(
                    "Данные изменились после предварительного просмотра. Обновите план."
                )
            target = (
                uow.execute(select(conduit).where(conduit.c.id == plan.target_id)).mappings().one()
            )
            now = datetime.now(UTC)
            cables = CableService(self.engine)
            for kind, segment_id, old_id, _version in plan.members:
                if kind == "CABLE":
                    result = (
                        uow.execute(
                            update(conduit_segment_assignment)
                            .where(
                                conduit_segment_assignment.c.project_id == plan.project_id,
                                conduit_segment_assignment.c.cable_segment_id == segment_id,
                                conduit_segment_assignment.c.conduit_id == old_id,
                            )
                            .values(
                                conduit_id=plan.target_id,
                                row_version=conduit_segment_assignment.c.row_version + 1,
                            )
                        )
                        if old_id
                        else None
                    )
                    if old_id is None:
                        uow.execute(
                            conduit_segment_assignment.insert().values(
                                id=new_id(),
                                project_id=plan.project_id,
                                conduit_id=plan.target_id,
                                cable_segment_id=segment_id,
                            )
                        )
                    elif result.rowcount != 1:
                        raise RouteMutationError("Назначение кабельного сегмента изменилось.")
                    cables._set_segment_conduit_facts(
                        uow,
                        plan.project_id,
                        segment_id,
                        conduit_type=target["conduit_type"],
                        color=target["color"] or "",
                        designation=target["designation"],
                        now=now,
                    )
                else:
                    result = (
                        uow.execute(
                            update(bus_segment_conduit_assignment)
                            .where(
                                bus_segment_conduit_assignment.c.project_id == plan.project_id,
                                bus_segment_conduit_assignment.c.bus_segment_id == segment_id,
                                bus_segment_conduit_assignment.c.conduit_id == old_id,
                            )
                            .values(
                                conduit_id=plan.target_id,
                                row_version=bus_segment_conduit_assignment.c.row_version + 1,
                            )
                        )
                        if old_id
                        else None
                    )
                    if old_id is None:
                        uow.execute(
                            bus_segment_conduit_assignment.insert().values(
                                id=new_id(),
                                project_id=plan.project_id,
                                conduit_id=plan.target_id,
                                bus_segment_id=segment_id,
                            )
                        )
                    elif result.rowcount != 1:
                        raise RouteMutationError("Назначение BUS-сегмента изменилось.")
                    uow.execute(
                        update(bus_segment)
                        .where(
                            bus_segment.c.id == segment_id,
                            bus_segment.c.project_id == plan.project_id,
                        )
                        .values(
                            gofra_type=target["conduit_type"],
                            gofra_color=target["color"],
                            gofra_id=target["designation"],
                            updated_at_utc=now,
                            row_version=bus_segment.c.row_version + 1,
                        )
                    )
            for source_id in plan.sources:
                if source_id == plan.target_id:
                    continue
                ordinary_count = uow.execute(
                    select(conduit_segment_assignment.c.id).where(
                        conduit_segment_assignment.c.conduit_id == source_id
                    )
                ).first()
                bus_count = uow.execute(
                    select(bus_segment_conduit_assignment.c.id).where(
                        bus_segment_conduit_assignment.c.conduit_id == source_id
                    )
                ).first()
                if ordinary_count or bus_count:
                    raise RouteMutationError("Исходная труба не пуста; операция отменена.")
                uow.execute(
                    update(conduit)
                    .where(conduit.c.id == source_id, conduit.c.project_id == plan.project_id)
                    .values(
                        lifecycle="RETIRED",
                        updated_at_utc=now,
                        row_version=conduit.c.row_version + 1,
                    )
                )
            lengths = {row[-1] for row in plan.conduits if row[-1]}
            if len(lengths) > 1:
                path = dict(target["path_json"] or {})
                path["length_source"] = "INCOMPLETE_SHARED"
                uow.execute(
                    update(conduit)
                    .where(conduit.c.id == plan.target_id)
                    .values(
                        length_m_decimal=None,
                        path_json=path,
                        row_version=conduit.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
            else:
                refresh_conduit_length(uow, plan.project_id, plan.target_id)
            for source_id in {row[2] for row in plan.members if row[2]} - set(plan.sources):
                refresh_conduit_length(uow, plan.project_id, source_id)
            uow.execute(
                update(project)
                .where(project.c.id == plan.project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=now,
                )
            )
            uow.commit()
