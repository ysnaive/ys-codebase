"""
knowledge-db 模組之 Computed Token Providers
提供動態解算 KNOWLEDGE_DB_SPACE 空間表格等宣告式資產注入能力（委派至 file_space.providers）。
100% Python Standard Library, Zero Third-Party Dependency.
"""

from pathlib import Path
import sys
from typing import Any, Optional


def _ensure_file_space_path() -> None:
    """純標準庫掛載 module:file-space 路徑，避免連帶載入 ast_engine / networkx / fastembed。"""
    try:
        from core import uri

        mod_dir = uri.resolve("module://file-space", interactive=False)
        if mod_dir:
            m_path = Path(mod_dir).resolve()
            if (m_path / "file_space" / "__init__.py").is_file() and str(m_path) not in sys.path:
                sys.path.insert(0, str(m_path))
    except Exception:
        pass
    pkg_parent = Path(__file__).resolve().parent.parent.parent
    for cand in (pkg_parent / "file-space", pkg_parent.parent / ".modules" / "file-space"):
        if (cand / "file_space" / "__init__.py").is_file():
            cand_str = str(cand.resolve())
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)


_ensure_file_space_path()
from file_space.providers import get_knowledge_db_spaces as _render_knowledge_db_spaces


def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str:
    """
    動態編譯全系統已註冊之知識庫工作空間清單為 Markdown 表格。

    :param context: 可選之編譯期上下文（由 agents-workflow compiler 提供）
    :return: 格式化完成之 Markdown 空間表格
    """
    return _render_knowledge_db_spaces(context=context, **kwargs)
