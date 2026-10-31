"""
knowledge-db 核心資料結構、Enums 與 Schema 模型
"""

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import InvalidSpaceConfigError, SchemaValidationError


class SymbolKind(str, Enum):
    # 代碼符號
    CLASS = "class"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE_ALIAS = "type_alias"
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
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
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
class LanguageConfig:
    """YSCB contributes.knowledge_db 語言宣告規格模型"""
    id: str
    name: str
    extensions: Tuple[str, ...]
    mode: str = "tree_sitter"  # "tree_sitter" | "custom"
    grammar: Optional[str] = None
    query_file: Optional[str] = None
    parser_entry: Optional[str] = None
    custom_kinds: Tuple[Dict[str, str], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "extensions": list(self.extensions),
            "mode": self.mode,
            "grammar": self.grammar,
            "query_file": self.query_file,
            "parser_entry": self.parser_entry,
            "custom_kinds": [dict(k) for k in self.custom_kinds],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LanguageConfig":
        if not isinstance(data, dict):
            raise SchemaValidationError("LanguageConfig data must be a dict.")
        if "id" not in data or "extensions" not in data:
            raise SchemaValidationError("LanguageConfig requires 'id' and 'extensions'.")
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            extensions=tuple(str(e) for e in data.get("extensions", [])),
            mode=str(data.get("mode", "tree_sitter")),
            grammar=data.get("grammar"),
            query_file=data.get("query_file"),
            parser_entry=data.get("parser_entry"),
            custom_kinds=tuple(dict(k) for k in data.get("custom_kinds", [])),
        )


@dataclass(frozen=True)
class UnifiedSymbol:
    """通用階層化代碼與文檔符號模型 (一等公民符號節點，支援任意巢狀層級)"""
    id: str
    name: str
    kind: str
    file_path: str
    line_number: int
    language: str
    docstring: str = ""
    signature: str = ""
    end_line: int = 0
    fqn: str = ""
    scope_path: str = ""
    parent_id: Optional[str] = None
    children: Tuple[Any, ...] = ()
    parameters: Tuple[Dict[str, Any], ...] = ()
    return_type: str = ""
    search_payload: str = ""
    visibility: str = "public"
    members: Tuple[Any, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # 階層與成員欄位同步
        if not self.children and self.members:
            object.__setattr__(self, "children", tuple(self.members))
        elif not self.members and self.children:
            object.__setattr__(self, "members", tuple(self.children))

    @property
    def spaces(self) -> List[str]:
        """獲取該符號所屬之空間標籤清單"""
        sp = self.metadata.get("spaces", [])
        if isinstance(sp, list):
            return sp
        if isinstance(sp, str) and sp:
            return [sp]
        return []

    @classmethod
    def compute_id(cls, space: str, file_path: str, name: str, kind: str, line_number: int) -> str:
        """計算唯一 SHA1 雜湊識別碼"""
        normalized_path = file_path.replace("\\", "/")
        raw = f"{space}:{normalized_path}:{name}:{kind}:{line_number}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        meta = dict(self.metadata)
        if "space" in meta:
            single_sp = meta.pop("space")
            if "spaces" not in meta and single_sp:
                meta["spaces"] = [single_sp]
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
            "fqn": self.fqn,
            "scope_path": self.scope_path,
            "parent_id": self.parent_id,
            "children": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.children],
            "parameters": [dict(p) for p in self.parameters],
            "return_type": self.return_type,
            "search_payload": self.search_payload,
            "visibility": self.visibility,
            "metadata": meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol":
        if not isinstance(data, dict):
            raise SchemaValidationError("UnifiedSymbol data must be a dict.")
        required = ["id", "name", "kind", "file_path", "line_number", "language"]
        for key in required:
            if key not in data:
                raise SchemaValidationError(f"UnifiedSymbol missing required field '{key}'.")

        children_raw = data.get("children", [])
        children: List[Any] = []
        members: List[Any] = []
        for m in children_raw:
            if isinstance(m, dict):
                if "file_path" in m or "language" in m or "children" in m:
                    c_sym = cls.from_dict(m)
                    children.append(c_sym)
                    members.append(c_sym)
                else:
                    mem = MemberInfo.from_dict(m)
                    members.append(mem)
                    children.append(cls(
                        id=f"{data['id']}::{mem.name}",
                        name=mem.name,
                        kind=mem.kind,
                        file_path=data["file_path"],
                        line_number=mem.line_number,
                        end_line=mem.line_number,
                        language=data["language"],
                        signature=mem.signature,
                        docstring=mem.docstring,
                        visibility=mem.visibility,
                        parent_id=data["id"],
                    ))
            elif isinstance(m, cls):
                children.append(m)
                members.append(m)
            elif isinstance(m, MemberInfo):
                members.append(m)
                children.append(cls(
                    id=f"{data['id']}::{m.name}",
                    name=m.name,
                    kind=m.kind,
                    file_path=data["file_path"],
                    line_number=m.line_number,
                    end_line=m.line_number,
                    language=data["language"],
                    signature=m.signature,
                    docstring=m.docstring,
                    visibility=m.visibility,
                    parent_id=data["id"],
                ))

        params_raw = data.get("parameters", [])
        parameters = tuple(dict(p) for p in params_raw if isinstance(p, dict))
        metadata = dict(data.get("metadata", {}))
        if "space" in metadata:
            single_sp = metadata.pop("space")
            if "spaces" not in metadata and single_sp:
                metadata["spaces"] = [single_sp]

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
            fqn=str(data.get("fqn", "")),
            scope_path=str(data.get("scope_path", "")),
            parent_id=data.get("parent_id"),
            children=tuple(children),
            parameters=parameters,
            return_type=str(data.get("return_type", "")),
            search_payload=str(data.get("search_payload", "")),
            visibility=str(data.get("visibility", "public")),
            members=tuple(members),
            metadata=metadata,
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


@dataclass(frozen=True)
class SymbolCallSite:
    """
    符號調用點不可變模型 (Value Object)
    記錄單一調用表達式所在位置、調用上下文與被調用名稱。
    """
    callee_name: str             # 被調用之識別碼名稱 (如 'build_index' 或 'load_binary')
    line_number: int             # 調用所在行號 (1-based)
    caller_symbol_id: str = ""   # 調用者所屬頂層 UnifiedSymbol ID
    caller_member_name: str = "" # 若在類別/方法內，記錄方法名 (如 'KnowledgeEngine.search')
    context_prefix: str = ""     # 調用前綴 (如 'self.', 'InvertedIndex.', 'uri.')
    file_path: str = ""          # 相對於專案根目錄之正規化檔案路徑
    space: str = ""              # 所屬語意空間

    def to_dict(self) -> Dict[str, Any]:
        return {
            "callee_name": self.callee_name,
            "line_number": self.line_number,
            "caller_symbol_id": self.caller_symbol_id,
            "caller_member_name": self.caller_member_name,
            "context_prefix": self.context_prefix,
            "file_path": self.file_path,
            "space": self.space,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolCallSite":
        if not isinstance(data, dict):
            raise SchemaValidationError("SymbolCallSite data must be a dict.")
        return cls(
            callee_name=str(data.get("callee_name", "")),
            line_number=int(data.get("line_number", 0)),
            caller_symbol_id=str(data.get("caller_symbol_id", "")),
            caller_member_name=str(data.get("caller_member_name", "")),
            context_prefix=str(data.get("context_prefix", "")),
            file_path=str(data.get("file_path", "")),
            space=str(data.get("space", "")),
        )
