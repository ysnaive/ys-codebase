"""
knowledge-db 模組核心套件導出
"""

from .exceptions import (
    FingerprintCorruptedError,
    InvalidSpaceConfigError,
    KnowledgeDBError,
    SchemaValidationError,
    SpaceNotFoundError,
)
from .scanner import FileFingerprint, FingerprintScanner, ScanDiffResult
from .schema import (
    LanguageType,
    MemberInfo,
    SpaceConfig,
    SpaceOrigin,
    SymbolKind,
    ThesaurusConfig,
    ThesaurusGroup,
    UnifiedSymbol,
)
from .space import SpaceManager

__all__ = [
    "KnowledgeDBError",
    "SpaceNotFoundError",
    "InvalidSpaceConfigError",
    "SchemaValidationError",
    "FingerprintCorruptedError",
    "SymbolKind",
    "LanguageType",
    "SpaceOrigin",
    "MemberInfo",
    "UnifiedSymbol",
    "SpaceConfig",
    "ThesaurusConfig",
    "ThesaurusGroup",
    "SpaceManager",
    "FileFingerprint",
    "ScanDiffResult",
    "FingerprintScanner",
]
