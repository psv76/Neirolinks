"""Machine-readable AutoCAD plan-block contract and pure validation API."""

from .catalog import (
    BlockContractCatalog,
    BlockRule,
    ContractCatalogError,
    FunctionalGroupRule,
    default_contract_path,
    load_contract,
)
from .models import (
    BlockDefinitionMetadata,
    CableIdentity,
    CableSuffixKind,
    CadAttribute,
    CadObservation,
    CadObservationBatch,
    IssueSeverity,
    NormalizedCadReadPayload,
    TaggedFact,
    ValidatedObservation,
    ValidationIssue,
    ValidationResult,
)
from .port import CadObservationPort, CadReadRequest
from .validator import CadContractValidator, issue_codes

__all__ = [
    "BlockContractCatalog",
    "BlockDefinitionMetadata",
    "CableIdentity",
    "CableSuffixKind",
    "BlockRule",
    "CadAttribute",
    "CadContractValidator",
    "CadObservation",
    "CadObservationBatch",
    "CadObservationPort",
    "CadReadRequest",
    "ContractCatalogError",
    "FunctionalGroupRule",
    "IssueSeverity",
    "NormalizedCadReadPayload",
    "TaggedFact",
    "ValidatedObservation",
    "ValidationIssue",
    "ValidationResult",
    "default_contract_path",
    "issue_codes",
    "load_contract",
]
