"""
ExecutionContext definition for YS-Codebase.
Single Source of Truth (SSOT) for execution context across all modules.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface) - 單一真相來源 (SSOT)"""
    module_name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
