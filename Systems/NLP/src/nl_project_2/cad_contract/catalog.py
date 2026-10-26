"""Loader and typed runtime view of the approved plan-block metadata contract."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from nl_project_2.runtime_resources import bundled_path

from .layer_groups import function_group_for_working_layer


class ContractCatalogError(ValueError):
    """Raised when the machine-readable CAD contract is invalid."""


@dataclass(frozen=True, slots=True)
class FunctionalGroupRule:
    name: str
    cable_prefix: str | None
    layers: frozenset[str]
    device_types: frozenset[str]


@dataclass(frozen=True, slots=True)
class BlockRule:
    name: str
    block_class: str
    device_type: str | None
    attribute_profile: str | None
    required_attributes: frozenset[str]
    required_definition_attributes: frozenset[str]
    optional_attributes: frozenset[str]
    forbidden_attributes: frozenset[str]
    allowed_groups: frozenset[str]
    key_count: int = 0
    posts: int | None = None
    logical_layer: str | None = None
    dynamic_if_metadata_available: bool = False
    ignored_project_data: bool = False
    allowed_load_types: frozenset[str] = frozenset()
    derived_phase: int | None = None
    cable_link_kind: str | None = None
    bus_link_kind: str | None = None


@dataclass(frozen=True, slots=True)
class BlockContractCatalog:
    contract_version: str
    source_documents: tuple[str, ...]
    block_name_pattern: re.Pattern[str]
    blocks: Mapping[str, BlockRule]
    approved_block_names: frozenset[str]
    functional_groups: Mapping[str, FunctionalGroupRule]
    forbidden_attributes: frozenset[str]
    forbidden_prefixes: tuple[str, ...]
    numeric_attributes: Mapping[str, str]
    load_types: Mapping[str, frozenset[str]]
    board_rules: Mapping[str, Any]
    av_rules: Mapping[str, Any]

    def block(self, name: str) -> BlockRule | None:
        aliases = {
            "LIGHT_IN": "LIGHT_IN_230V",
            "LIGHT_OUT": "LIGHT_OUT_230V",
            "SENSOR_M1W2": "WB_M1W2",
            "SENSOR_MAI2": "WB_MAI2",
        }
        return self.blocks.get(aliases.get(name, name))

    def groups_for_layer(self, layer: object, *, include_legacy: bool = True) -> frozenset[str]:
        """Resolve numeric layers; retain exact legacy aliases for existing callers.

        Numeric suffixes are unrestricted. Contract layers contain representative
        numeric names plus explicit legacy aliases, not numeric suffix allow-lists.
        New numeric-only consumers can opt out of legacy compatibility.
        """
        group = function_group_for_working_layer(layer)
        if group is not None:
            return frozenset({group}) if group in self.functional_groups else frozenset()
        if not include_legacy or not isinstance(layer, str):
            return frozenset()
        return frozenset(
            name for name, rule in self.functional_groups.items() if layer in rule.layers
        )

    def groups_for_board_layer(
        self, block_name: str, load_type: str, layer: object
    ) -> frozenset[str]:
        """Staged role-aware board placement; runtime validator adoption is C7b.

        Do not add AV to generic BOARD allowed_groups: the exception requires
        the approved block, role and numeric group together.
        """
        rule = self.block(block_name)
        if rule is None or rule.device_type != "BOARD" or load_type not in rule.allowed_load_types:
            return frozenset()
        if load_type == self.board_rules["av_role"]:
            group = function_group_for_working_layer(layer)
            if block_name == self.board_rules["av_block_name"] and group == self.board_rules.get(
                "av_function_group"
            ):
                return frozenset({group}) if group in self.functional_groups else frozenset()
            return frozenset()
        # Ethernet SCS cabinet is a network root, not a 230 V distribution
        # board. Permit ONLY the approved BOARD_OUT + BOARD_SCS combination
        # on numeric 800 layers; never generalize to POWER boards or BOARD_IN.
        if function_group_for_working_layer(layer) == "NETWORK":
            return (
                frozenset({"NETWORK"})
                if block_name == "BOARD_OUT" and load_type == "BOARD_SCS"
                else frozenset()
            )
        return self.groups_for_layer(layer) & rule.allowed_groups


def default_contract_path() -> Path:
    return bundled_path("resources", "autocad", "block_contract.json")


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractCatalogError(f"{field} must be an array of strings")
    return tuple(value)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractCatalogError(f"{field} must be an object")
    return value


def load_contract(path: Path | None = None) -> BlockContractCatalog:
    source_path = default_contract_path() if path is None else path
    try:
        root = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractCatalogError(f"cannot load contract: {source_path}") from exc
    data = _mapping(root, "root")
    load_type_values = _mapping(data.get("load_types"), "load_types")

    profiles = _mapping(data.get("attribute_profiles"), "attribute_profiles")
    groups: dict[str, FunctionalGroupRule] = {}
    for name, raw_group in _mapping(data.get("functional_groups"), "functional_groups").items():
        group = _mapping(raw_group, f"functional_groups.{name}")
        groups[name] = FunctionalGroupRule(
            name=name,
            cable_prefix=group.get("cable_prefix"),
            layers=frozenset(_strings(group.get("layers"), f"{name}.layers")),
            device_types=frozenset(_strings(group.get("device_types"), f"{name}.device_types")),
        )

    blocks: dict[str, BlockRule] = {}
    for family_index, raw_family in enumerate(data.get("block_families", [])):
        family = _mapping(raw_family, f"block_families[{family_index}]")
        profile_name = family.get("attribute_profile")
        profile = _mapping(profiles.get(profile_name), f"attribute_profiles.{profile_name}")
        device_type = family.get("device_type")
        explicit_groups = family.get("allowed_groups")
        # The approved 48 V DALI track-light family is a LIGHT in the
        # functional catalogue but physically belongs to the 4YY LED group.
        # Keep the 3YY/4YY voltage boundary without changing the CAD JSON.
        if (
            explicit_groups is None
            and family.get("attribute_profile") == "TRACK_DALI_LIGHT"
            and family.get("names") == ["LIGHT_TRACK_DALI_48V"]
        ):
            explicit_groups = ["LIGHTING_LED"]
        if explicit_groups is not None:
            # A protocol-only BUS outlet is not an ordinary CABLE_OUTLET
            # belonging to POWER/LIGHTING/etc. Respect the contract's
            # explicit allowed_groups rather than deriving from device_type.
            allowed_groups = frozenset(
                _strings(explicit_groups, f"block_families[{family_index}].allowed_groups")
            )
            unknown_groups = allowed_groups - groups.keys()
            if unknown_groups:
                raise ContractCatalogError(
                    f"unknown allowed_groups for block family {family_index}: "
                    f"{sorted(unknown_groups)}"
                )
        else:
            allowed_groups = frozenset(
                name for name, group in groups.items() if device_type in group.device_types
            )
        key_counts = _mapping(family.get("key_counts", {}), "key_counts")
        posts = _mapping(family.get("posts", {}), "posts")
        family_optional = set(
            _strings(family.get("optional_attributes", []), "optional_attributes")
        )
        for name in _strings(family.get("names"), f"block_families[{family_index}].names"):
            if name in blocks:
                raise ContractCatalogError(f"duplicate block name: {name}")
            key_count = int(key_counts.get(name, 0))
            required = set(_strings(profile.get("required"), f"{profile_name}.required"))
            key_attributes = {f"KEY_{index}" for index in range(1, key_count + 1)}
            optional = set(_strings(profile.get("optional", []), f"{profile_name}.optional"))
            optional.update(key_attributes)
            optional.update(family_optional)
            required_definitions = required | set(
                _strings(
                    profile.get("definition_required", []),
                    f"{profile_name}.definition_required",
                )
            )
            required_definitions.update(key_attributes)
            forbidden = set(_strings(profile.get("forbidden", []), f"{profile_name}.forbidden"))
            blocks[name] = BlockRule(
                name=name,
                block_class=str(family.get("class")),
                device_type=str(device_type),
                attribute_profile=str(profile_name),
                required_attributes=frozenset(required),
                required_definition_attributes=frozenset(required_definitions),
                optional_attributes=frozenset(optional),
                forbidden_attributes=frozenset(forbidden),
                allowed_groups=allowed_groups,
                key_count=key_count,
                posts=int(posts[name]) if name in posts else None,
                allowed_load_types=frozenset(
                    _strings(
                        load_type_values.get(family.get("load_type_group"), [])
                        if family.get("load_type_group")
                        else family.get("allowed_load_types", []),
                        "allowed_load_types",
                    )
                ),
                derived_phase=(
                    int(family["derived_phase"])
                    if family.get("derived_phase") is not None
                    else None
                ),
                cable_link_kind=family.get("cable_link_kind"),
                bus_link_kind=family.get("bus_link_kind"),
            )

    for name, raw_logical in _mapping(data.get("logical_blocks"), "logical_blocks").items():
        logical = _mapping(raw_logical, f"logical_blocks.{name}")
        if name in blocks:
            raise ContractCatalogError(f"duplicate block name: {name}")
        blocks[name] = BlockRule(
            name=name,
            block_class="LOGICAL",
            device_type=None,
            attribute_profile=None,
            required_attributes=frozenset(_strings(logical.get("required", []), "required")),
            required_definition_attributes=frozenset(
                _strings(logical.get("required", []), "required")
            ),
            optional_attributes=frozenset(_strings(logical.get("optional", []), "optional")),
            forbidden_attributes=frozenset(),
            allowed_groups=frozenset(),
            logical_layer=logical.get("layer"),
            dynamic_if_metadata_available=bool(logical.get("dynamic_if_metadata_available")),
            ignored_project_data=bool(logical.get("ignored_project_data")),
        )

    approved_name_items = _strings(data.get("approved_block_names"), "approved_block_names")
    approved_names = frozenset(approved_name_items)
    if len(approved_names) != len(approved_name_items):
        raise ContractCatalogError("approved_block_names contains duplicates")
    actual_names = frozenset(blocks)
    if actual_names != approved_names:
        missing = sorted(approved_names - actual_names)
        unexpected = sorted(actual_names - approved_names)
        raise ContractCatalogError(
            f"block families do not match approved_block_names; missing={missing}, "
            f"unexpected={unexpected}"
        )
    version = data.get("contract_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ContractCatalogError("invalid contract_version")

    forbidden_exact: set[str] = set()
    forbidden_prefixes: list[str] = []
    for item in _strings(data.get("forbidden_attributes"), "forbidden_attributes"):
        if item.endswith("*"):
            forbidden_prefixes.append(item[:-1])
        else:
            forbidden_exact.add(item)
    numeric = {
        key: str(value)
        for key, value in _mapping(data.get("numeric_attributes", {}), "numeric_attributes").items()
    }
    load_types = {
        key: frozenset(_strings(value, f"load_types.{key}"))
        for key, value in _mapping(data.get("load_types"), "load_types").items()
    }
    return BlockContractCatalog(
        contract_version=version,
        source_documents=_strings(data.get("source_documents"), "source_documents"),
        block_name_pattern=re.compile(str(data.get("block_name_pattern"))),
        blocks=MappingProxyType(blocks),
        approved_block_names=approved_names,
        functional_groups=MappingProxyType(groups),
        forbidden_attributes=frozenset(forbidden_exact),
        forbidden_prefixes=tuple(forbidden_prefixes),
        numeric_attributes=MappingProxyType(numeric),
        load_types=MappingProxyType(load_types),
        board_rules=MappingProxyType(_mapping(data.get("board_rules"), "board_rules")),
        av_rules=MappingProxyType(_mapping(data.get("av_rules"), "av_rules")),
    )
