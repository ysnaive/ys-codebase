"""
knowledge-db 專屬例外階層定義
"""


class KnowledgeDBError(Exception):
    """knowledge-db 模組基礎例外類別"""


class InvalidConfigError(KnowledgeDBError):
    """knowledge-db 組態缺失必填欄位或格式不合法"""


class SchemaValidationError(KnowledgeDBError):
    """UnifiedSymbol 或 MemberInfo 資料校驗失敗"""
