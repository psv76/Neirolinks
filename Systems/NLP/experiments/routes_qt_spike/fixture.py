"""Synthetic read-only snapshot for NL Project 3.0 Routes A/B comparison.

These are NOT real project identifiers or measured quantities. Both variants
receive the same immutable snapshot. No database, CAD or network access.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Conduit:
    id: str
    designation: str
    source: str
    target: str
    pipe_type: str
    final_m: Optional[str]
    note: str = ""


@dataclass(frozen=True)
class Segment:
    id: str
    line: str
    source: str
    target: str
    conduit_id: Optional[str]
    geometry_m: Optional[str]
    cable: str
    mount: str
    tube_need: str = ""
    note: str = ""


@dataclass(frozen=True)
class Snapshot:
    conduits: tuple[Conduit, ...]
    segments: tuple[Segment, ...]


def load_fixture() -> Snapshot:
    # Naming intentionally follows familiar notation; ALL values are fictional.
    specs = (
        ("001.PND25", "ЩР-1", "BOX.001", "ПНД Ø25", "12", ""),
        ("002.PND25", "BOX.001", "Гостиная", "ПНД Ø25", "9", ""),
        ("003.PVH20", "ЩР-1", "BOX.002", "ПВХ Ø20", "17", ""),
        ("004.PND25", "ЩР-1", "BOX.001", "ПНД Ø25", "12", "Параллельная труба"),
        ("005.MR20", "ЩР-2", "BOX.005", "Металлорукав Ø20", "21", ""),
        ("006.PVH25", "BOX.005", "Кухня", "ПВХ Ø25", "8", ""),
        ("007.PND32", "ЩР-3", "BOX.011", "ПНД Ø32", "33", ""),
        ("008.PND25", "BOX.011", "Терраса", "ПНД Ø25", "14", ""),
        ("009.PVH16", "ЩР-1", "Спальня 2", "ПВХ Ø16", "11", ""),
        ("010.PND25", "ЩР-2", "BOX.007", "ПНД Ø25", "19", ""),
        ("011.PVH20", "BOX.007", "Санузел", "ПВХ Ø20", None, "Геометрия не рассчитана"),
        ("012.PND32", "ЩР-3", "BOX.012", "ПНД Ø32", "27", ""),
    )
    tubes = tuple(
        Conduit(f"tube-{i:03d}", designation, source, target, kind, length, note)
        for i, (designation, source, target, kind, length, note) in enumerate(specs, 1)
    )
    geometry_by_tube = (
        "10", "7.3", "14", "10", "18", "6", "28", "12", "9",
        "16", None, "23",
    )
    segments = []
    index = 0
    counts = (3, 2, 2, 1, 3, 2, 3, 2, 2, 2, 1, 3)
    for tube, count, geometry in zip(tubes, counts, geometry_by_tube):
        for n in range(count):
            index += 1
            # Same physical bounds per conduit; one physical cable per segment.
            source, target = (tube.source, tube.target) if n % 2 == 0 else (tube.target, tube.source)
            segments.append(
                Segment(
                    id=f"segment-{index:03d}",
                    line=f"{100 + index}",
                    source=source, target=target,
                    conduit_id=tube.id,
                    geometry_m=geometry,
                    cable="ВВГнг(А)-LS 3×2,5" if index % 3 else "UTP Cat5e медь",
                    mount="В полу" if index % 3 else "В стене",
                    note="Общий физический участок · тестовые данные" if count > 1 else "",
                )
            )
    needs = (
        ("Требуется", "В полу"), ("Не требуется", "Открыто"),
        ("Не определено", "—"), ("Требуется", "В брусе"),
        ("Не требуется", "В кабель-канале"), ("Не определено", "—"),
        ("Требуется", "В полу"), ("Не требуется", "Открыто"),
        ("Требуется", "В полу"), ("Не определено", "—"),
        ("Не требуется", "Открыто"), ("Требуется", "В полу"),
    )
    for n, (need, mount) in enumerate(needs, 1):
        index += 1
        segments.append(
            Segment(
                id=f"segment-{index:03d}",
                line=str(500 + n) if n != 10 else "590.01 Очень длинное обозначение линии",
                source="ЩР-1" if n % 2 else "BOX.011",
                target=f"Помещение {n} · светильник / привод / датчик",
                conduit_id=None,
                geometry_m=None if need == "Не определено" else str(3 + n),
                cable="ВВГнг(А)-LS 3×1,5" if n % 2 else "UTP Cat6",
                mount=mount,
                tube_need=need,
                note="Прокладка без трубы разрешена" if need == "Не требуется" else (
                    "Нужна проверка способа прокладки" if need == "Не определено" else "Требуется труба"
                ),
            )
        )
    return Snapshot(tubes, tuple(segments))
