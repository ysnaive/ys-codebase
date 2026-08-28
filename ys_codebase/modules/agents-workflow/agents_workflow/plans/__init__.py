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


from .archiver import PlanArchiver
from .scanner import PlanScanner
from .searcher import PlanSearcher
from .verifier import PlanVerifier, PlanSeverity, PlanIssue, PlanReport

__all__ = [
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
]

