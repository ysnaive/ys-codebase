"""
knowledge-db 專屬例外階層定義
"""

from ast_engine.exceptions import ASTError, SchemaValidationError as _ASTSchemaValidationError


class KnowledgeDBError(ASTError):
    """knowledge-db 模組基礎例外類別"""


class InvalidConfigError(KnowledgeDBError):
    """knowledge-db 組態缺失必填欄位或格式不合法"""


SchemaValidationError = _ASTSchemaValidationError

__all__ = [
    "KnowledgeDBError",
    "InvalidConfigError",
    "SchemaValidationError",
]
