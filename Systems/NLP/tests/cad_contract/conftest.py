from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    load_contract,
)


@pytest.fixture(scope="session")
def block_contract():
    return load_contract()


@pytest.fixture
def make_observation(block_contract) -> Callable[..., CadObservation]:
    def factory(
        name: str,
        *,
        handle: str = "A1",
        layer: str | None = None,
        cable_id: str | None = None,
        attributes: Mapping[str, object] | None = None,
        x: int | float | str = 100,
        y: int | float | str = 200,
        dynamic: bool | None = None,
        definition_tags: tuple[str, ...] | None | object = ...,  # noqa: B008
    ) -> CadObservation:
        rule = block_contract.block(name)
        assert rule is not None
        if name == "ROOM_NAME":
            attrs: dict[str, object] = {}
            chosen_layer = layer or "ROOMS"
        elif name == "DALI_GROUP":
            attrs = {"DALI_GROUP_ID": "D.001"}
            chosen_layer = layer or "DALI_GROUPS"
            dynamic = True if dynamic is None else dynamic
        else:
            groups = sorted(group for group in rule.allowed_groups if group != "AV")
            group = groups[0]
            group_rule = block_contract.functional_groups[group]
            chosen_layer = layer or sorted(group_rule.layers)[0]
            attrs = {tag: "" for tag in rule.required_definition_attributes}
            attrs.update(
                {
                    "DEVICE_NAME": f"Fixture {name}",
                    "BUILDING": "B1",
                    "ROOM": "R1",
                    "MOUNT_HEIGHT": "300",
                }
            )
            if "CABLE_ID" in attrs:
                default_id = f"{group_rule.cable_prefix or '1'}01"
                if rule.device_type in {"SWITCH", "BUTTON"}:
                    default_id += ".01"
                attrs["CABLE_ID"] = cable_id or default_id
            for tag, value in {
                "CABLE_TYPE": "TEST CABLE",
                "BOARD": "B.01",
                "MOUNT_WAY": "По потолку",
                "LOAD_NAME": "Fixture load",
            }.items():
                if tag in attrs:
                    attrs[tag] = value
            if "BUS_POINT_ID" in attrs:
                attrs["BUS_POINT_ID"] = "901.001"
            if "BUS_SOURCE" in attrs:
                attrs["BUS_SOURCE"] = "901.000"
            if "BUS_CABLE_TYPE" in attrs:
                attrs["BUS_CABLE_TYPE"] = "BUS CABLE"
            if "BUS_MOUNT_WAY" in attrs:
                attrs["BUS_MOUNT_WAY"] = "По потолку"
            if "BOX_ID" in attrs:
                attrs["BOX_ID"] = "BOX.001"
            if "LOAD_TYPE" in attrs and rule.allowed_load_types:
                attrs["LOAD_TYPE"] = sorted(rule.allowed_load_types)[0]
            if "LED_TYPE" in attrs:
                attrs["LED_TYPE"] = "MONO"
            if "BOARD_ID" in attrs:
                attrs["BOARD_ID"] = "B.01"
            for index in range(1, rule.key_count + 1):
                attrs[f"KEY_{index}"] = "D.001"
            for tag in rule.required_definition_attributes:
                attrs.setdefault(tag, "")
        if attributes:
            attrs.update(attributes)
        if definition_tags is ...:
            tags: tuple[str, ...] | None = tuple(attrs)
        else:
            tags = definition_tags  # type: ignore[assignment]
        definition = BlockDefinitionMetadata(
            attribute_definition_tags=tags,
            is_dynamic=dynamic,
        )
        return CadObservation.from_mapping(
            effective_name=name,
            layer=chosen_layer,
            raw_attributes=attrs,
            x=x,
            y=y,
            handle=handle,
            definition=definition,
        )

    return factory
