"""
ExecutionContext definition for YS-Codebase.
"""
from dataclasses import dataclass, field
from typing import List

@dataclass
class ExecutionContext:
    module_name: str
    command: str
    args: List[str] = field(default_factory=list)
