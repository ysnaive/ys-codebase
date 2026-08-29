"""
knowledge-db 核心資料結構、Enums 與 Schema 模型
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import fnmatch
import hashlib
from typing import Any, Dict, List, Optional

from .exceptions import InvalidSpaceConfigError, SchemaValidationError


class SymbolKind(str, Enum):
    # 代碼符號
    CLASS = "class"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    MACRO = "macro"
    VARIABLE = "variable"
    CONSTANT = "constant"

    # 文檔符號
    DOC_HEADING_1 = "doc_heading_1"
    DOC_HEADING_2 = "doc_heading_2"
    DOC_HEADING_3 = "doc_heading_3"
    DOC_HEADING_4 = "doc_heading_4"
    DOC_TABLE = "doc_table"
    DOC_SECTION = "doc_section"


class LanguageType(str, Enum):
    PYTHON = "python"
    MARKDOWN = "markdown"
    CPP = "cpp"
    CSHARP = "csharp"
    SPICE = "spice"
    JSON = "json"
    TEXT = "text"
    UNKNOWN = "unknown"


class SpaceOrigin(str, Enum):
    CONTRIBUTED = "contributed"
    PROJECT = "project"
    LOCAL = "local"


@dataclass(frozen=True)
class MemberInfo:
    name: str
    kind: str
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    line_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "docstring": self.docstring,
            "visibility": self.visibility,
            "line_number": self.line_number,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemberInfo":
        if not isinstance(data, dict):
            raise SchemaValidationError("MemberInfo data must be a dict.")
        if "name" not in data or "kind" not in data:
            raise SchemaValidationError("MemberInfo requires 'name' and 'kind'.")
        return cls(
            name=str(data["name"]),
            kind=str(data["kind"]),
            signature=str(data.get("signature", "")),
            docstring=str(data.get("docstring", "")),
            visibility=str(data.get("visibility", "public")),
            line_number=int(data.get("line_number", 0)),
        )


@dataclass(frozen=True)
class UnifiedSymbol:
    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    language: str
    docstring: str = ""
    signature: str = ""
    end_line: int = 0
    members: List[MemberInfo] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def spaces(self) -> List[str]:
        """獲取該符號所屬之空間標籤清單"""
        sp = self.metadata.get("spaces", [])
        if isinstance(sp, list):
            return sp
        if isinstance(sp, str) and sp:
            return [sp]
        single_sp = self.metadata.get("space", "")
        return [single_sp] if single_sp else []

    @classmethod
    def compute_id(cls, space: str, file_path: str, name: str, kind: str, line_number: int) -> str:
        """計算唯一 SHA1 雜湊識別碼"""
        # 正規化 file_path (forward slashes)
        normalized_path = file_path.replace("\\", "/")
        raw = f"{space}:{normalized_path}:{name}:{kind}:{line_number}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "language": self.language,
            "docstring": self.docstring,
            "signature": self.signature,
            "members": [m.to_dict() for m in self.members],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol":
        if not isinstance(data, dict):
            raise SchemaValidationError("UnifiedSymbol data must be a dict.")
        required = ["id", "name", "kind", "file_path", "line_number", "language"]
        for key in required:
            if key not in data:
                raise SchemaValidationError(f"UnifiedSymbol missing required field '{key}'.")

        members_raw = data.get("members", [])
        members = [
            MemberInfo.from_dict(m) if isinstance(m, dict) else m
            for m in members_raw
        ]
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            kind=str(data["kind"]),
            file_path=str(data["file_path"]),
            line_number=int(data["line_number"]),
            end_line=int(data.get("end_line", data.get("line_number", 0))),
            language=str(data["language"]),
            docstring=str(data.get("docstring", "")),
            signature=str(data.get("signature", "")),
            members=members,
            metadata=dict(data.get("metadata", {})),
        )


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

    @property
    def symbol(self) -> UnifiedSymbol:
        """向後相容：獲取該檔案中排名最高之主要 UnifiedSymbol"""
        if self.items:
            return self.items[0].symbol
        return UnifiedSymbol(
            id=self.file_path,
            name=self.file_path,
            kind="file",
            file_path=self.file_path,
            line_number=1,
            language=self.language,
        )

    @property
    def score(self) -> float:
        """向後相容別名"""
        return self.total_score

    @property
    def space(self) -> str:
        """向後相容別名"""
        return ", ".join(self.spaces) if self.spaces else ""

    @property
    def matched_terms(self) -> List[str]:
        """向後相容：獲取子項目命中詞聯集"""
        terms = set()
        for itm in self.items:
            terms.update(itm.matched_terms)
        return sorted(list(terms))

    @property
    def snippet(self) -> str:
        """向後相容：獲取主要子項目之摘要"""
        if self.items:
            return self.items[0].snippet
        return ""

    @property
    def code_snippet(self) -> Optional[Any]:
        """向後相容：獲取主要子項目之代碼切片"""
        if self.items:
            return self.items[0].code_snippet
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_score": round(self.total_score, 4),
            "spaces": self.spaces,
            "language": self.language,
            "item_count": len(self.items),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class SpaceConfig:
    name: str
    description: str = ""
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    file_patterns: Optional[List[str]] = None
    origin: str = "project"

    def is_file_included(self, filename: str) -> bool:
        """
        若未指定 file_patterns 則預設全包含 (include all)；若有指定則依 pattern 比對
        """
        if not self.file_patterns:
            return True
        return any(fnmatch.fnmatch(filename, pat) for pat in self.file_patterns)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "origin": self.origin,
        }
        if self.file_patterns is not None:
            result["file_patterns"] = list(self.file_patterns)
        return result

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any], origin: str = "project") -> "SpaceConfig":
        if not isinstance(data, dict):
            raise InvalidSpaceConfigError(f"Space config for '{name}' must be a dict.")
        include = data.get("include")
        if include is None or not isinstance(include, list):
            raise InvalidSpaceConfigError(f"Space '{name}' requires 'include' list.")

        exclude = data.get("exclude", [])
        if not isinstance(exclude, list):
            exclude = [str(exclude)]

        file_patterns = data.get("file_patterns")
        if file_patterns is not None and not isinstance(file_patterns, list):
            file_patterns = [str(file_patterns)]

        return cls(
            name=name,
            description=str(data.get("description", "")),
            include=[str(item) for item in include],
            exclude=[str(item) for item in exclude],
            file_patterns=[str(item) for item in file_patterns] if file_patterns is not None else None,
            origin=str(data.get("origin", origin)),
        )


@dataclass
class WeightedToken:
    """查詢 Token 資料結構 (含權重與語意類別)"""
    term: str
    weight: float = 1.0
    kind: str = "original"  # "original" | "synonym" | "alias" | "related"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "weight": self.weight,
            "kind": self.kind,
        }


ThesaurusGroup = List[str]


@dataclass
class ThesaurusConfig:
    groups: List[ThesaurusGroup] = field(default_factory=list)
    aliases: Dict[str, List[str]] = field(default_factory=dict)
    related: List[ThesaurusGroup] = field(default_factory=list)
    origin: str = "project"

    @property
    def thesaurus(self) -> List[ThesaurusGroup]:
        return self.groups

    @thesaurus.setter
    def thesaurus(self, value: List[ThesaurusGroup]) -> None:
        self.groups = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groups": [list(g) for g in self.groups],
            "thesaurus": [list(g) for g in self.groups],
            "aliases": {str(k): [str(w) for w in v] for k, v in self.aliases.items()},
            "related": [list(g) for g in self.related],
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, data: Any, origin: str = "project") -> "ThesaurusConfig":
        if isinstance(data, list):
            # 直接傳入 List[List[str]] 形式
            groups = []
            for item in data:
                if isinstance(item, list):
                    groups.append([str(w) for w in item if str(w).strip()])
            return cls(groups=groups, origin=origin)
        elif isinstance(data, dict):
            # 1. 讀取 groups / thesaurus
            raw_thesaurus = data.get("thesaurus") or data.get("groups", [])
            groups = []
            if isinstance(raw_thesaurus, list):
                for item in raw_thesaurus:
                    if isinstance(item, list):
                        groups.append([str(w) for w in item if str(w).strip()])

            # 2. 讀取 aliases (Dict[str, List[str]])
            raw_aliases = data.get("aliases", {})
            aliases: Dict[str, List[str]] = {}
            if isinstance(raw_aliases, dict):
                for k, v in raw_aliases.items():
                    key_clean = str(k).strip()
                    if key_clean:
                        if isinstance(v, list):
                            aliases[key_clean] = [str(w).strip() for w in v if str(w).strip()]
                        elif isinstance(v, str) and v.strip():
                            aliases[key_clean] = [v.strip()]

            # 3. 讀取 related (List[List[str]])
            raw_related = data.get("related", [])
            related = []
            if isinstance(raw_related, list):
                for item in raw_related:
                    if isinstance(item, list):
                        related.append([str(w) for w in item if str(w).strip()])

            return cls(
                groups=groups,
                aliases=aliases,
                related=related,
                origin=str(data.get("origin", origin)),
            )
        else:
            return cls(groups=[], origin=origin)

