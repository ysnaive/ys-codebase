"""
agents_workflow.plans — 開發計畫 (Dev Plans) 工具鏈子套件。
包含計畫安全歸檔 (PlanArchiver)、狀態掃描 (PlanScanner)、歷史與決策檢索 (PlanSearcher) 與規範稽核 (PlanVerifier)。
"""

class PlansToolchainError(Exception):
    """Plans 工具鏈通用例外基底。"""
    pass


class PlanNotFoundError(PlansToolchainError):
    """找不到指定的計畫目錄時拋出。"""
    pass


class PlanFormatError(PlansToolchainError):
    """計畫名稱時間戳前綴不符合規範時拋出。"""
    pass


class PlanIncompleteError(PlansToolchainError):
    """計畫未標記 Completed 或未登載 CHANGELOG 且無 --force 時拋出。"""
    pass


class PlanDestinationExistsError(PlansToolchainError):
    """歸檔目的地目錄已存在同名計畫時拋出。"""
    pass


from pathlib import Path
from typing import Optional

def _resolve_uri_path(uri_str: str, default_fallback: Optional[str] = None) -> Optional[Path]:
    """安全解析語意 URI，若無 core 上下文或解析失敗則回傳 default_fallback 或 None。"""
    try:
        from core.uri import resolve
        resolved = resolve(uri_str)
        return Path(resolved).resolve()
    except Exception:
        if default_fallback:
            return Path(default_fallback).resolve()
        return None


from .archiver import PlanArchiver
from .scanner import PlanScanner
from .searcher import PlanSearcher
from .verifier import PlanVerifier, PlanSeverity, PlanIssue, PlanReport
from .status import PlanStatusResolver

__all__ = [
    "_resolve_uri_path",
    "PlansToolchainError",
    "PlanNotFoundError",
    "PlanFormatError",
    "PlanIncompleteError",
    "PlanDestinationExistsError",
    "PlanArchiver",
    "PlanScanner",
    "PlanSearcher",
    "PlanVerifier",
    "PlanSeverity",
    "PlanIssue",
    "PlanReport",
    "PlanStatusResolver",
]

