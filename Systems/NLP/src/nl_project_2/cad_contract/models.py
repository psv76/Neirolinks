"""Typed, transport-neutral CAD observation and validation DTOs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass(frozen=True, slots=True)
class CadAttribute:
    tag: str
    value: str


@dataclass(frozen=True, slots=True)
class BlockDefinitionMetadata:
    """Optional definition facts exposed by a CAD adapter; never geometry."""

    attribute_definition_tags: tuple[str, ...] | None = None
    is_dynamic: bool | None = None


@dataclass(frozen=True, slots=True)
class CadObservation:
    effective_name: str
    layer: str
    raw_attributes: tuple[CadAttribute, ...]
    x: int | float | str
    y: int | float | str
    handle: str
    definition: BlockDefinitionMetadata | None = None

    @classmethod
    def from_mapping(
        cls,
        *,
        effective_name: str,
        layer: str,
        raw_attributes: Mapping[str, Any],
        x: int | float | str,
        y: int | float | str,
        handle: str,
        definition: BlockDefinitionMetadata | None = None,
    ) -> CadObservation:
        return cls(
            effective_name=effective_name,
            layer=layer,
            raw_attributes=tuple(
                CadAttribute(tag=str(tag), value="" if value is None else str(value))
                for tag, value in raw_attributes.items()
            ),
            x=x,
            y=y,
            handle=handle,
            definition=definition,
        )


@dataclass(frozen=True, slots=True)
class CadObservationBatch:
    document_identity: str
    observations: tuple[CadObservation, ...]
    source_metadata: Mapping[str, Any] = field(default_factory=dict)


class IssueSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class CableSuffixKind(StrEnum):
    BASE = "BASE"
    POINT = "POINT"


@dataclass(frozen=True, slots=True)
class CableIdentity:
    raw: str
    base: str
    suffix_kind: CableSuffixKind
    suffix_order: int | None = None


@dataclass(frozen=True, slots=True)
class TaggedFact:
    tag: str
    value: str


@dataclass(frozen=True, slots=True)
class NormalizedCadReadPayload:
    """Read-only normalized facts retained for the next reconciliation block."""

    block_name: str
    device_type: str | None
    layer: str
    handle: str
    x: int | float | str
    y: int | float | str
    cable_identity: CableIdentity | None
    box_id: str | None = None
    cable_source: str | None = None
    bus_point_id: str | None = None
    bus_id: str | None = None
    bus_source: str | None = None
    bus_type: str | None = None
    cable_link_kind: str | None = None
    bus_link_kind: str | None = None
    derived_phase: int | None = None
    keys: tuple[TaggedFact, ...] = ()
    topology_outputs: tuple[TaggedFact, ...] = ()
    field_ports: tuple[TaggedFact, ...] = ()
    led_type: str | None = None
    route_fields: tuple[TaggedFact, ...] = ()
    bus_route_fields: tuple[TaggedFact, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: IssueSeverity
    blocks_acceptance: bool
    handle: str | None = None
    field: str | None = None
    related_handles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidatedObservation:
    observation: CadObservation
    normalized_attributes: Mapping[str, str]
    block_class: str
    device_type: str | None
    function_group: str | None
    ignored_project_data: bool = False
    read_payload: NormalizedCadReadPayload | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    observations: tuple[ValidatedObservation, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def is_acceptable(self) -> bool:
        return not any(issue.blocks_acceptance for issue in self.issues)

    @property
    def ignored_count(self) -> int:
        return sum(item.ignored_project_data for item in self.observations)
