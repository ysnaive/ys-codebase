"""
Structured exception hierarchy for module:ast (ast_engine).
"""


class ASTError(Exception):
    """Base exception for module:ast."""


class ASTIndexNotFoundError(ASTError):
    """Raised when an expected AST snapshot or call graph binary index is missing."""


class ASTCorruptedError(ASTError):
    """Raised when an AST snapshot or call graph binary index is corrupted or fails schema validation."""


class InvalidConfigError(ASTError):
    """Raised when AST language or contribute configuration is invalid."""


class SchemaValidationError(ASTCorruptedError):
    """Raised when UnifiedSymbol, MemberInfo, or ASTSnapshot deserialization fails validation."""


__all__ = [
    "ASTError",
    "ASTIndexNotFoundError",
    "ASTCorruptedError",
    "InvalidConfigError",
    "SchemaValidationError",
]

