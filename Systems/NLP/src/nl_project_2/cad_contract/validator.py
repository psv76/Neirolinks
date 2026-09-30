"""Pure validation of AutoCAD observation metadata against the approved contract."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from nl_project_2.cables.domain import (
    LINE_CONDUIT_ATTRIBUTES,
    ConduitContractError,
    conduit_is_present,
    parse_conduit_id,
)

from .catalog import BlockContractCatalog, BlockRule
from .models import (
    CableIdentity,
    CableSuffixKind,
    CadObservation,
    CadObservationBatch,
    IssueSeverity,
    NormalizedCadReadPayload,
    TaggedFact,
    ValidatedObservation,
    ValidationIssue,
    ValidationResult,
)

_ATTRIBUTE_TAG = re.compile(r"^[A-Z][A-Z0-9_]*$")
_STANDARD_CABLE_ID = re.compile(r"^[1-9][0-9]{2}(?:\.[0-9]{2})?$")
_BASE_CABLE_ID = re.compile(r"^[1-9][0-9]{2}$")
_POINT_CABLE_ID = re.compile(r"^(?P<base>[1-9][0-9]{2})\.(?P<order>[0-9]{2})$")
_BOX_ID = re.compile(r"^BOX\.[0-9]{3}$")
_EL_BOX_CABLE_ID = re.compile(r"^(?P<base>[1-9][0-9]{2})\.RK(?P<order>[1-9][0-9]*)$")
_CABLE_SOURCE = re.compile(
    r"^(?:BOX\.[0-9]{3}|[1-9][0-9]{2}\.[0-9]{2}|"
    r"[1-9][0-9]{2}\.[0-9]{3}/(?:COM1|COM2|K1|K2|IN_1|IN_2|W1|W2))$"
)
_FIELD_PORT_REFERENCE = re.compile(r"^(?:BOX\.[0-9]{3}|[1-8][0-9]{2}(?:\.[0-9]{2})?)$")
_BUS_POINT_ID = re.compile(r"^(?P<bus>9[0-9]{2})\.(?P<order>[0-9]{3})$")
_KEY_SOURCE_REFERENCE = re.compile(r"^(?P<cable>[1-9][0-9]{2}(?:\.[0-9]{2})?)/(?P<tag>KEY_[1-4])$")
_DALI_GROUP_ID = re.compile(r"^D\.[0-9]{3}$")
_LIGHTING_DEVICE_TYPES = frozenset({"LIGHT", "LIGHT_LED", "TRACK_230V", "TRACK_48V", "TRACK_DALI"})


@dataclass(slots=True)
class _BatchFacts:
    board_roles: dict[str, str]
    dali_groups: set[str]
    base_cables: set[str]
    key_references: list[tuple[str, str, str]]
    line_rows: dict[str, list[tuple[str, str, str, str, str]]]
    conduit_rows: dict[str, list[tuple[str, str, str]]]
    point_rows: dict[str, list[tuple[str, str, str, str, str, str, str, str, str, str]]]
    identity_handles: dict[str, list[str]]
    key_source_handles: dict[str, list[str]]
    special_references: list[tuple[str, str, str, str]]
    el_box_outputs: list[tuple[str, str, str, str]]
    switch_rows: dict[str, list[tuple[int | None, str, tuple[str, ...], str]]]
    frame_rows: list[tuple[str, str, int, bool]]
    mechanism_rows: list[tuple[str, str, bool]]
    av_identity_handles: dict[tuple[str, str], list[str]]
    av_rows: list[tuple[str, str, str]]
    source_rows: list[tuple[str, str, str]]
    box_handles: dict[str, list[str]]
    bus_rows: list[tuple[str, str, str, str, str]]
    port_identities: set[str]

    @classmethod
    def empty(cls) -> _BatchFacts:
        return cls(
            {},
            set(),
            set(),
            [],
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
            defaultdict(list),
            [],
            [],
            defaultdict(list),
            [],
            [],
            defaultdict(list),
            [],
            [],
            defaultdict(list),
            [],
            set(),
        )


class CadContractValidator:
    def __init__(self, catalog: BlockContractCatalog) -> None:
        self.catalog = catalog
        self._owned_attribute_tags = frozenset(
            tag
            for rule in catalog.blocks.values()
            for tag in (
                set(rule.required_attributes)
                | set(rule.required_definition_attributes)
                | set(rule.optional_attributes)
            )
        )

    def validate(self, batch: CadObservationBatch) -> ValidationResult:
        issues: list[ValidationIssue] = []
        validated: list[ValidatedObservation] = []
        facts = _BatchFacts.empty()
        if not batch.document_identity:
            issues.append(
                self._issue("DOCUMENT_IDENTITY_REQUIRED", "document identity is required")
            )

        handle_counts = Counter(
            observation.handle
            for observation in batch.observations
            if observation.effective_name != "ROOM_NAME"
            and observation.handle
            and self._claims_contract(observation)
        )
        for handle, count in sorted(handle_counts.items()):
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_DWG_HANDLE",
                        f"DWG handle {handle!r} occurs {count} times",
                        handle=handle,
                        field="DWG_HANDLE",
                    )
                )

        for observation in batch.observations:
            item, item_issues = self._validate_observation(observation, facts)
            validated.append(item)
            issues.extend(item_issues)

        issues.extend(self._validate_batch_facts(facts, batch.source_metadata))
        return ValidationResult(observations=tuple(validated), issues=tuple(issues))

    def _validate_observation(
        self, observation: CadObservation, facts: _BatchFacts
    ) -> tuple[ValidatedObservation, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        name = observation.effective_name
        if not self._claims_contract(observation):
            return (
                ValidatedObservation(
                    observation,
                    {},
                    "UNMANAGED",
                    None,
                    None,
                    ignored_project_data=True,
                ),
                issues,
            )
        if not self.catalog.block_name_pattern.fullmatch(name):
            issues.append(
                self._issue(
                    "BLOCK_NAME_FORMAT",
                    f"block name {name!r} does not match the approved format",
                    observation,
                    "BLOCK_NAME",
                )
            )
        rule = self.catalog.block(name)
        if rule is None:
            issues.append(
                self._issue(
                    "UNKNOWN_BLOCK_NAME",
                    f"block name {name!r} is absent from the approved catalog",
                    observation,
                    "BLOCK_NAME",
                )
            )
            return (
                ValidatedObservation(observation, {}, "UNKNOWN", None, None),
                issues,
            )

        if rule.ignored_project_data:
            return (
                ValidatedObservation(
                    observation,
                    {},
                    rule.block_class,
                    None,
                    None,
                    ignored_project_data=True,
                ),
                issues,
            )

        if not observation.handle:
            issues.append(
                self._issue(
                    "DWG_HANDLE_REQUIRED",
                    "DWG handle is required",
                    observation,
                    "DWG_HANDLE",
                )
            )
        for field, value in (("X", observation.x), ("Y", observation.y)):
            if not _is_finite_number(value):
                issues.append(
                    self._issue(
                        "COORDINATE_NOT_FINITE",
                        f"{field} must be a finite number",
                        observation,
                        field,
                    )
                )

        attributes, tag_issues = self._attributes(observation)
        issues.extend(tag_issues)
        normalized = dict(attributes)

        if rule.block_class == "LOGICAL":
            issues.extend(self._validate_logical(observation, rule, attributes, facts))
            return (
                ValidatedObservation(
                    observation,
                    normalized,
                    rule.block_class,
                    None,
                    None,
                ),
                issues,
            )

        function_group = self._function_group(observation, rule, issues)
        if function_group == "AV" and "CABLE_ID" in normalized:
            normalized["CABLE_ID"] = normalized["CABLE_ID"].strip().upper()

        required = set(rule.required_attributes)
        required_definitions = set(rule.required_definition_attributes)
        if function_group == "AV":
            required.update(self.catalog.av_rules["required"])
        if rule.device_type == "BOARD":
            role = normalized.get("LOAD_TYPE", "")
            if role in self.catalog.board_rules["feed_required_roles"]:
                required.update(self.catalog.board_rules["feed_attributes"])
                required_definitions.update(self.catalog.board_rules["feed_attributes"])

        av_nonblocking = function_group == "AV"
        av_incomplete_fields = set(self.catalog.av_rules["required"])
        issues.extend(
            self._validate_attributes(
                observation,
                rule,
                attributes,
                required,
                required_definitions,
                nonblocking_missing=av_incomplete_fields if av_nonblocking else set(),
            )
        )
        issues.extend(self._validate_numeric_attributes(observation, attributes))

        issues.extend(self._validate_load_type(observation, rule, function_group, normalized))
        issues.extend(self._validate_posts_and_keys(observation, rule, normalized, facts))
        issues.extend(self._validate_special_attributes(observation, rule, normalized, facts))
        issues.extend(self._validate_line_conduit(observation, normalized))
        issues.extend(
            self._collect_line_facts(observation, rule, function_group, normalized, facts)
        )
        self._collect_board_fact(observation, rule, normalized, facts, issues)
        self._collect_frame_mechanism_fact(observation, rule, normalized, facts)

        return (
            ValidatedObservation(
                observation,
                normalized,
                rule.block_class,
                rule.device_type,
                function_group,
                read_payload=self._read_payload(observation, rule, normalized),
            ),
            issues,
        )

    def _claims_contract(self, observation: CadObservation) -> bool:
        """Return true only for approved blocks or explicit NL attribute claimants."""

        if observation.effective_name in self.catalog.approved_block_names:
            return True
        tags = {attribute.tag for attribute in observation.raw_attributes}
        if observation.definition is not None:
            tags.update(observation.definition.attribute_definition_tags or ())
        return bool(tags & self._owned_attribute_tags)

    def _attributes(
        self, observation: CadObservation
    ) -> tuple[dict[str, str], list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        result: dict[str, str] = {}
        counts = Counter(attribute.tag for attribute in observation.raw_attributes)
        for tag, count in sorted(counts.items()):
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_ATTRIBUTE_TAG",
                        f"attribute tag {tag!r} occurs {count} times",
                        observation,
                        tag,
                    )
                )
        for attribute in observation.raw_attributes:
            if not _ATTRIBUTE_TAG.fullmatch(attribute.tag):
                issues.append(
                    self._issue(
                        "ATTRIBUTE_TAG_FORMAT",
                        f"attribute tag {attribute.tag!r} is not canonical uppercase",
                        observation,
                        attribute.tag,
                    )
                )
            result.setdefault(attribute.tag, attribute.value)
        return result, issues

    def _validate_attributes(
        self,
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        required: set[str],
        required_definitions: set[str],
        *,
        nonblocking_missing: set[str],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        allowed = required | set(rule.optional_attributes)
        for tag in sorted(required):
            if tag not in attributes or not attributes[tag]:
                issues.append(
                    self._issue(
                        "REQUIRED_ATTRIBUTE_MISSING",
                        f"required attribute {tag} is absent or empty",
                        observation,
                        tag,
                        blocks_acceptance=tag not in nonblocking_missing,
                    )
                )
        for tag in sorted(attributes):
            if tag in rule.forbidden_attributes:
                code = (
                    "EL_BOX_IN_FORBIDDEN"
                    if rule.device_type == "EL_BOX" and tag == "IN"
                    else "FORBIDDEN_ATTRIBUTE"
                )
                issues.append(
                    self._issue(
                        code,
                        f"attribute {tag} is forbidden for {rule.name}",
                        observation,
                        tag,
                    )
                )
            elif self._is_forbidden(tag):
                issues.append(
                    self._issue(
                        "FORBIDDEN_ATTRIBUTE",
                        f"attribute {tag} is forbidden by the plan-block contract",
                        observation,
                        tag,
                    )
                )
            elif tag not in allowed:
                issues.append(
                    self._issue(
                        "UNDECLARED_ATTRIBUTE",
                        f"attribute {tag} is not declared for {rule.name}",
                        observation,
                        tag,
                    )
                )

        definition = observation.definition
        if definition is None or definition.attribute_definition_tags is None:
            return issues
        definitions = definition.attribute_definition_tags
        definition_counts = Counter(definitions)
        for tag, count in sorted(definition_counts.items()):
            if count > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_ATTRIBUTE_DEFINITION",
                        f"attribute definition {tag!r} occurs {count} times",
                        observation,
                        tag,
                    )
                )
        definition_set = set(definitions)
        for tag in definitions:
            if not _ATTRIBUTE_TAG.fullmatch(tag):
                issues.append(
                    self._issue(
                        "ATTRIBUTE_DEFINITION_TAG_FORMAT",
                        f"attribute definition tag {tag!r} is not canonical uppercase",
                        observation,
                        tag,
                    )
                )
            if self._is_forbidden(tag):
                issues.append(
                    self._issue(
                        "FORBIDDEN_ATTRIBUTE_DEFINITION",
                        f"attribute definition {tag} is forbidden",
                        observation,
                        tag,
                    )
                )
            elif tag not in allowed:
                issues.append(
                    self._issue(
                        "UNDECLARED_ATTRIBUTE_DEFINITION",
                        f"attribute definition {tag} is not declared for {rule.name}",
                        observation,
                        tag,
                    )
                )
        for tag in sorted(required_definitions - definition_set):
            issues.append(
                self._issue(
                    "REQUIRED_ATTRIBUTE_DEFINITION_MISSING",
                    f"canonical definition is missing required tag {tag}",
                    observation,
                    tag,
                    blocks_acceptance=tag not in nonblocking_missing,
                )
            )
        for tag in sorted(set(attributes) - definition_set):
            issues.append(
                self._issue(
                    "ATTRIBUTE_NOT_IN_DEFINITION",
                    f"insertion attribute {tag} is absent from definition metadata",
                    observation,
                    tag,
                )
            )
        return issues

    def _validate_line_conduit(
        self, observation: CadObservation, attributes: dict[str, str]
    ) -> list[ValidationIssue]:
        if not attributes.get("CABLE_ID") or not set(LINE_CONDUIT_ATTRIBUTES).issubset(attributes):
            return []
        issues: list[ValidationIssue] = []
        definition_tags = (
            None
            if observation.definition is None
            else observation.definition.attribute_definition_tags
        )
        del definition_tags

        mount_way = attributes["MOUNT_WAY"].strip()
        conduit_type = attributes["GOFRA_TYPE"].strip()
        conduit_color = attributes["GOFRA_COLOR"].strip()
        conduit_id = attributes["GOFRA_ID"].strip()
        try:
            present = conduit_is_present(mount_way, conduit_type)
        except ConduitContractError as exc:
            message = str(exc)
            if message.startswith("MOUNT_WAY"):
                code, field = "MOUNT_WAY_NOT_ALLOWED", "MOUNT_WAY"
            elif "required" in message:
                code, field = "GOFRA_TYPE_REQUIRED", "GOFRA_TYPE"
            elif "must be empty" in message:
                code, field = "GOFRA_TYPE_NOT_EMPTY", "GOFRA_TYPE"
            else:
                code, field = "GOFRA_TYPE_FORMAT", "GOFRA_TYPE"
            issues.append(self._issue(code, message, observation, field))
            return issues

        if not present and (conduit_color or conduit_id):
            issues.append(
                self._issue(
                    "GOFRA_FIELDS_WITHOUT_CONDUIT",
                    "GOFRA_COLOR and GOFRA_ID must be empty when no conduit exists",
                    observation,
                    "GOFRA_ID" if conduit_id else "GOFRA_COLOR",
                )
            )
            return issues
        if conduit_id:
            try:
                parse_conduit_id(conduit_id, conduit_type)
            except ConduitContractError as exc:
                message = str(exc)
                code = (
                    "GOFRA_ID_FORMAT"
                    if message.startswith("GOFRA_ID must match")
                    else "GOFRA_ID_TYPE_MISMATCH"
                )
                issues.append(self._issue(code, message, observation, "GOFRA_ID"))
        return issues

    def _validate_logical(
        self,
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        facts: _BatchFacts,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if observation.layer != rule.logical_layer:
            issues.append(
                self._issue(
                    "LOGICAL_LAYER_MISMATCH",
                    f"{rule.name} must be on layer {rule.logical_layer}",
                    observation,
                    "LAYER",
                )
            )
        issues.extend(
            self._validate_attributes(
                observation,
                rule,
                attributes,
                set(rule.required_attributes),
                set(rule.required_definition_attributes),
                nonblocking_missing=set(),
            )
        )
        if rule.dynamic_if_metadata_available:
            dynamic = observation.definition.is_dynamic if observation.definition else None
            if dynamic is False:
                issues.append(
                    self._issue(
                        "DALI_GROUP_NOT_DYNAMIC",
                        "DALI_GROUP definition metadata says the block is not dynamic",
                        observation,
                        "IS_DYNAMIC",
                    )
                )
        identifier = attributes.get("DALI_GROUP_ID", "")
        if identifier and not _DALI_GROUP_ID.fullmatch(identifier):
            issues.append(
                self._issue(
                    "DALI_GROUP_ID_FORMAT",
                    "DALI_GROUP_ID must match D.YYY",
                    observation,
                    "DALI_GROUP_ID",
                )
            )
        elif identifier:
            if identifier in facts.dali_groups:
                issues.append(
                    self._issue(
                        "DUPLICATE_DALI_GROUP_ID",
                        f"DALI_GROUP_ID {identifier} is not unique",
                        observation,
                        "DALI_GROUP_ID",
                    )
                )
            facts.dali_groups.add(identifier)
        return issues

    def _function_group(
        self,
        observation: CadObservation,
        rule: BlockRule,
        issues: list[ValidationIssue],
    ) -> str | None:
        candidates = self.catalog.groups_for_layer(observation.layer) & rule.allowed_groups
        if len(candidates) != 1:
            issues.append(
                self._issue(
                    "LAYER_FUNCTION_GROUP_MISMATCH",
                    f"layer {observation.layer!r} is not an approved unique group for {rule.name}",
                    observation,
                    "LAYER",
                )
            )
            return None
        return next(iter(candidates))

    def _validate_numeric_attributes(
        self, observation: CadObservation, attributes: dict[str, str]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for tag, kind in self.catalog.numeric_attributes.items():
            if tag not in attributes or not attributes[tag]:
                continue
            value = _decimal(attributes[tag])
            invalid = value is None
            if value is not None and kind == "NON_NEGATIVE_DECIMAL":
                invalid = value < 0
            elif value is not None and kind == "POSITIVE_DECIMAL":
                invalid = value <= 0
            elif value is not None and kind == "POSITIVE_INTEGER":
                invalid = value <= 0 or value != value.to_integral_value()
            if invalid:
                issues.append(
                    self._issue(
                        "NUMERIC_ATTRIBUTE_FORMAT",
                        f"{tag} must satisfy {kind}",
                        observation,
                        tag,
                    )
                )
        return issues

    def _validate_load_type(
        self,
        observation: CadObservation,
        rule: BlockRule,
        function_group: str | None,
        attributes: dict[str, str],
    ) -> list[ValidationIssue]:
        value = attributes.get("LOAD_TYPE", "")
        if not value:
            return []
        allowed = (
            self.catalog.load_types["AV"] if function_group == "AV" else rule.allowed_load_types
        )
        if value and not allowed:
            return [
                self._issue(
                    "LOAD_TYPE_NOT_ALLOWED",
                    "LOAD_TYPE is not used by this canonical block",
                    observation,
                    "LOAD_TYPE",
                )
            ]
        if allowed and value not in allowed:
            return [
                self._issue(
                    "LOAD_TYPE_NOT_ALLOWED",
                    f"LOAD_TYPE={value!r} is not approved for this block context",
                    observation,
                    "LOAD_TYPE",
                    blocks_acceptance=function_group != "AV",
                )
            ]
        return []

    def _validate_posts_and_keys(
        self,
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        facts: _BatchFacts,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for index in range(1, rule.key_count + 1):
            tag = f"KEY_{index}"
            value = attributes.get(tag, "")
            cable_id = attributes.get("CABLE_ID", "")
            if cable_id and _STANDARD_CABLE_ID.fullmatch(cable_id):
                facts.key_source_handles[f"{cable_id}/{tag}"].append(observation.handle)
                facts.key_source_handles[f"{cable_id[:3]}/{tag}"].append(observation.handle)
            if not value:
                continue
            if _BASE_CABLE_ID.fullmatch(value):
                facts.key_references.append((observation.handle, tag, value))
            elif _DALI_GROUP_ID.fullmatch(value):
                facts.key_references.append((observation.handle, tag, value))
            else:
                issues.append(
                    self._issue(
                        "KEY_TARGET_FORMAT",
                        f"{tag} must be a base XYY cable or D.YYY group",
                        observation,
                        tag,
                    )
                )
        return issues

    def _validate_special_attributes(
        self,
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        facts: _BatchFacts,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cable_id = attributes.get("CABLE_ID", "")
        legacy_box_id = _EL_BOX_CABLE_ID.fullmatch(cable_id)
        if rule.device_type == "EL_BOX" and ".RK" in cable_id:
            if legacy_box_id is None:
                issues.append(
                    self._issue(
                        "EL_BOX_CABLE_ID_REQUIRED",
                        "legacy EL_BOX identity is invalid; migrate to BOX_ID=BOX.NNN",
                        observation,
                        "CABLE_ID",
                    )
                )
            else:
                facts.identity_handles[cable_id].append(observation.handle)
        elif rule.device_type != "EL_BOX" and ".RK" in cable_id:
            issues.append(
                self._issue(
                    "EL_BOX_SUFFIX_NOT_ALLOWED",
                    "legacy .RKn is reserved for explicit EL_BOX migration",
                    observation,
                    "CABLE_ID",
                )
            )
        box_id = attributes.get("BOX_ID", "").strip()
        if box_id and not _BOX_ID.fullmatch(box_id):
            issues.append(
                self._issue(
                    "BOX_ID_FORMAT",
                    "BOX_ID must match BOX.NNN",
                    observation,
                    "BOX_ID",
                )
            )
        elif box_id:
            facts.box_handles[box_id].append(observation.handle)

        if rule.device_type == "EL_BOX" and legacy_box_id is not None:
            for index in range(1, 6):
                tag = f"OUT_{index}"
                target = attributes.get(tag, "").strip()
                if target:
                    facts.el_box_outputs.append((observation.handle, cable_id, tag, target))

        source = attributes.get("CABLE_SOURCE", "").strip()
        if source and not _CABLE_SOURCE.fullmatch(source):
            issues.append(
                self._issue(
                    "CABLE_SOURCE_FORMAT",
                    "CABLE_SOURCE must be BOX.NNN, XYY.ZZ or 9YY.ZZZ/PORT",
                    observation,
                    "CABLE_SOURCE",
                )
            )
        elif source:
            facts.source_rows.append((observation.handle, cable_id, source))

        bus_point_id = attributes.get("BUS_POINT_ID", "").strip()
        bus_source = attributes.get("BUS_SOURCE", "").strip()
        if bus_point_id:
            match = _BUS_POINT_ID.fullmatch(bus_point_id)
            if match is None:
                issues.append(
                    self._issue(
                        "BUS_POINT_ID_FORMAT",
                        "BUS_POINT_ID must match 9YY.ZZZ",
                        observation,
                        "BUS_POINT_ID",
                    )
                )
            elif match.group("order") == "000":
                issues.append(
                    self._issue(
                        "BUS_ROOT_RESERVED",
                        ".000 is reserved for the Project-owned bus root",
                        observation,
                        "BUS_POINT_ID",
                    )
                )
            else:
                bus_kind = (
                    "DALI" if "BUS_SOURCE" in rule.required_definition_attributes else "RS485"
                )
                facts.bus_rows.append(
                    (
                        observation.handle,
                        bus_point_id,
                        bus_source,
                        bus_kind,
                        attributes.get("BUS_CABLE_TYPE", ""),
                    )
                )
                if bus_kind == "DALI":
                    if not bus_source or _BUS_POINT_ID.fullmatch(bus_source) is None:
                        issues.append(
                            self._issue(
                                "BUS_SOURCE_FORMAT",
                                "DALI BUS_SOURCE must match 9YY.ZZZ",
                                observation,
                                "BUS_SOURCE",
                            )
                        )
                elif bus_source:
                    issues.append(
                        self._issue(
                            "RS485_BUS_SOURCE_FORBIDDEN",
                            "RS-485 blocks do not declare BUS_SOURCE",
                            observation,
                            "BUS_SOURCE",
                        )
                    )

        if rule.device_type == "LIGHT_LED":
            led_type = attributes.get("LED_TYPE", "")
            if led_type and led_type not in {"MONO", "CCT", "RGB", "RGBW"}:
                issues.append(
                    self._issue(
                        "LED_TYPE_NOT_ALLOWED",
                        "LED_TYPE must be MONO, CCT, RGB or RGBW; MIX is not accepted",
                        observation,
                        "LED_TYPE",
                    )
                )

        if rule.name == "WB_MRM2_MINI":
            for tag in ("COM1", "COM2", "K1", "K2", "IN_1", "IN_2"):
                if bus_point_id:
                    facts.port_identities.add(f"{bus_point_id}/{tag}")
                target = attributes.get(tag, "").strip()
                if not target:
                    continue
                if not _FIELD_PORT_REFERENCE.fullmatch(target):
                    issues.append(
                        self._issue(
                            "FIELD_PORT_REFERENCE_FORMAT",
                            f"{tag} must reference BOX.NNN, XYY or XYY.ZZ",
                            observation,
                            tag,
                        )
                    )

        if rule.name == "WB_M1W2":
            for tag in ("W1", "W2"):
                if bus_point_id:
                    facts.port_identities.add(f"{bus_point_id}/{tag}")
                target = attributes.get(tag, "").strip()
                if not target:
                    continue
                if not _FIELD_PORT_REFERENCE.fullmatch(target):
                    issues.append(
                        self._issue(
                            "FIELD_PORT_REFERENCE_FORMAT",
                            f"{tag} must reference BOX.NNN, XYY or XYY.ZZ",
                            observation,
                            tag,
                        )
                    )
        return issues

    @staticmethod
    def _read_payload(
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
    ) -> NormalizedCadReadPayload:
        cable_identity = _parse_cable_identity(attributes.get("CABLE_ID", ""))
        keys = tuple(
            TaggedFact(tag, attributes[tag])
            for tag in ("KEY_1", "KEY_2", "KEY_3", "KEY_4")
            if tag in attributes
        )
        outputs = ()
        ports = tuple(
            TaggedFact(tag, attributes[tag])
            for tag in ("COM1", "COM2", "W1", "W2", "K1", "K2", "IN_1", "IN_2")
            if tag in attributes
        )
        route = tuple(
            TaggedFact(tag, attributes.get(tag, ""))
            for tag in LINE_CONDUIT_ATTRIBUTES
            if tag in attributes
        )
        bus_route = tuple(
            TaggedFact(tag, attributes.get(tag, ""))
            for tag in ("BUS_MOUNT_WAY", "BUS_GOFRA_TYPE", "BUS_GOFRA_COLOR", "BUS_GOFRA_ID")
            if tag in attributes
        )
        bus_point_id = attributes.get("BUS_POINT_ID", "")
        bus_match = _BUS_POINT_ID.fullmatch(bus_point_id)
        return NormalizedCadReadPayload(
            block_name=observation.effective_name,
            device_type=rule.device_type,
            layer=observation.layer,
            handle=observation.handle,
            x=observation.x,
            y=observation.y,
            cable_identity=cable_identity,
            box_id=attributes.get("BOX_ID") or None,
            cable_source=attributes.get("CABLE_SOURCE") or None,
            bus_point_id=bus_point_id or None,
            bus_id=bus_match.group("bus") if bus_match else None,
            bus_source=attributes.get("BUS_SOURCE") or None,
            bus_type=("DALI" if "BUS_SOURCE" in rule.required_definition_attributes else "RS485")
            if bus_match
            else None,
            cable_link_kind=rule.cable_link_kind,
            bus_link_kind=rule.bus_link_kind,
            derived_phase=rule.derived_phase,
            keys=keys,
            topology_outputs=outputs,
            field_ports=ports,
            led_type=attributes.get("LED_TYPE") or None,
            route_fields=route,
            bus_route_fields=bus_route,
        )

    def _collect_line_facts(
        self,
        observation: CadObservation,
        rule: BlockRule,
        function_group: str | None,
        attributes: dict[str, str],
        facts: _BatchFacts,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cable_id = attributes.get("CABLE_ID", "")
        if function_group == "AV":
            if rule.name != self.catalog.av_rules["block_name"]:
                issues.append(
                    self._issue(
                        "AV_BLOCK_NAME",
                        "AV line observation must use CABLE_OUTLET",
                        observation,
                        "BLOCK_NAME",
                    )
                )
            board = attributes.get("BOARD", "")
            if board and cable_id:
                facts.av_identity_handles[(board, cable_id)].append(observation.handle)
                facts.av_rows.append((observation.handle, board, cable_id))
            return issues
        if not cable_id:
            if any(attributes.get(tag) for tag in ("CABLE_TYPE", "BOARD")):
                issues.append(
                    self._issue(
                        "LINE_FIELDS_WITHOUT_CABLE_ID",
                        "CABLE_TYPE/BOARD cannot define a line without CABLE_ID",
                        observation,
                        "CABLE_ID",
                    )
                )
            return issues
        if not _STANDARD_CABLE_ID.fullmatch(cable_id):
            issues.append(
                self._issue(
                    "CABLE_ID_FORMAT",
                    "non-AV CABLE_ID must match XYY, XYY.ZZ or XYY.RKn",
                    observation,
                    "CABLE_ID",
                )
            )
            return issues
        base = cable_id[:3]
        facts.base_cables.add(base)
        if function_group is not None:
            expected_prefix = self.catalog.functional_groups[function_group].cable_prefix
            if expected_prefix != base[0]:
                issues.append(
                    self._issue(
                        "CABLE_GROUP_PREFIX_MISMATCH",
                        f"CABLE_ID {cable_id} contradicts FUNCTION_GROUP={function_group}",
                        observation,
                        "CABLE_ID",
                    )
                )
            facts.line_rows[base].append(
                (
                    observation.handle,
                    attributes.get("CABLE_TYPE", ""),
                    attributes.get("BOARD", ""),
                    function_group,
                    attributes.get("LED_TYPE", ""),
                )
            )
            facts.identity_handles[cable_id].append(observation.handle)
            if "." in cable_id:
                facts.point_rows[cable_id].append(
                    (
                        observation.handle,
                        rule.device_type or "",
                        attributes.get("BOARD", ""),
                        attributes.get("ROOM", ""),
                        attributes.get("MOUNT_HEIGHT", ""),
                        attributes.get("CABLE_TYPE", ""),
                        attributes.get("MOUNT_WAY", ""),
                        attributes.get("GOFRA_TYPE", ""),
                        attributes.get("GOFRA_COLOR", ""),
                        attributes.get("GOFRA_ID", ""),
                    )
                )
            if rule.device_type in {"SWITCH", "BUTTON"} and base.startswith("2"):
                identity = _parse_cable_identity(cable_id)
                key_tags = tuple(f"KEY_{index}" for index in range(1, rule.key_count + 1))
                facts.switch_rows[base].append(
                    (
                        None if identity is None else identity.suffix_order,
                        attributes.get("CABLE_TYPE", ""),
                        key_tags,
                        observation.handle,
                    )
                )
            conduit_id = attributes.get("GOFRA_ID", "")
            if conduit_id:
                facts.conduit_rows[conduit_id].append(
                    (
                        observation.handle,
                        attributes.get("GOFRA_TYPE", ""),
                        attributes.get("GOFRA_COLOR", ""),
                    )
                )
        return issues

    def _collect_board_fact(
        self,
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        facts: _BatchFacts,
        issues: list[ValidationIssue],
    ) -> None:
        if rule.device_type != "BOARD":
            return
        board_id = attributes.get("BOARD_ID", "")
        if not board_id:
            return
        if board_id in facts.board_roles:
            issues.append(
                self._issue(
                    "DUPLICATE_BOARD_ID",
                    f"BOARD_ID {board_id!r} is not unique",
                    observation,
                    "BOARD_ID",
                )
            )
        else:
            facts.board_roles[board_id] = attributes.get("LOAD_TYPE", "")

    @staticmethod
    def _collect_frame_mechanism_fact(
        observation: CadObservation,
        rule: BlockRule,
        attributes: dict[str, str],
        facts: _BatchFacts,
    ) -> None:
        room = attributes.get("ROOM", "")
        is_ip44 = "_IP44" in rule.name
        if rule.device_type == "FRAME":
            posts = rule.posts or 0
            facts.frame_rows.append((room, observation.handle, posts, is_ip44))
        elif rule.device_type in {"SOCKET", "SWITCH", "BUTTON"}:
            facts.mechanism_rows.append((room, observation.handle, is_ip44))

    def _validate_batch_facts(self, facts: _BatchFacts, source_metadata) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for cable_id, rows in sorted(facts.point_rows.items()):
            if len(rows) <= 1:
                continue
            handles = tuple(row[0] for row in rows)
            device_types = {row[1] for row in rows}
            if device_types == {"SOCKET"} and _POINT_CABLE_ID.fullmatch(cable_id):
                for index, label in (
                    (2, "BOARD"),
                    (3, "ROOM"),
                    (4, "MOUNT_HEIGHT"),
                    (5, "CABLE_TYPE"),
                    (6, "MOUNT_WAY"),
                    (7, "GOFRA_TYPE"),
                    (8, "GOFRA_COLOR"),
                    (9, "GOFRA_ID"),
                ):
                    values = {row[index] for row in rows}
                    if len(values) > 1:
                        issues.append(
                            self._issue(
                                "SHARED_SOCKET_POINT_INCONSISTENT",
                                f"shared SOCKET point {cable_id} has inconsistent {label}: "
                                f"{sorted(values)}",
                                handle=handles[0],
                                field=label,
                                related_handles=handles,
                            )
                        )
                continue
            if "SOCKET" in device_types:
                issues.append(
                    self._issue(
                        "SHARED_SOCKET_DEVICE_TYPE_MISMATCH",
                        f"full CABLE_ID {cable_id} mixes device types {sorted(device_types)}",
                        handle=handles[0],
                        field="CABLE_ID",
                        related_handles=handles,
                    )
                )
            else:
                issues.append(
                    self._issue(
                        "DUPLICATE_FULL_CABLE_ID",
                        f"full CABLE_ID {cable_id} occurs at handles {handles}",
                        handle=handles[0],
                        field="CABLE_ID",
                        related_handles=handles,
                    )
                )
        for base, rows in sorted(facts.line_rows.items()):
            for index, label in (
                (1, "CABLE_TYPE"),
                (2, "BOARD"),
                (3, "FUNCTION_GROUP"),
                (4, "LED_TYPE"),
            ):
                values = {row[index] for row in rows}
                if label == "LED_TYPE" and values == {""}:
                    continue
                if len(values) > 1:
                    for row in rows:
                        issues.append(
                            self._issue(
                                f"LINE_{label}_INCONSISTENT",
                                f"base line {base} has inconsistent {label}: {sorted(values)}",
                                handle=row[0],
                                field=label,
                            )
                        )
        issues.extend(self._validate_source_graphs(facts))
        if facts.el_box_outputs:
            issues.extend(self._validate_el_box_graph(facts))
        issues.extend(self._validate_switch_capacity(facts, source_metadata))
        issues.extend(self._validate_frame_composition(facts))
        for conduit_id, rows in sorted(facts.conduit_rows.items()):
            for index, label in ((1, "TYPE"), (2, "COLOR")):
                values = {row[index] for row in rows}
                if len(values) > 1:
                    for row in rows:
                        issues.append(
                            self._issue(
                                f"CONDUIT_{label}_INCONSISTENT",
                                f"shared GOFRA_ID {conduit_id} has inconsistent {label}: "
                                f"{sorted(values)}",
                                handle=row[0],
                                field=f"GOFRA_{label}",
                            )
                        )
        for identity, handles in sorted(facts.av_identity_handles.items()):
            if len(handles) > 1:
                issues.append(
                    self._issue(
                        "DUPLICATE_AV_IDENTITY",
                        f"AV identity {identity[0]} / {identity[1]} occurs at {handles}",
                        handle=handles[0],
                        field="CABLE_ID",
                    )
                )
        for handle, board, _cable_id in facts.av_rows:
            role = facts.board_roles.get(board)
            if role is None:
                issues.append(
                    self._issue(
                        "AV_BOARD_NOT_FOUND",
                        f"AV BOARD {board!r} does not reference an observed board",
                        handle=handle,
                        field="BOARD",
                        blocks_acceptance=False,
                    )
                )
            elif role != self.catalog.board_rules["av_role"]:
                issues.append(
                    self._issue(
                        "AV_BOARD_WRONG_ROLE",
                        f"AV BOARD {board!r} has LOAD_TYPE={role!r}, not BOARD_AV",
                        handle=handle,
                        field="BOARD",
                        blocks_acceptance=False,
                    )
                )
        for handle, field, target in facts.key_references:
            known = (
                target in facts.dali_groups
                if target.startswith("D.")
                else target in facts.base_cables
            )
            if not known:
                issues.append(
                    self._issue(
                        "KEY_TARGET_NOT_FOUND",
                        f"{field} target {target!r} is absent from the observation batch",
                        handle=handle,
                        field=field,
                    )
                )
        return issues

    def _validate_source_graphs(self, facts: _BatchFacts) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cable_nodes = set(facts.identity_handles)
        box_nodes = set(facts.box_handles)
        parents: dict[str, str] = {}
        adjacency: dict[str, set[str]] = defaultdict(set)
        for handle, target, source in facts.source_rows:
            if source.startswith("BOX."):
                known = source in box_nodes
            elif "/" in source:
                known = source in facts.port_identities
            else:
                known = source in cable_nodes
            if not known:
                issues.append(
                    self._issue(
                        "CABLE_SOURCE_NOT_FOUND",
                        f"CABLE_SOURCE {source!r} is absent or its exact port does not exist",
                        handle=handle,
                        field="CABLE_SOURCE",
                    )
                )
                continue
            if target:
                previous = parents.get(target)
                if previous is not None and previous != source:
                    issues.append(
                        self._issue(
                            "CABLE_SOURCE_DOUBLE_PARENT",
                            f"{target} has incompatible parents {previous!r} and {source!r}",
                            handle=handle,
                            field="CABLE_SOURCE",
                        )
                    )
                parents[target] = source
                adjacency[source].add(target)
        nodes = set(adjacency) | {node for values in adjacency.values() for node in values}
        if _graph_has_cycle(adjacency, nodes):
            issues.append(
                self._issue(
                    "CABLE_SOURCE_CYCLE",
                    "ordinary cable topology contains a cycle",
                    field="CABLE_SOURCE",
                )
            )

        bus_points = {point for _handle, point, _source, _kind, _cable_type in facts.bus_rows}
        bus_adjacency: dict[str, set[str]] = defaultdict(set)
        cable_types: dict[str, set[str]] = defaultdict(set)
        for handle, point, source, kind, cable_type in facts.bus_rows:
            bus_id = point[:3]
            if cable_type:
                cable_types[bus_id].add(cable_type)
            if kind == "DALI":
                if source[:3] != bus_id:
                    issues.append(
                        self._issue(
                            "BUS_SOURCE_CROSS_BUS",
                            f"{source!r} does not belong to BUS_ID {bus_id}",
                            handle=handle,
                            field="BUS_SOURCE",
                        )
                    )
                elif source != f"{bus_id}.000" and source not in bus_points:
                    issues.append(
                        self._issue(
                            "BUS_SOURCE_NOT_FOUND",
                            f"BUS_SOURCE {source!r} is absent",
                            handle=handle,
                            field="BUS_SOURCE",
                        )
                    )
                else:
                    bus_adjacency[source].add(point)
        bus_nodes = set(bus_adjacency) | {
            node for values in bus_adjacency.values() for node in values
        }
        if _graph_has_cycle(bus_adjacency, bus_nodes):
            issues.append(
                self._issue(
                    "BUS_SOURCE_CYCLE", "DALI topology contains a cycle/ring", field="BUS_SOURCE"
                )
            )
        for bus_id, values in sorted(cable_types.items()):
            if len(values) > 1:
                issues.append(
                    self._issue(
                        "BUS_CABLE_TYPE_INCONSISTENT",
                        f"BUS_ID {bus_id} has inconsistent BUS_CABLE_TYPE: {sorted(values)}",
                        field="BUS_CABLE_TYPE",
                    )
                )
        return issues

    def _validate_el_box_graph(self, facts: _BatchFacts) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        edges_by_base: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
        seen_edges: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for handle, source, tag, target in sorted(facts.el_box_outputs):
            if not source or not _EL_BOX_CABLE_ID.fullmatch(source):
                continue
            source_base = source[:3]
            if target[:3] != source_base:
                if target not in facts.identity_handles and target not in facts.base_cables:
                    issues.append(
                        self._issue(
                            "EL_BOX_CROSS_LINE_TARGET_NOT_FOUND",
                            f"{tag} cross-line target {target!r} is absent",
                            handle=handle,
                            field=tag,
                        )
                    )
                continue
            if target == source:
                issues.append(
                    self._issue(
                        "EL_BOX_SELF_REFERENCE",
                        f"{tag} cannot reference its own EL_BOX {source}",
                        handle=handle,
                        field=tag,
                    )
                )
                continue
            if target not in facts.identity_handles:
                issues.append(
                    self._issue(
                        "EL_BOX_TARGET_NOT_FOUND",
                        f"{tag} same-line target {target!r} is absent",
                        handle=handle,
                        field=tag,
                    )
                )
                continue
            edge = (source, target)
            seen_edges[edge].append((handle, tag))
            parents[target].append((source, handle))
            edges_by_base[source_base].append((source, target, handle, tag))
        for (source, target), refs in sorted(seen_edges.items()):
            if len(refs) > 1:
                issues.append(
                    self._issue(
                        "EL_BOX_DUPLICATE_EDGE",
                        f"edge {source} -> {target} is declared more than once",
                        handle=refs[0][0],
                        field=refs[0][1],
                        related_handles=tuple(sorted({item[0] for item in refs})),
                    )
                )
        for target, incoming in sorted(parents.items()):
            distinct_sources = {item[0] for item in incoming}
            if len(distinct_sources) > 1:
                issues.append(
                    self._issue(
                        "EL_BOX_DOUBLE_PARENT",
                        f"target {target} has independent parents {sorted(distinct_sources)}",
                        handle=incoming[0][1],
                        field="OUT_*",
                        related_handles=tuple(sorted({item[1] for item in incoming})),
                    )
                )
        for base, edges in sorted(edges_by_base.items()):
            nodes = {node for source, target, _, _ in edges for node in (source, target)}
            targets = {target for _, target, _, _ in edges}
            roots = sorted(nodes - targets)
            if len(roots) != 1:
                handles = tuple(sorted({handle for _, _, handle, _ in edges}))
                issues.append(
                    self._issue(
                        "EL_BOX_AMBIGUOUS_ROOT",
                        f"base line {base} topology has roots {roots}",
                        handle=handles[0] if handles else None,
                        field="OUT_*",
                        related_handles=handles,
                    )
                )
            adjacency: dict[str, set[str]] = defaultdict(set)
            for source, target, _handle, _tag in edges:
                adjacency[source].add(target)
            if _graph_has_cycle(adjacency, nodes):
                handles = tuple(sorted({handle for _, _, handle, _ in edges}))
                issues.append(
                    self._issue(
                        "EL_BOX_CYCLE",
                        f"base line {base} EL_BOX topology contains a cycle",
                        handle=handles[0] if handles else None,
                        field="OUT_*",
                        related_handles=handles,
                    )
                )
        return issues

    def _validate_special_references(self, facts: _BatchFacts) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for kind, handle, tag, target in sorted(facts.special_references):
            if kind == "MRM2_INPUT":
                sources = facts.key_source_handles.get(target, [])
                if not sources:
                    code = "MRM2_INPUT_KEY_NOT_FOUND"
                    message = f"{tag} key source {target!r} is absent"
                elif len(set(sources)) > 1:
                    code = "MRM2_INPUT_KEY_AMBIGUOUS"
                    message = f"{tag} key source {target!r} is ambiguous"
                else:
                    continue
            elif kind == "MRM2_OUTPUT":
                if target in facts.base_cables:
                    continue
                code = "MRM2_OUTPUT_TARGET_NOT_FOUND"
                message = f"{tag} output line {target!r} is absent"
            else:
                if target in facts.identity_handles or target in facts.base_cables:
                    continue
                code = "M1W2_CHANNEL_TARGET_NOT_FOUND"
                message = f"{tag} channel target {target!r} is absent"
            issues.append(self._issue(code, message, handle=handle, field=tag))
        return issues

    def _validate_switch_capacity(
        self, facts: _BatchFacts, source_metadata
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        capacities = source_metadata.get("cable_type_conductors", {}) if source_metadata else {}
        capacities = capacities if isinstance(capacities, dict) else {}
        for base, rows in sorted(facts.switch_rows.items()):
            if len(rows) > 1 and any(order is None for order, _, _, _ in rows):
                issues.append(
                    self._issue(
                        "SWITCH_POINT_SUFFIX_REQUIRED",
                        f"grouped switch line {base} requires .ZZ physical point identities",
                        handle=sorted(row[3] for row in rows)[0],
                        field="CABLE_ID",
                    )
                )
            required = 1 + sum(len(row[2]) for row in rows)
            cable_type = rows[0][1]
            available = capacities.get(cable_type)
            if not isinstance(available, int) or isinstance(available, bool) or available <= 0:
                issues.append(
                    self._issue(
                        "SWITCH_CONDUCTOR_CAPACITY_UNKNOWN",
                        f"line {base} requires {required} conductors; exact capacity "
                        f"for {cable_type!r} is unavailable",
                        handle=sorted(row[3] for row in rows)[0],
                        field="CABLE_TYPE",
                        blocks_acceptance=False,
                    )
                )
            elif required > available:
                issues.append(
                    self._issue(
                        "SWITCH_CONDUCTOR_CAPACITY_EXCEEDED",
                        f"line {base} requires {required} conductors but "
                        f"{cable_type!r} provides {available}",
                        handle=sorted(row[3] for row in rows)[0],
                        field="CABLE_TYPE",
                    )
                )
        return issues

    def _validate_frame_composition(self, facts: _BatchFacts) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        rooms = {row[0] for row in facts.frame_rows} | {row[0] for row in facts.mechanism_rows}
        for room in sorted(rooms):
            frame_rows = [row for row in facts.frame_rows if row[0] == room]
            mechanisms = [row for row in facts.mechanism_rows if row[0] == room]
            posts = sum(row[2] for row in frame_rows)
            mechanism_count = len(mechanisms)
            handles = tuple(sorted({row[1] for row in frame_rows} | {row[1] for row in mechanisms}))
            if posts != mechanism_count:
                code = "FRAME_POSTS_DEFICIT" if posts < mechanism_count else "FRAME_POSTS_EXCESS"
                issues.append(
                    self._issue(
                        code,
                        f"room {room!r}: frame posts {posts}, mechanisms {mechanism_count}",
                        handle=handles[0] if handles else None,
                        field="ROOM",
                        related_handles=handles,
                        blocks_acceptance=False,
                    )
                )
            ip44_posts = sum(row[2] for row in frame_rows if row[3])
            ip44_mechanisms = sum(1 for row in mechanisms if row[2])
            if ip44_mechanisms > ip44_posts:
                issues.append(
                    self._issue(
                        "FRAME_IP44_POSTS_DEFICIT",
                        f"room {room!r}: IP44 frame posts {ip44_posts}, "
                        f"IP44 mechanisms {ip44_mechanisms}",
                        handle=handles[0] if handles else None,
                        field="ROOM",
                        related_handles=handles,
                        blocks_acceptance=False,
                    )
                )
        return issues

    def _is_forbidden(self, tag: str) -> bool:
        upper = tag.upper()
        return upper in self.catalog.forbidden_attributes or any(
            upper.startswith(prefix) for prefix in self.catalog.forbidden_prefixes
        )

    @staticmethod
    def _issue(
        code: str,
        message: str,
        observation: CadObservation | None = None,
        field: str | None = None,
        *,
        handle: str | None = None,
        blocks_acceptance: bool = True,
        related_handles: tuple[str, ...] = (),
    ) -> ValidationIssue:
        return ValidationIssue(
            code=code,
            message=message,
            severity=IssueSeverity.ERROR,
            blocks_acceptance=blocks_acceptance,
            handle=observation.handle if observation is not None else handle,
            field=field,
            related_handles=related_handles,
        )


def _decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _parse_cable_identity(value: str) -> CableIdentity | None:
    if _BASE_CABLE_ID.fullmatch(value):
        return CableIdentity(value, value, CableSuffixKind.BASE)
    point = _POINT_CABLE_ID.fullmatch(value)
    if point:
        return CableIdentity(
            value,
            point.group("base"),
            CableSuffixKind.POINT,
            int(point.group("order")),
        )
    return None


def _graph_has_cycle(adjacency: dict[str, set[str]], nodes: set[str]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cycle = any(visit(target) for target in sorted(adjacency.get(node, ())))
        visiting.remove(node)
        visited.add(node)
        return cycle

    return any(visit(node) for node in sorted(nodes) if node not in visited)


def _is_finite_number(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return _decimal(value) is not None


def issue_codes(issues: Iterable[ValidationIssue]) -> set[str]:
    return {issue.code for issue in issues}
