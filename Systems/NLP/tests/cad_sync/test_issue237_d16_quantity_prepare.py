"""D16 selective immutable preparation: no legacy quantity or Conduit mutations."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows
from test_issue237_d15_line_preview import _approval

from nl_project_2.cables.transit_quantity_prepare import (
    TransitQuantityIntent,
    TransitQuantityPreparationError,
    prepare_approved_transit_quantities,
    prepared_transit_batch_sha256,
    read_prepared_transit_quantities,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    TRANSIT_PHYSICAL_STAGING_REVISION,
    current_revision_read_only,
    downgrade_database,
)
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
)


def _intent(database):
    approval = _approval(database)
    ev = approval.transit
    with database.engine.connect() as conn:
        line = (
            conn.execute(select(cable_line).where(cable_line.c.id == ev.cable_line_id))
            .mappings()
            .one()
        )
        fact = (
            conn.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.project_id == ev.project_id,
                    cable_length_fact.c.cable_line_id == ev.cable_line_id,
                )
            )
            .mappings()
            .one_or_none()
        )
    approval = replace(
        approval,
        additional_m=Decimal(str(fact["additional_length_m_decimal"] or 0)) if fact else Decimal(0),
        manual_full_m=(
            Decimal(str(fact["manual_full_length_m_decimal"]))
            if fact is not None and fact["manual_full_length_m_decimal"] is not None
            else None
        ),
    )
    return TransitQuantityIntent(
        approval=approval,
        expected_line_row_version=line["row_version"],
        expected_length_fact_id=fact["id"] if fact else None,
        expected_length_fact_row_version=fact["row_version"] if fact else None,
        acceptance_evidence="reviewed physical quantity inputs, synthetic fixture",
    )


def _prepare(database, *intents, token=None, confirmed=True):
    batch = tuple(intents)
    selection = frozenset(i.approval.transit.cable_line_id for i in batch)
    return prepare_approved_transit_quantities(
        database.engine,
        batch,
        selected_line_ids=selection,
        approved_batch_sha256=(
            token
            if token is not None
            else prepared_transit_batch_sha256(batch, selected_line_ids=selection)
        ),
        confirmed=confirmed,
    )


def _count(database):
    with database.engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(cable_transit_line_commit))


def test_approved_prep_receipt_is_idempotent_and_never_modifies_authoritative_data(database):
    intent = _intent(database)
    pid = intent.approval.transit.project_id
    watched = (
        cable_line,
        cable_segment,
        cable_length_fact,
        conduit,
        conduit_segment_assignment,
        cable_transit_route,
        cable_transit_span,
    )
    with database.engine.connect() as conn:
        original = {t.name: _canonical_rows(conn, t, pid) for t in watched}
    (first,) = _prepare(database, intent)
    assert first.newly_prepared
    assert len(first.approved_sha256) == 64
    assert _count(database) == 1
    (second,) = _prepare(database, intent)
    assert not second.newly_prepared
    assert second.record_id == first.record_id
    with database.engine.connect() as conn:
        rows = read_prepared_transit_quantities(conn, project_id=pid)
        assert len(rows) == 1
        assert rows[0]["state"] == "PREPARED_APPROVED"
        assert rows[0]["automatic_length_m_decimal"]
        assert rows[0]["calculation_snapshot_json"]["source"] == "AUTOMATIC"
        assert {t.name: _canonical_rows(conn, t, pid) for t in watched} == original
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    assert current_revision_read_only(database.path) == HEAD_REVISION


@pytest.mark.parametrize("problem", ["confirmation", "digest", "unknown_selection", "duplicate"])
def test_no_write_without_exact_explicit_selected_set(database, problem):
    intent = _intent(database)
    if problem == "confirmation":
        with pytest.raises(
            TransitQuantityPreparationError, match="TRANSIT_BATCH_APPROVAL_REQUIRED"
        ):
            _prepare(database, intent, confirmed=False)
    elif problem == "digest":
        with pytest.raises(
            TransitQuantityPreparationError, match="TRANSIT_BATCH_APPROVAL_REQUIRED"
        ):
            _prepare(database, intent, token="0" * 64)
    elif problem == "unknown_selection":
        with pytest.raises(TransitQuantityPreparationError, match="TRANSIT_SELECTION_NOT_EXACT"):
            prepare_approved_transit_quantities(
                database.engine,
                (intent,),
                selected_line_ids=frozenset({new_id()}),
                approved_batch_sha256="0" * 64,
                confirmed=True,
            )
    else:
        with pytest.raises(TransitQuantityPreparationError, match="TRANSIT_SELECTION_NOT_EXACT"):
            _prepare(database, intent, intent)
    assert _count(database) == 0


@pytest.mark.parametrize("problem", ["line_version", "segment_version", "length_version", "manual"])
def test_optimistic_change_or_manual_override_never_silently_replaced(database, problem):
    intent = _intent(database)
    ev = intent.approval.transit
    with database.engine.begin() as conn:
        if problem == "line_version":
            conn.execute(
                update(cable_line)
                .where(cable_line.c.id == ev.cable_line_id)
                .values(row_version=cable_line.c.row_version + 1)
            )
        elif problem == "segment_version":
            conn.execute(
                update(cable_segment)
                .where(cable_segment.c.id == ev.electrical_segment_id)
                .values(row_version=cable_segment.c.row_version + 1)
            )
        else:
            fact = (
                conn.execute(
                    select(cable_length_fact).where(
                        cable_length_fact.c.cable_line_id == ev.cable_line_id
                    )
                )
                .mappings()
                .one()
            )
            if problem == "length_version":
                conn.execute(
                    update(cable_length_fact)
                    .where(cable_length_fact.c.id == fact["id"])
                    .values(row_version=cable_length_fact.c.row_version + 1)
                )
            else:
                conn.execute(
                    update(cable_length_fact)
                    .where(cable_length_fact.c.id == fact["id"])
                    .values(manual_full_length_m_decimal="8.3")
                )
    with pytest.raises(
        TransitQuantityPreparationError,
        match="TRANSIT_(LINE_OWNER_CHANGED|ELECTRICAL_OWNER_CHANGED|LENGTH_FACT_CHANGED|MANUAL_OR_ADDITIONAL_CONFLICT)",
    ):
        _prepare(database, intent)
    assert _count(database) == 0


def test_explicit_existing_manual_override_is_carried_not_rewritten(database):
    intent = _intent(database)
    ev = intent.approval.transit
    with database.engine.begin() as conn:
        row = (
            conn.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.cable_line_id == ev.cable_line_id
                )
            )
            .mappings()
            .one()
        )
        conn.execute(
            update(cable_length_fact)
            .where(cable_length_fact.c.id == row["id"])
            .values(
                manual_full_length_m_decimal="8.3",
                row_version=cable_length_fact.c.row_version + 1,
            )
        )
    approval = replace(intent.approval, manual_full_m=Decimal("8.3"))
    intent = replace(
        intent,
        approval=approval,
        expected_length_fact_row_version=intent.expected_length_fact_row_version + 1,
    )
    (record,) = _prepare(database, intent)
    assert record.newly_prepared
    with database.engine.connect() as conn:
        fact = (
            conn.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.id == intent.expected_length_fact_id
                )
            )
            .mappings()
            .one()
        )
        prepared = read_prepared_transit_quantities(conn, project_id=ev.project_id)[0]
    assert fact["manual_full_length_m_decimal"] == "8.3"
    assert prepared["source"] == "MANUAL"
    assert Decimal(prepared["final_length_m_decimal"]) == Decimal("8.3")


def test_existing_canonical_conduit_conflict_stops_commit_without_any_mutation(database):
    intent = _intent(database)
    ev = intent.approval.transit
    with database.engine.begin() as conn:
        conn.execute(
            conduit.insert().values(
                id=new_id(),
                project_id=ev.project_id,
                designation="001.PND25",
                conduit_type="ПНД25",
                lifecycle="ACTIVE",
            )
        )
    with pytest.raises(
        TransitQuantityPreparationError,
        match="TRANSIT_QUANTITY_PREVIEW_REQUIRES_REVIEW",
    ):
        _prepare(database, intent)
    assert _count(database) == 0


def test_trigger_failure_rolls_back_new_prepared_receipt(database):
    intent = _intent(database)
    with database.engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER d16_abort BEFORE INSERT ON cable_transit_line_commit "
            "BEGIN SELECT RAISE(ABORT, 'forced D16 receipt failure'); END"
        )
    with pytest.raises(Exception, match="forced D16 receipt failure"):
        _prepare(database, intent)
    assert _count(database) == 0


def test_inconsistent_line_evidence_cannot_replace_existing_prepared_receipt(database):
    intent = _intent(database)
    _prepare(database, intent)
    altered = replace(intent, acceptance_evidence="different approved acceptance")
    with pytest.raises(TransitQuantityPreparationError, match="TRANSIT_PREPARED_COMMIT_CONFLICT"):
        _prepare(database, altered)
    assert _count(database) == 1


def test_populated_rev17_downgrade_rejected_before_ddl(database, tmp_path):
    intent = _intent(database)
    _prepare(database, intent)
    database.engine.dispose()
    with pytest.raises(
        RuntimeError, match="TRANSIT_LINE_COMMIT_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW"
    ):
        downgrade_database(
            database.path,
            tmp_path / "verified",
            target=TRANSIT_PHYSICAL_STAGING_REVISION,
        )
    assert current_revision_read_only(database.path) == HEAD_REVISION
    assert _count(database) == 1
