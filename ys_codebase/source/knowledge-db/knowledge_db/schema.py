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
            language=str(data["language"]),
            docstring=str(data.get("docstring", "")),
            signature=str(data.get("signature", "")),
            members=members,
            metadata=dict(data.get("metadata", {})),
        )


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


ThesaurusGroup = List[str]


@dataclass
class ThesaurusConfig:
    groups: List[ThesaurusGroup] = field(default_factory=list)
    origin: str = "project"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groups": [list(g) for g in self.groups],
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, data: Any, origin: str = "project") -> "ThesaurusConfig":
        if isinstance(data, list):
            # 直接傳入 List[List[str]] 形式
            groups = []
            for item in data:
                if isinstance(item, list):
                    groups.append([str(w) for w in item])
            return cls(groups=groups, origin=origin)
        elif isinstance(data, dict):
            groups_raw = data.get("groups", [])
            groups = []
            for item in groups_raw:
                if isinstance(item, list):
                    groups.append([str(w) for w in item])
            return cls(groups=groups, origin=str(data.get("origin", origin)))
        else:
            return cls(groups=[], origin=origin)
