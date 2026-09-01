"""
knowledge-db 模組之 Computed Token Providers
提供動態解算 KNOWLEDGE_DB_SPACE 空間表格等宣告式資產注入能力。
100% Python Standard Library, Zero Third-Party Dependency.
"""

from typing import Any, Dict, List, Optional
from .space import SpaceManager


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已註冊之 knowledge-db 知識庫空間清單為 Markdown 表格。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之 Markdown 空間表格
    """
    try:
        mgr = SpaceManager(core_context=context)
        spaces = mgr.load_spaces()
    except Exception:
        spaces = {}

    if not spaces:
        return (
            "| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |\n"
            "| :--- | :--- | :--- | :--- |\n"
            "| - | - | *(目前無已註冊空間)* | - |"
        )

    lines = [
        "| 空間名稱 (`--space=<name>`) | 來源定義 | 涵蓋路徑與包含範圍 | 語意說明 |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for sp_name, sp in sorted(spaces.items()):
        name_badge = f"**`{sp_name}`**"
        origin_label = f"`{sp.origin}`"

        inc_parts: List[str] = [f"`{inc}`" for inc in sp.include]
        if sp.file_patterns:
            pat_desc = f"*(過濾: `{', '.join(sp.file_patterns)}`)*"
            inc_parts.append(pat_desc)

        scope_desc = "<br/>".join(inc_parts) if inc_parts else "*(全目錄)*"
        desc = sp.description or "*(無描述)*"
        lines.append(f"| {name_badge} | {origin_label} | {scope_desc} | {desc} |")

    return "\n".join(lines)
