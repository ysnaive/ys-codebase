"""
Universal Tree-sitter AST driver (TreeSitterDriver) for module:ast.
Delegates all language-specific rules to `get_dialect(self.language_name)` and uses
`GrammarProvisioner` for stderr-isolated grammar loading.
"""

from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from core.log import log_warn

try:
    import tree_sitter
except ImportError:
    tree_sitter = None

from ..dialects import DialectAdapter, get_dialect
from ..provisioner import DEFAULT_GRAMMAR_PACKAGES, GrammarProvisioner
from ..schema import (
    LanguageConfig,
    MemberInfo,
    SymbolCallSite,
    UnifiedSymbol,
)
from .base import BaseParser

_DEFAULT_SCM_DIR = Path(__file__).resolve().parents[2] / "assets" / "queries"

BUILTIN_QUERIES: Mapping[str, str] = MappingProxyType({
    "python.scm": """
;; Python S-Expression Query for Universal AST
(class_definition
  name: (identifier) @symbol.name
  body: (block
    (expression_statement
      (string) @symbol.docstring)?
  )?
) @definition.class

(class_definition
  body: (block
    (expression_statement
      (assignment
        left: (identifier) @symbol.name
        type: (type)? @symbol.return_type
      ) @definition.field
    )
  )
)

(function_definition
  name: (identifier) @symbol.name
  parameters: (parameters) @symbol.signature
  return_type: (type)? @symbol.return_type
  body: (block
    (expression_statement
      (string) @symbol.docstring)?
  )?
) @definition.function

(assignment
  left: (attribute
    object: (identifier) @_self (#eq? @_self "self")
    attribute: (identifier) @symbol.name
  )
  type: (type)? @symbol.return_type
) @definition.field

(call
  function: [
    (identifier) @call.name
    (attribute attribute: (identifier) @call.name)
  ]
) @call.site

(import_statement) @import.stmt
(import_from_statement) @import.stmt
""",
    "c_sharp.scm": """
;; C# S-Expression Query for Universal AST
(class_declaration
  name: (identifier) @symbol.name
) @definition.class

(interface_declaration
  name: (identifier) @symbol.name
) @definition.interface

(struct_declaration
  name: (identifier) @symbol.name
) @definition.struct

(record_declaration
  name: (identifier) @symbol.name
) @definition.struct

(enum_declaration
  name: (identifier) @symbol.name
) @definition.enum

(namespace_declaration
  name: [(identifier) (qualified_name)] @symbol.name
) @definition.namespace

(file_scoped_namespace_declaration
  name: [(identifier) (qualified_name)] @symbol.name
) @definition.namespace

(method_declaration
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
  type: (_)? @symbol.return_type
) @definition.method

(local_function_statement
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
  type: (_)? @symbol.return_type
) @definition.function

(constructor_declaration
  name: (identifier) @symbol.name
  parameters: (parameter_list) @symbol.signature
) @definition.constructor

(property_declaration
  name: (identifier) @symbol.name
  type: (_)? @symbol.return_type
) @definition.property

(field_declaration
  (variable_declaration
    type: (_) @symbol.return_type
    (variable_declarator
      name: (identifier) @symbol.name
    )
  )
) @definition.field

(invocation_expression
  function: [
    (identifier) @call.name
    (generic_name
      (identifier) @call.name
    )
    (member_access_expression
      name: (identifier) @call.name
    )
    (member_access_expression
      name: (generic_name
        (identifier) @call.name
      )
    )
    (conditional_access_expression
      (member_binding_expression
        name: (identifier) @call.name
      )
    )
    (conditional_access_expression
      (member_binding_expression
        name: (generic_name
          (identifier) @call.name
        )
      )
    )
  ]
) @call.site

(using_directive) @import.stmt
""",
    "cpp.scm": """
;; C/C++ S-Expression Query for Universal AST
(class_specifier
  name: [(type_identifier) (template_type)] @symbol.name
) @definition.class

(struct_specifier
  name: [(type_identifier) (template_type)] @symbol.name
) @definition.struct

(enum_specifier
  name: (type_identifier) @symbol.name
) @definition.enum

(namespace_definition
  name: [(namespace_identifier) (nested_namespace_specifier)] @symbol.name
) @definition.namespace

(function_definition
  declarator: (function_declarator
    declarator: [(identifier) (field_identifier) (qualified_identifier) (destructor_name)] @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.function

(field_declaration
  declarator: (function_declarator
    declarator: [(field_identifier) (destructor_name)] @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.method

(field_declaration
  declarator: (field_identifier) @symbol.name
) @definition.field

(preproc_def
  name: (identifier) @symbol.name
) @definition.macro

(preproc_function_def
  name: (identifier) @symbol.name
  parameters: (preproc_params) @symbol.signature
) @definition.macro

(call_expression
  function: [
    (identifier) @call.name
    (template_function
      name: (identifier) @call.name
    )
    (field_expression
      field: (field_identifier) @call.name
    )
    (field_expression
      field: (template_method
        name: (field_identifier) @call.name
      )
    )
    (qualified_identifier
      name: (identifier) @call.name
    )
    (qualified_identifier
      name: (template_function
        name: (identifier) @call.name
      )
    )
  ]
) @call.site
""",
    "c.scm": """
;; C S-Expression Query for Universal AST
(struct_specifier
  name: (type_identifier) @symbol.name
) @definition.struct

(enum_specifier
  name: (type_identifier) @symbol.name
) @definition.enum

(union_specifier
  name: (type_identifier) @symbol.name
) @definition.union

(function_definition
  declarator: (function_declarator
    declarator: (identifier) @symbol.name
    parameters: (parameter_list) @symbol.signature
  )
) @definition.function

(call_expression
  function: [
    (identifier) @call.name
    (field_expression
      field: (field_identifier) @call.name
    )
  ]
) @call.site
""",
    "javascript.scm": """
;; JavaScript S-Expression Query for Universal AST
(class_declaration
  name: (identifier) @symbol.name
) @definition.class

(function_declaration
  name: (identifier) @symbol.name
  parameters: (formal_parameters) @symbol.signature
) @definition.function

(method_definition
  name: [(property_identifier) (identifier)] @symbol.name
  parameters: (formal_parameters) @symbol.signature
) @definition.method

(variable_declarator
  name: (identifier) @symbol.name
  value: (function_expression
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(variable_declarator
  name: (identifier) @symbol.name
  value: (arrow_function
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(call_expression
  function: [
    (identifier) @call.name
    (member_expression
      property: (property_identifier) @call.name
    )
  ]
) @call.site

(import_statement) @import.stmt
(export_statement) @export.stmt
""",
    "typescript.scm": """
;; TypeScript S-Expression Query for Universal AST
(class_declaration
  name: (type_identifier) @symbol.name
) @definition.class

(interface_declaration
  name: (type_identifier) @symbol.name
) @definition.interface

(enum_declaration
  name: (identifier) @symbol.name
) @definition.enum

(type_alias_declaration
  name: (type_identifier) @symbol.name
) @definition.type

(function_declaration
  name: (identifier) @symbol.name
  parameters: (formal_parameters) @symbol.signature
  return_type: (type_annotation)? @symbol.return_type
) @definition.function

(method_definition
  name: [(property_identifier) (identifier)] @symbol.name
  parameters: (formal_parameters) @symbol.signature
  return_type: (type_annotation)? @symbol.return_type
) @definition.method

(variable_declarator
  name: (identifier) @symbol.name
  value: (function_expression
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(variable_declarator
  name: (identifier) @symbol.name
  value: (arrow_function
    parameters: (formal_parameters) @symbol.signature
  )
) @definition.function

(call_expression
  function: [
    (identifier) @call.name
    (member_expression
      property: (property_identifier) @call.name
    )
  ]
) @call.site

(import_statement) @import.stmt
(export_statement) @export.stmt
""",
    "markdown.scm": """
;; Markdown S-Expression Query for Universal AST
(atx_heading
  (inline) @symbol.name
) @definition.heading

(setext_heading
  (paragraph) @symbol.name
) @definition.heading

(pipe_table) @definition.table
""",
})


class TreeSitterDriver(BaseParser):
    """
    Universal Tree-sitter AST driver.
    Uses `DialectAdapter` (`get_dialect(self.language_name)`) for all language-specific semantics
    and `GrammarProvisioner` for on-demand grammar loading.
    """

    def __init__(self, config: LanguageConfig, scm_dir: Optional[Path] = None):
        self.config = config
        self.language_name: str = config.id
        self.dialect: DialectAdapter = get_dialect(self.language_name)
        self._scm_dir: Path = scm_dir or _DEFAULT_SCM_DIR
        self._language: Optional[Any] = None
        self._parser: Optional[Any] = None
        self._query: Optional[Any] = None
        self._cache_lock = threading.RLock()
        self._last_parse_cache: Optional[Tuple[str, int, str, bytes, List[Tuple[int, Dict[str, List[Any]]]]]] = None
        self._init_driver()

    def _init_driver(self) -> None:
        """Load Tree-sitter grammar via GrammarProvisioner and compile S-Expression query."""
        if tree_sitter is None or self.config.mode != "tree_sitter":
            return

        if self.config.grammar:
            grammar_str = self.config.grammar
            if ":" in grammar_str:
                mod_name, func_name = grammar_str.split(":", 1)
            else:
                mod_name = grammar_str
                func_name = "language"

            ts_lang = GrammarProvisioner.load_language(
                lang_key=self.language_name,
                module_name=mod_name,
                func_name=func_name,
            )
            if ts_lang is not None:
                try:
                    self._language = ts_lang
                    self._parser = tree_sitter.Parser(self._language)
                except Exception as exc:
                    log_warn(f"TreeSitterDriver: Failed initializing parser for '{self.language_name}': {exc}")
                    self._language = None
                    self._parser = None

        if self._language and self.config.query_file:
            q_name = Path(self.config.query_file).name
            candidates = [
                Path(self.config.query_file),
                self._scm_dir / q_name,
                Path(__file__).resolve().parents[2] / self.config.query_file,
                Path(__file__).resolve().parents[1] / self.config.query_file,
            ]
            q_str: Optional[str] = None
            for c in candidates:
                if c.exists() and c.is_file():
                    try:
                        with open(c, "r", encoding="utf-8") as f:
                            q_str = f.read()
                        break
                    except Exception:
                        pass

            if q_str is None and q_name in BUILTIN_QUERIES:
                q_str = BUILTIN_QUERIES[q_name]

            if q_str:
                try:
                    self._query = tree_sitter.Query(self._language, q_str)
                except Exception as exc:
                    log_warn(f"TreeSitterDriver: Failed compiling query for '{self.language_name}': {exc}")
                    self._query = None
            else:
                log_warn(f"TreeSitterDriver: Query file '{self.config.query_file}' not found for '{self.language_name}'")
                self._query = None

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        supported = getattr(self, "SUPPORTED_EXTENSIONS", None)
        if supported:
            return ext in supported
        return ext in self.config.extensions

    def _extract_preceding_comment(self, node: Any) -> str:
        """Extract immediately preceding comment siblings as docstring via dialect adapter."""
        try:
            target_node = node
            if target_node.parent and target_node.parent.type in ("export_statement", "decorated_definition"):
                target_node = target_node.parent
            curr = target_node.prev_named_sibling
            comment_lines: List[str] = []
            while curr and curr.type == "comment":
                comment_lines.insert(0, curr.text.decode("utf-8", errors="replace"))
                curr = curr.prev_named_sibling
            if comment_lines:
                return self.dialect.clean_docstring("\n".join(comment_lines))
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_base_types(def_node: Any) -> List[str]:
        """Extract base class and implemented interface short names from class/struct/interface AST node."""
        base_types: List[str] = []
        try:
            for child in def_node.children:
                if child.type in ("base_list", "base_class_clause", "class_heritage", "argument_list"):
                    raw_text = child.text.decode("utf-8", errors="replace")
                    cleaned = re.sub(r"\b(extends|implements|public|protected|private|virtual)\b", " ", raw_text)
                    cleaned = cleaned.strip().lstrip(":(").rstrip(")")
                    cleaned = re.sub(r"<[^>]+>", "", cleaned)
                    for part in cleaned.split(","):
                        token = part.strip()
                        if not token:
                            continue
                        short_base = re.split(r"[.:]+", token)[-1].strip()
                        if short_base and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", short_base):
                            if short_base not in base_types:
                                base_types.append(short_base)
        except Exception:
            pass
        return base_types

    def _extract_raw_definition_items(
        self,
        matches: List[Tuple[int, Dict[str, List[Any]]]],
        lines: List[str],
    ) -> List[Dict[str, Any]]:
        """Stage 1: Extract raw symbol definitions from query matches and run dialect hooks."""
        raw_items: List[Dict[str, Any]] = []
        for _, captures in matches:
            def_capture_key = next((k for k in captures if k.startswith("definition.")), None)
            if not def_capture_key:
                continue

            def_kind = def_capture_key.split(".", 1)[1]
            def_nodes = captures[def_capture_key]
            if not def_nodes:
                continue
            def_node = def_nodes[0]

            raw_b = def_node.text
            nl = raw_b.find(b"\n")
            first_line = (raw_b[:nl] if nl != -1 else raw_b).decode("utf-8", errors="replace").rstrip("\r").strip()

            name = ""
            if "symbol.name" in captures and captures["symbol.name"]:
                name = captures["symbol.name"][0].text.decode("utf-8", errors="replace").strip()
            if not name:
                name = first_line[:60].strip()

            if first_line.endswith("{") or first_line.endswith(":"):
                first_line = first_line[:-1].strip()

            captured_sig = ""
            if "symbol.signature" in captures and captures["symbol.signature"]:
                captured_sig = captures["symbol.signature"][0].text.decode("utf-8", errors="replace").strip()

            signature = self.dialect.format_signature(
                first_line=first_line,
                captured_signature=captured_sig,
                name=name,
                def_kind=def_kind,
            )

            return_type = ""
            if "symbol.return_type" in captures and captures["symbol.return_type"]:
                return_type = captures["symbol.return_type"][0].text.decode("utf-8", errors="replace").strip()
                if return_type.startswith("->"):
                    return_type = return_type[2:].strip()
                if return_type.startswith(":"):
                    return_type = return_type[1:].strip()

            docstring = ""
            if "symbol.docstring" in captures and captures["symbol.docstring"]:
                raw_doc = captures["symbol.docstring"][0].text.decode("utf-8", errors="replace")
                docstring = self.dialect.clean_docstring(raw_doc)
            if not docstring:
                docstring = self._extract_preceding_comment(def_node)

            start_line = def_node.start_point[0] + 1
            end_line = def_node.end_point[0] + 1

            item = {
                "short_name": name,
                "kind": def_kind,
                "signature": signature,
                "return_type": return_type,
                "docstring": docstring,
                "start_line": start_line,
                "end_line": end_line,
                "start_byte": def_node.start_byte,
                "end_byte": def_node.end_byte,
                "node": def_node,
                "is_static": self.dialect.is_static_symbol(
                    def_node=def_node,
                    signature=signature,
                    lines=lines,
                    start_line=start_line,
                ),
            }
            self.dialect.post_process_raw_item(item, def_node)
            raw_items.append(item)

        return self.dialect.finalize_raw_items(raw_items, lines)

    def _build_symbol_hierarchy(
        self,
        raw_items: List[Dict[str, Any]],
        normalized_path: str,
        space: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Stage 2: Deduplicate, sort, and build parent-child hierarchy & FQN via stack algorithm."""
        seen_keys = set()
        dedup_items: List[Dict[str, Any]] = []
        for item in raw_items:
            k = (item["start_byte"], item["end_byte"], item["kind"], item["short_name"])
            if k not in seen_keys:
                seen_keys.add(k)
                dedup_items.append(item)

        dedup_items.sort(key=lambda x: (x["start_byte"], -x["end_byte"]))
        scope_sep = self.dialect.scope_separator
        stack: List[Dict[str, Any]] = []

        # Track same-line overload collisions so same-line overloads receive distinct IDs
        line_name_counts: Dict[Tuple[int, str, str], int] = {}
        for item in dedup_items:
            norm_kind = "method" if item["kind"] == "function" else item["kind"]
            key = (item["start_line"], norm_kind, item["short_name"])
            line_name_counts[key] = line_name_counts.get(key, 0) + 1

        for item in dedup_items:
            while stack and not (
                stack[-1]["start_byte"] <= item["start_byte"] and item["end_byte"] <= stack[-1]["end_byte"]
            ):
                stack.pop()

            if stack:
                parent = stack[-1]
                # If a field is defined inside a method/constructor (e.g., `self.x = ...` in `__init__`),
                # attach it to the enclosing class/struct/interface container if one exists on the stack.
                if item["kind"] in ("field", "property") and parent["kind"] in ("method", "function", "constructor"):
                    for ancestor in reversed(stack[:-1]):
                        if ancestor["kind"] in ("class", "struct", "interface"):
                            parent = ancestor
                            break
                item["parent_id"] = parent["id"]
                item["parent_kind"] = parent["kind"]
                item["scope_path"] = parent["scope_path"] + [parent["short_name"]]
                item["fqn"] = scope_sep.join(item["scope_path"] + [item["short_name"]])
                if item["kind"] == "function" and parent["kind"] in ("class", "struct", "interface"):
                    item["kind"] = "method"
                if not any(
                    c["kind"] == item["kind"]
                    and c["short_name"] == item["short_name"]
                    and c.get("signature") == item.get("signature")
                    and c.get("start_line") == item.get("start_line")
                    for c in parent["children_items"]
                ):
                    parent["children_items"].append(item)
            else:
                item["parent_id"] = None
                item["parent_kind"] = None
                item["scope_path"] = []
                item["fqn"] = item["short_name"]

            resolved_out_of_line = self.dialect.resolve_out_of_line_scope(
                name=item["short_name"],
                parent_scope=item["scope_path"][-1] if item["scope_path"] else "",
                kind=item["kind"],
            )
            item["_resolved_out_of_line"] = resolved_out_of_line
            _, _, resolved_kind = resolved_out_of_line
            item["kind"] = resolved_kind

            collision_key = (item["start_line"], "method" if item["kind"] == "function" else item["kind"], item["short_name"])
            sig_hint = item["signature"] if line_name_counts.get(collision_key, 0) > 1 else ""
            item["id"] = UnifiedSymbol.compute_id(
                space=space,
                file_path=normalized_path,
                name=item["fqn"],
                kind=item["kind"],
                line_number=item["start_line"],
                signature_hint=sig_hint,
            )
            item["children_items"] = []
            stack.append(item)

        return dedup_items, scope_sep

    def _materialize_unified_symbols(
        self,
        dedup_items: List[Dict[str, Any]],
        normalized_path: str,
        scope_sep: str,
        source_bytes: bytes = b"",
    ) -> List[UnifiedSymbol]:
        """Stage 3: Materialize hierarchy items into UnifiedSymbol instances."""
        symbols: List[UnifiedSymbol] = []
        for item in dedup_items:
            if item["kind"] == "field" and item["parent_id"]:
                continue

            members_list: List[MemberInfo] = []
            field_types: Dict[str, str] = {}
            for child in item["children_items"]:
                c_name = child["short_name"]
                vis = self.dialect.extract_visibility(
                    node=child.get("node"),
                    source_bytes=source_bytes,
                    parent_kind=item["kind"],
                    default_vis="public",
                    short_name=c_name,
                    kind=child["kind"],
                )
                if child["kind"] in ("field", "property") and child.get("return_type"):
                    raw_t = re.sub(r"<[^>]+>", "", str(child["return_type"])).strip().rstrip("?[]")
                    short_t = re.split(r"[.:]+", raw_t)[-1].strip()
                    if short_t and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", short_t):
                        field_types[c_name] = short_t
                members_list.append(
                    MemberInfo(
                        name=c_name,
                        kind=child["kind"],
                        signature=child["signature"],
                        docstring=child["docstring"],
                        visibility=vis,
                        line_number=child["start_line"],
                        is_static=bool(child.get("is_static", False)),
                    )
                )

            search_payload = f"{item['fqn']} {item['short_name']} {item['docstring']} {item['signature']}".strip()
            sym_name = item["fqn"] if item["parent_id"] else item["short_name"]
            short_name_val = item["short_name"]
            parent_scope_val = item["scope_path"][-1] if item["scope_path"] else ""

            cached_resolved = item.get("_resolved_out_of_line")
            if cached_resolved is not None:
                short_name_val, parent_scope_val, resolved_kind = cached_resolved
            else:
                short_name_val, parent_scope_val, resolved_kind = self.dialect.resolve_out_of_line_scope(
                    name=short_name_val,
                    parent_scope=parent_scope_val,
                    kind=item["kind"],
                )
            item["kind"] = resolved_kind

            sym_vis = self.dialect.extract_visibility(
                node=item.get("node"),
                source_bytes=source_bytes,
                parent_kind=item.get("parent_kind"),
                default_vis="public",
                short_name=short_name_val,
                kind=item["kind"],
            )

            base_types: List[str] = []
            is_partial = False
            if item["kind"] in ("class", "struct", "interface") and item.get("node") is not None:
                base_types = self._extract_base_types(item["node"])
                mods = self.dialect.extract_modifiers(item["node"])
                if "partial" in mods:
                    is_partial = True

            metadata: Dict[str, Any] = {
                "short_name": short_name_val,
                "parent_scope": parent_scope_val,
                "end_line": item["end_line"],
                "scope_path": item["scope_path"],
                "start_byte": item["start_byte"],
                "end_byte": item["end_byte"],
            }
            if base_types:
                metadata["base_types"] = base_types
            if is_partial:
                metadata["is_partial"] = True
            if item.get("is_static"):
                metadata["is_static"] = True
            if field_types:
                metadata["field_types"] = field_types

            symbols.append(
                UnifiedSymbol(
                    id=item["id"],
                    name=sym_name,
                    kind=item["kind"],
                    file_path=normalized_path,
                    line_number=item["start_line"],
                    end_line=item["end_line"],
                    language=self.language_name,
                    docstring=item["docstring"],
                    signature=item["signature"],
                    fqn=item["fqn"],
                    scope_path=scope_sep.join(item["scope_path"]),
                    parent_id=item["parent_id"],
                    children=tuple(members_list),
                    parameters=(),
                    return_type=item["return_type"],
                    search_payload=search_payload,
                    visibility=sym_vis,
                    members=tuple(members_list),
                    metadata=metadata,
                )
            )
        return symbols

    def _get_bytes_and_matches(
        self,
        normalized_path: str,
        content: str,
    ) -> Optional[Tuple[bytes, List[Tuple[int, Dict[str, List[Any]]]]]]:
        """Parse `content` or reuse single-entry thread-safe `_last_parse_cache`."""
        with self._cache_lock:
            cached = self._last_parse_cache
            if (
                cached is not None
                and cached[0] == normalized_path
                and cached[1] == len(content)
                and cached[2] == content
            ):
                return cached[3], cached[4]
            try:
                content_bytes = content.encode("utf-8", errors="replace")
                tree = self._parser.parse(content_bytes)
                cursor = tree_sitter.QueryCursor(self._query)
                matches = cursor.matches(tree.root_node)
            except Exception as exc:
                log_warn(f"TreeSitterDriver: parse error on '{normalized_path}': {exc}")
                return None
            self._last_parse_cache = (normalized_path, len(content), content, content_bytes, matches)
            return content_bytes, matches

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        lines = content.splitlines()
        if self._parser is None or self._query is None:
            if self._language is None and self.config.mode == "tree_sitter" and self.config.grammar:
                grammar_str = self.config.grammar
                mod_name = grammar_str.split(":", 1)[0] if ":" in grammar_str else grammar_str
                pkg_name = DEFAULT_GRAMMAR_PACKAGES.get(mod_name) or mod_name.replace("_", "-")
                GrammarProvisioner._emit_warning(pkg_name)
            return self.dialect.fallback_symbols(normalized_path, lines, space)

        parsed_res = self._get_bytes_and_matches(normalized_path, content)
        if parsed_res is None:
            return []
        content_bytes, matches = parsed_res

        raw_items = self._extract_raw_definition_items(matches, lines)
        if not raw_items:
            return self.dialect.fallback_symbols(normalized_path, lines, space)

        dedup_items, scope_sep = self._build_symbol_hierarchy(raw_items, normalized_path, space)
        return self._materialize_unified_symbols(dedup_items, normalized_path, scope_sep, source_bytes=content_bytes)

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        custom_sites = self.dialect.extract_custom_call_sites(normalized_path, content, space)
        if custom_sites is not None:
            return custom_sites

        if self._parser is None or self._query is None:
            return []

        parsed_res = self._get_bytes_and_matches(normalized_path, content)
        if parsed_res is None:
            return []
        content_bytes, matches = parsed_res

        target_symbols = (
            symbols if symbols is not None else self.parse(file_path=file_path, content=content, space=space)
        )
        sorted_target_symbols = sorted(target_symbols, key=lambda s: (s.end_line - s.line_number))
        call_sites: List[SymbolCallSite] = []

        for _, captures in matches:
            if "call.name" not in captures or not captures["call.name"]:
                continue

            name_node = captures["call.name"][0]
            callee_name = name_node.text.decode("utf-8", errors="replace").strip()
            line_no = name_node.start_point[0] + 1

            prefix = ""
            call_node = captures.get("call.site", [name_node])[0]
            if call_node.start_byte < name_node.start_byte:
                raw_prefix = content_bytes[call_node.start_byte : name_node.start_byte].decode(
                    "utf-8", errors="replace"
                ).strip()
                prefix = self.dialect.normalize_call_receiver(raw_prefix)

            caller_name = "<module>"
            caller_sym_id: Optional[str] = None
            enclosing = next(
                (
                    s
                    for s in sorted_target_symbols
                    if s.line_number <= line_no <= s.end_line
                    and s.kind in ("method", "function", "constructor", "property", "class", "struct", "interface")
                ),
                None,
            )
            if enclosing is not None:
                if enclosing.kind in ("method", "function", "constructor", "property"):
                    caller_sym_id = enclosing.id
                    if enclosing.metadata.get("parent_scope"):
                        caller_name = f"{enclosing.metadata['parent_scope']}.{enclosing.metadata.get('short_name', enclosing.name)}"
                    else:
                        caller_name = enclosing.name
                elif enclosing.kind in ("class", "struct", "interface"):
                    caller_sym_id = enclosing.id
                    caller_name = enclosing.metadata.get("short_name") or enclosing.name

            call_sites.append(
                SymbolCallSite(
                    callee_name=callee_name,
                    line_number=line_no,
                    caller_symbol_id=caller_sym_id or "",
                    caller_member_name=caller_name,
                    context_prefix=prefix,
                    file_path=normalized_path,
                    space=space,
                )
            )

        return call_sites

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        if not content:
            return {}
        return self.dialect.extract_imports(content, file_path=file_path)
