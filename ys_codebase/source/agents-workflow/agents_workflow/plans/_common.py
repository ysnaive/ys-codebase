"""
agents_workflow.plans._common — Plans 工具鏈共用基礎設施（語意 URI 解析與 Markdown 標頭提取 SSOT）。
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

DEFAULT_URI_FALLBACKS: Dict[str, str] = {
    "workflow.plans://": "plans",
    "workflow.archived://": "plans/archived",
    "project://": ".",
}


def resolve_plan_uri(uri_str: str, default_fallback: Optional[str] = None) -> Optional[Path]:
    """
    安全解析語意 URI；若無 core 上下文或解析失敗，則依 default_fallback 或 DEFAULT_URI_FALLBACKS 退避。

    Args:
        uri_str: 語意 URI 字串（如 'workflow.plans://'、'workflow.archived://'、'project://'）
        default_fallback: 選填退避相對路徑；若未指定則查表 DEFAULT_URI_FALLBACKS

    Returns:
        Optional[Path]: 解析後之絕對路徑，若無對應退避則回傳 None
    """
    try:
        from core.uri import resolve
        resolved = resolve(uri_str)
        if resolved and not str(resolved).startswith("!undefined"):
            return Path(resolved).resolve()
    except Exception:
        pass

    fallback = default_fallback if default_fallback is not None else DEFAULT_URI_FALLBACKS.get(uri_str)
    if fallback:
        return (Path.cwd() / fallback).resolve()
    return None


def parse_markdown_blockquote_headers(
    lines_or_content: Union[str, List[str]],
    max_lines: int = 35,
) -> Dict[str, str]:
    """
    結構化解析 Markdown 開頭 Blockquote (> 欄位：值 或 > 欄位: 值) 中的 Header 元數據 (SSOT)。

    Args:
        lines_or_content: Markdown 全文字串或行清單
        max_lines: 最大掃描行數（預設 35 行）

    Returns:
        Dict[str, str]: 小寫欄位名對應修剪後欄位值之字典
    """
    if isinstance(lines_or_content, str):
        lines = lines_or_content.splitlines()
    else:
        lines = list(lines_or_content)

    headers: Dict[str, str] = {}
    for line in lines[:max_lines]:
        line_clean = line.strip().replace("\u3000", " ")
        if line_clean.startswith(">"):
            inner = line_clean.lstrip(">").strip()
            if "：" in inner:
                k, v = inner.split("：", 1)
                headers[k.strip().lower()] = v.strip()
            elif ":" in inner:
                k, v = inner.split(":", 1)
                headers[k.strip().lower()] = v.strip()
    return headers
