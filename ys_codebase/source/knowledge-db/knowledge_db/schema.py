"""
knowledge-db 核心資料結構、Enums 與 Schema 模型
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ast_engine.schema import (
    LanguageType,
    MemberInfo,
    SemanticBundle,
    SymbolCallSite,
    SymbolKind,
    UnifiedSymbol,
)

from .exceptions import InvalidConfigError, SchemaValidationError


def validate_space_weights(raw_weights: Any) -> Dict[str, float]:
    """校驗並正規化邏輯空間檢索權重映射表"""
    if raw_weights is None:
        return {}
    if not isinstance(raw_weights, dict):
        raise InvalidConfigError("space_weights must be a dict mapping space names to positive floats.")
    validated: Dict[str, float] = {}
    for space_name, weight_val in raw_weights.items():
        if isinstance(weight_val, bool):
            raise InvalidConfigError(f"Space '{space_name}' weight must be a number, got {weight_val!r}.")
        try:
            w = float(weight_val)
        except (TypeError, ValueError) as exc:
            raise InvalidConfigError(f"Space '{space_name}' weight must be a number, got {weight_val!r}.") from exc
        if w <= 0.0:
            raise InvalidConfigError(f"Space '{space_name}' weight must be > 0, got {w}.")
        validated[str(space_name)] = w
    return validated


@dataclass(frozen=True)
class KnowledgeDBContributes:
    """knowledge-db 擴充貢獻結構模型（僅管理 space_weights，語言擴充由 module:ast 管理）"""
    space_weights: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validated_weights = validate_space_weights(self.space_weights)
        object.__setattr__(self, "space_weights", validated_weights)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space_weights": dict(self.space_weights),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDBContributes":
        if not isinstance(data, dict):
            raise InvalidConfigError("KnowledgeDBContributes data must be a dict.")
        weights = validate_space_weights(data.get("space_weights", {}))
        return cls(space_weights=weights)


@dataclass(frozen=True)
class AggregatedItem:
    """單一檔案節點內部的命中項目"""

    symbol: UnifiedSymbol
    score: float
    matched_terms: List[str]
    snippet: str = ""
    code_snippet: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.symbol.id,
            "name": self.symbol.name,
            "kind": self.symbol.kind,
            "line_number": self.symbol.line_number,
            "end_line": self.symbol.end_line,
            "score": round(self.score, 4),
            "matched_terms": self.matched_terms,
            "signature": self.symbol.signature,
            "snippet": self.snippet,
        }
        if self.code_snippet and hasattr(self.code_snippet, "to_dict"):
            data["code_snippet"] = self.code_snippet.to_dict()
        return data


@dataclass(frozen=True)
class AggregatedFileResult:
    """檔案層級聚合結果節點"""

    file_path: str
    total_score: float
    items: List[AggregatedItem]
    spaces: List[str]
    language: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_score": round(self.total_score, 4),
            "spaces": self.spaces,
            "language": self.language,
            "item_count": len(self.items),
            "items": [item.to_dict() for item in self.items],
        }


__all__ = [
    "SymbolKind",
    "LanguageType",
    "MemberInfo",
    "UnifiedSymbol",
    "SemanticBundle",
    "SymbolCallSite",
    "KnowledgeDBContributes",
    "validate_space_weights",
    "AggregatedItem",
    "AggregatedFileResult",
    "SchemaValidationError",
    "InvalidConfigError",
]
