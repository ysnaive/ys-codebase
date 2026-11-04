"""
knowledge-db 模組之 Computed Token Providers
提供動態解算 KNOWLEDGE_DB_SPACE 空間表格等宣告式資產注入能力（委派至 file_space.providers）。
100% Python Standard Library, Zero Third-Party Dependency.
"""

from typing import Any, Optional

from file_space.providers import get_knowledge_db_spaces as _render_knowledge_db_spaces


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已註冊之知識庫工作空間清單為 Markdown 表格。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之 Markdown 空間表格
    """
    return _render_knowledge_db_spaces(context=context, **kwargs)
