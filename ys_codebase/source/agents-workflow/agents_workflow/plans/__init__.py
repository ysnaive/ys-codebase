"""
agents_workflow.plans — 開發計畫 (Dev Plans) 工具鏈子套件。
包含計畫安全歸檔 (PlanArchiver)、狀態掃描 (PlanScanner)、歷史與決策檢索 (PlanSearcher) 與規範稽核 (PlanVerifier)。
採用 PEP 562 模組級 __getattr__ 延遲載入，避免無關命令啟動時全量載入所有子模組。
"""

from typing import Any
from ._common import resolve_plan_uri, parse_markdown_blockquote_headers


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


_LAZY_EXPORTS = {
    "PlanArchiver": (".archiver", "PlanArchiver"),
    "PlanScanner": (".scanner", "PlanScanner"),
    "PlanSearcher": (".searcher", "PlanSearcher"),
    "PlanVerifier": (".verifier", "PlanVerifier"),
    "PlanSeverity": (".verifier", "PlanSeverity"),
    "PlanIssue": (".verifier", "PlanIssue"),
    "PlanReport": (".verifier", "PlanReport"),
    "PlanStatusResolver": (".status", "PlanStatusResolver"),
    "FrictionSignal": (".session_trace", "FrictionSignal"),
    "SessionTraceReport": (".session_trace", "SessionTraceReport"),
    "SessionTraceEngine": (".session_trace", "SessionTraceEngine"),
}

__all__ = [
    "resolve_plan_uri",
    "parse_markdown_blockquote_headers",
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
    "FrictionSignal",
    "SessionTraceReport",
    "SessionTraceEngine",
]


def __getattr__(name: str) -> Any:
    """PEP 562 模組級延遲載入。"""
    if name in _LAZY_EXPORTS:
        import importlib
        mod_rel, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(mod_rel, __name__)
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
