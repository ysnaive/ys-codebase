"""
knowledge-db 專屬例外階層定義
"""

from typing import List, Optional


class KnowledgeDBError(Exception):
    """knowledge-db 模組基礎例外類別"""


class SpaceNotFoundError(KnowledgeDBError):
    """指定之空間名稱未註冊或不存在"""

    def __init__(self, space_name: str, available_spaces: Optional[List[str]] = None):
        msg = f"Space '{space_name}' not found."
        if available_spaces:
            msg += f" Available spaces: {', '.join(available_spaces)}"
        super().__init__(msg)
        self.space_name = space_name
        self.available_spaces = available_spaces or []


class InvalidSpaceConfigError(KnowledgeDBError):
    """空間組態缺失必填欄位或格式不合法"""


class SchemaValidationError(KnowledgeDBError):
    """UnifiedSymbol 或 MemberInfo 資料校驗失敗"""


class FingerprintCorruptedError(KnowledgeDBError):
    """指紋庫快取檔案損毀或無法解析"""
