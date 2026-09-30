"""Repeatable TASK_022 performance probe over an isolated control dataset."""

from __future__ import annotations

import gc
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from time import perf_counter

import sqlalchemy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nl_project_2.buses.domain import TopologyPoint, branched_topology  # noqa: E402
from nl_project_2.cad_contract import (  # noqa: E402
    BlockDefinitionMetadata,
    CadContractValidator,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.catalog.equipment import EquipmentService  # noqa: E402
from nl_project_2.config import PathConfig  # noqa: E402
from nl_project_2.objects.models import ProjectCard  # noqa: E402
from nl_project_2.objects.runtime import ApplicationRuntime  # noqa: E402

CONTROL_COUNT = 100
GRAPH_COUNT = 90


def _timed(operation):
    started = perf_counter()
    value = operation()
    return value, round((perf_counter() - started) * 1000, 3)


def _paths(root: Path) -> PathConfig:
    return PathConfig(
        app_root=PROJECT_ROOT,
        backup_root=root / "backups",
        release_root=root / "releases",
        user_projects_root=root / "projects",
        local_state_root=root / "state",
    )


def _remove_probe_directory(root: Path) -> None:
    resolved = root.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if resolved.parent != temp_root or not resolved.name.startswith("nlp2-task022-"):
        raise RuntimeError("Refusing to remove a directory outside the probe temp scope")
    for attempt in range(20):
        if not resolved.exists():
            return
        try:
            shutil.rmtree(resolved)
            return
        except PermissionError:
            if attempt == 19:
                raise
            gc.collect()
            time.sleep(0.1)


def _cad_batch() -> CadObservationBatch:
    observations = []
    for index in range(CONTROL_COUNT):
        cable_id = f"{index + 1:03}.01"
        attributes = {
            "DEVICE_TYPE": "SOCKET",
            "DEVICE_NAME": f"Synthetic socket {index + 1}",
            "BUILDING": "Synthetic",
            "ROOM": "Room",
            "MOUNT_HEIGHT": "300",
            "CABLE_ID": cable_id,
            "CABLE_TYPE": "NYM",
            "BOARD": "B.01",
            "LOAD_TYPE": "SOCKET_LIVING_LOW",
            "LOAD_NAME": "Synthetic load",
        }
        observations.append(
            CadObservation.from_mapping(
                effective_name="SOCKET_IN",
                layer="POWER",
                raw_attributes=attributes,
                x=index * 100,
                y=0,
                handle=f"P{index + 1:X}",
                definition=BlockDefinitionMetadata(tuple(attributes), False),
            )
        )
    return CadObservationBatch(
        document_identity="fixture://task-022/control-100",
        observations=tuple(observations),
        source_metadata={"adapter_version": "performance-probe", "protocol_version": "1.0"},
    )


def run() -> dict:
    with tempfile.TemporaryDirectory(
        prefix="nlp2-task022-", ignore_cleanup_errors=True
    ) as raw_root:
        root = Path(raw_root)
        paths = _paths(root)
        runtime, cold_start = _timed(lambda: ApplicationRuntime.open(paths))
        runtime.close()
        runtime, warm_start = _timed(lambda: ApplicationRuntime.open(paths))
        project_id = runtime.objects.create_project(
            ProjectCard(name="Synthetic performance project", project_code="PERF-022")
        )
        equipment = EquipmentService(runtime.database.engine)
        for index in range(CONTROL_COUNT):
            equipment.create_instance(
                project_id=project_id,
                designation=f"QF.PERF.{index + 1}",
                passport_key="protection.circuit_breaker.1p",
                product_key="product.schneider.a9f84116",
                supply_scope="NEIROLINKS",
            )

        _detail, object_open = _timed(lambda: runtime.open_project(project_id))
        _rows, constructor_section = _timed(lambda: runtime.constructor.list_instances(project_id))
        _spec, specification_recalculation = _timed(lambda: runtime.specification.build(project_id))
        _issues, full_validation = _timed(
            lambda: runtime.integrated_ui.validation_items(project_id)
        )
        validator = CadContractValidator(load_contract())
        _validation, fixture_scan = _timed(lambda: validator.validate(_cad_batch()))
        points = tuple(
            TopologyPoint(f"resource-{index}", f"100.{index + 1:02}", index, index)
            for index in range(GRAPH_COUNT)
        )
        _graph, graph_rebuild = _timed(
            lambda: branched_topology(
                "root",
                "100",
                points,
                branches=(tuple(point.point_id for point in points),),
            )
        )
        _state, main_view_switch = _timed(
            lambda: [runtime.navigate_within_project(index % 8) for index in range(100)]
        )
        backup, backup_ms = _timed(runtime.manual_backup)
        _restore, restore_ms = _timed(
            lambda: runtime.backup_service.restore_to(
                backup.path, root / "restore" / "restored.sqlite"
            )
        )
        runtime.close()
        time.sleep(0.2)

        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        _process, package_cold_start = _timed(
            lambda: subprocess.run(
                [sys.executable, "-c", "import nl_project_2; print(nl_project_2.__name__)"],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
        )
    _remove_probe_directory(Path(raw_root))

    measurements = {
        "cold_start": cold_start,
        "warm_start": warm_start,
        "object_open": object_open,
        "constructor_section": constructor_section,
        "specification_full_recalculation": specification_recalculation,
        "full_validation": full_validation,
        "fixture_scan_validation": fixture_scan,
        "graph_rebuild": graph_rebuild,
        "main_view_switch_100": main_view_switch,
        "manual_backup": backup_ms,
        "restore": restore_ms,
        "package_cold_start": package_cold_start,
    }
    threshold_payload = json.loads(
        (PROJECT_ROOT / "resources" / "performance_thresholds.json").read_text(encoding="utf-8")
    )
    thresholds = threshold_payload["thresholds_ms"]
    checks = {
        name: {
            "measured_ms": value,
            "threshold_ms": thresholds[name],
            "status": "PASS" if value <= thresholds[name] else "FAIL",
        }
        for name, value in measurements.items()
    }
    return {
        "status": "PASSED" if all(row["status"] == "PASS" for row in checks.values()) else "FAILED",
        "metadata": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "sqlalchemy": sqlalchemy.__version__,
            "control_project_instances": CONTROL_COUNT,
            "control_cad_observations": CONTROL_COUNT,
            "control_graph_points": GRAPH_COUNT,
        },
        "measurements_ms": measurements,
        "checks": checks,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASSED" else 1)
