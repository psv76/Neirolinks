"""Universal constructor public API."""

from .domain import (
    RelationDefinition,
    RelationPreview,
    ResourceFacts,
    RuleResult,
    default_relation_definitions,
    find_cycle,
    has_path,
    validate_relation,
)
from .service import (
    BlockingViolation,
    ConstructorError,
    ConstructorService,
    RelationReceipt,
)
from .trace import FunctionalEdge, FunctionalTrace, FunctionalTraceStep

__all__ = [
    "RelationDefinition",
    "RelationPreview",
    "ResourceFacts",
    "RuleResult",
    "default_relation_definitions",
    "find_cycle",
    "has_path",
    "validate_relation",
    "BlockingViolation",
    "ConstructorError",
    "ConstructorService",
    "RelationReceipt",
    "FunctionalEdge",
    "FunctionalTrace",
    "FunctionalTraceStep",
]
