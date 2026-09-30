from __future__ import annotations

import pytest

from nl_project_2.cad_contract import CadObservationBatch
from nl_project_2.cad_sync import DwgSyncError, DwgSyncService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService


class _Port:
    request = None

    def read_observations(self, request):
        self.request = request
        return CadObservationBatch(request.expected_document_identity, ())


def test_scan_requires_confirmed_identity_and_sends_definition_allowlist(database):
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="Target", project_code="TARGET")
    )
    port = _Port()
    service = DwgSyncService(database.engine, port)

    with pytest.raises(DwgSyncError, match="must be confirmed"):
        service.scan_active(project_id=project_id)

    service.scan_active(project_id=project_id, expected_identity="C:/target.dwg")
    assert port.request.expected_document_identity == "C:/target.dwg"
    assert "SOCKET_IN" in port.request.definition_names
    assert port.request.deadline_seconds == 120.0
