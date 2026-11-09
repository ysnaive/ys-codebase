"""
Universal Tree-sitter AST driver (TreeSitterDriver) for module:ast.
Delegates all language-specific rules to `get_dialect(self.language_name)` and uses
`GrammarProvisioner` for stderr-isolated grammar loading.
"""

from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Pattern, Set, Tuple, Union

from core.log import log_warn

try:
    import tree_sitter
except ImportError:
    tree_sitter = None

from ..dialects import DialectAdapter, get_dialect
from ..provisioner import DEFAULT_GRAMMAR_PACKAGES, GrammarProvisioner
from ..schema import (
    FileSymbolGraph,
    LanguageConfig,
    MemberInfo,
    ProvenanceStep,
    RelationEdge,
    Span,
    SymbolCallSite,
    SymbolNode,
    UnifiedSymbol,
)
from .base import BaseParser, SymbolProcessor, compute_content_hash

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

    def __init__(
        self,
        config: LanguageConfig,
        scm_dir: Optional[Path] = None,
        processors: Optional[Tuple[SymbolProcessor, ...]] = None,
    ):
        self.config = config
        self.language_name: str = config.id
        self.dialect: DialectAdapter = get_dialect(self.language_name)
        self._scm_dir: Path = scm_dir or _DEFAULT_SCM_DIR
        self._language: Optional[Any] = None
        self._parser: Optional[Any] = None
        self._query: Optional[Any] = None
        self._queries: List[Tuple[str, Any]] = []
        self._query_directives: Dict[str, Dict[str, Any]] = {}
        self._processors: Tuple[SymbolProcessor, ...] = tuple(processors) if processors else ()
        self._cache_lock = threading.RLock()
        self._last_parse_cache: Optional[Tuple[str, int, str, bytes, List[Tuple[int, Dict[str, List[Any]]]]]] = None
        self._init_driver()

    @staticmethod
    def _parse_scm_directives(q_str: str) -> Dict[str, Any]:
        """
        Parse official Tree-sitter `tags.scm` directives:
        - `(#strip! @capture "regex")`
        - `(#select-adjacent! @doc_cap @def_cap)`
        """
        strip_rules: Dict[str, List[Pattern[str]]] = {}
        select_adjacent: List[Tuple[str, str]] = []
        for m in re.finditer(
            r'\(#strip!\s+@([A-Za-z0-9_.]+)\s+"((?:\\.|[^"\\])*)"\)',
            q_str,
        ):
            cap_name = m.group(1).strip()
            raw_pat = m.group(2)
            # Unescape double-escaped backslashes common in S-expression strings
            unescaped_pat = raw_pat.replace("\\\\", "\\")
            try:
                compiled_rx = re.compile(unescaped_pat)
                strip_rules.setdefault(cap_name, []).append(compiled_rx)
            except re.error:
                pass

        for m in re.finditer(
            r"\(#select-adjacent!\s+@([A-Za-z0-9_.]+)\s+@([A-Za-z0-9_.]+)\)",
            q_str,
        ):
            select_adjacent.append((m.group(1).strip(), m.group(2).strip()))

        return {
            "strip": strip_rules,
            "select_adjacent": select_adjacent,
        }

    @staticmethod
    def _sanitize_query_for_compiler(q_str: str) -> str:
        """
        Replace non-builtin Tree-sitter tags directives (`#strip!`, `#select-adjacent!`)
        with whitespace so `tree_sitter.Query` compiles cleanly.
        """
        return re.sub(
            r"\(#(?:strip|select-adjacent)![^)]*\)",
            lambda m: " " * len(m.group(0)),
            q_str,
        )

    @staticmethod
    def _apply_select_adjacent_nodes(
        doc_nodes: List[Any],
        def_node: Any,
    ) -> List[Any]:
        """
        Filter `doc_nodes` according to Tree-sitter `(#select-adjacent! @doc @definition.*)`:
        keep only the contiguous block of comment nodes immediately preceding `def_node`
        with no intervening blank lines or non-comment syntax nodes.
        """
        if not doc_nodes or def_node is None:
            return doc_nodes
        def_start_line = int(def_node.start_point[0])
        preceding = [
            dn for dn in doc_nodes if int(dn.start_point[0]) < def_start_line
        ]
        preceding.sort(key=lambda n: (int(n.start_point[0]), int(n.start_byte)))
        selected: List[Any] = []
        expected_max_line = def_start_line
        for dn in reversed(preceding):
            dn_start = int(dn.start_point[0])
            dn_end = int(dn.end_point[0])
            # In Tree-sitter, single-line comments with trailing `\n` have `end_point = (dn_start + 1, 0)`
            effective_end_line = (
                dn_end - 1
                if (dn_end > dn_start and int(dn.end_point[1]) == 0)
                else dn_end
            )
            if expected_max_line - effective_end_line <= 1:
                selected.insert(0, dn)
                expected_max_line = dn_start
            else:
                break
        return selected

    @staticmethod
    def _apply_strip_directives(raw_text: str, regex_list: List[Any]) -> str:
        """Apply `(#strip! @doc "regex")` line-by-line to captured documentation text."""
        if not raw_text or not regex_list:
            return raw_text
        stripped_lines: List[str] = []
        for line in raw_text.splitlines():
            curr = line
            for rx in regex_list:
                curr = rx.sub("", curr)
            stripped_lines.append(curr.strip())
        return "\n".join(ln for ln in stripped_lines if ln).strip()

    def _resolve_query_source(self, query_path_str: str) -> Optional[str]:
        """Resolve an `.scm` query string from URI, filesystem candidates, or `BUILTIN_QUERIES`."""
        q_str: Optional[str] = None
        if "://" in query_path_str:
            try:
                from core import uri

                resolved_q = uri.resolve(query_path_str, interactive=False)
                if resolved_q and not str(resolved_q).startswith("!undefined"):
                    rp = Path(resolved_q)
                    if rp.is_file():
                        with open(rp, "r", encoding="utf-8") as f:
                            return f.read()
            except Exception:
                pass

        q_name = Path(query_path_str).name
        candidates = [
            Path(query_path_str),
            self._scm_dir / q_name,
            Path(__file__).resolve().parents[2] / query_path_str,
            Path(__file__).resolve().parents[1] / query_path_str,
        ]
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
        return q_str

    def _init_driver(self) -> None:
        """Load Tree-sitter grammar via GrammarProvisioner and compile peer S-Expression queries."""
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
                    log_warn(f"TreeSitterDriver: Failed initializing parser for '{self.language_name}': {exc}", stream="stderr")
                    self._language = None
                    self._parser = None

        query_paths = list(self.config.query_files)
        if not query_paths and self.config.query_file:
            query_paths = [self.config.query_file]

        self._queries = []
        self._query_directives = {}
        self._query = None
        if self._language and query_paths:
            for q_path in query_paths:
                q_str = self._resolve_query_source(q_path)
                if not q_str:
                    log_warn(f"TreeSitterDriver: Query file '{q_path}' not found for '{self.language_name}'", stream="stderr")
                    continue
                try:
                    directives = self._parse_scm_directives(q_str)
                    clean_q_str = self._sanitize_query_for_compiler(q_str)
                    compiled_q = tree_sitter.Query(self._language, clean_q_str)
                    q_name = Path(q_path).name
                    prov_id = f"ast:{self.language_name}/{q_name}"
                    self._queries.append((prov_id, compiled_q))
                    self._query_directives[prov_id] = directives
                except Exception as exc:
                    log_warn(f"TreeSitterDriver: Failed compiling query '{q_path}' for '{self.language_name}': {exc}", stream="stderr")
            if self._queries:
                self._query = self._queries[0][1]

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        supported = getattr(self, "SUPPORTED_EXTENSIONS", None)
        if supported:
            return ext in supported
        return ext in self.config.extensions

    @staticmethod
    def _node_to_span(node: Any) -> Span:
        """Convert a Tree-sitter CST `Node` into a 0-based byte / 1-based line `Span`."""
        return Span(
            start_byte=int(node.start_byte),
            end_byte=int(node.end_byte),
            start_line=int(node.start_point[0]) + 1,
            start_col=int(node.start_point[1]),
            end_line=int(node.end_point[0]) + 1,
            end_col=int(node.end_point[1]),
        )

    @staticmethod
    def _extract_overload_param_suffix(signature_or_params: str) -> str:
        """Extract normalized parameter list suffix `(param1, param2)` for overload disambiguation."""
        if not signature_or_params:
            return ""
        text = signature_or_params.strip()
        lpar = text.find("(")
        rpar = text.rfind(")")
        if lpar != -1 and rpar != -1 and rpar >= lpar:
            inner = text[lpar + 1 : rpar].strip()
            inner_norm = " ".join(inner.split())
            return f"({inner_norm})"
        return f"({text})"

    def _extract_preceding_comment(self, node: Any) -> str:
        """Extract immediately preceding contiguous comment siblings as docstring via dialect adapter."""
        try:
            target_node = node
            if target_node.parent and target_node.parent.type in ("export_statement", "decorated_definition"):
                target_node = target_node.parent
            curr = target_node.prev_named_sibling
            comment_nodes: List[Any] = []
            while curr and curr.type == "comment":
                comment_nodes.insert(0, curr)
                curr = curr.prev_named_sibling
            if comment_nodes:
                adj_nodes = self._apply_select_adjacent_nodes(comment_nodes, target_node)
                if adj_nodes:
                    raw = "\n".join(cn.text.decode("utf-8", errors="replace") for cn in adj_nodes)
                    return self.dialect.clean_docstring(raw)
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_base_types(def_node: Any) -> List[str]:
        """Extract base class and implemented interface expressions from class/struct/interface AST node."""
        return [expr for expr, _ in TreeSitterDriver._extract_base_type_relations(def_node)]

    @staticmethod
    def _extract_base_type_relations(def_node: Any) -> List[Tuple[str, str]]:
        """
        Extract `(base_type_expr, edge_kind)` pairs (`"inherits"` or `"implements"`) from a type AST node.
        Preserves qualified expressions (e.g. `pkg.BaseClass`) while stripping generic `<...>` arguments.
        """
        relations: List[Tuple[str, str]] = []
        seen_exprs: Set[str] = set()
        try:
            for child in def_node.children:
                if child.type in ("base_list", "base_class_clause", "class_heritage", "argument_list"):
                    raw_text = child.text.decode("utf-8", errors="replace")
                    if child.type == "class_heritage":
                        # TS/JS: `extends Base implements IFoo, IBar`
                        no_gen = re.sub(r"<[^>]+>", "", raw_text)
                        for m_ext in re.finditer(r"\bextends\s+([^\s,{]+)", no_gen):
                            tok = m_ext.group(1).strip()
                            if tok and tok not in seen_exprs:
                                seen_exprs.add(tok)
                                relations.append((tok, "inherits"))
                        for m_imp in re.finditer(r"\bimplements\s+([^\{]+)", no_gen):
                            for part in m_imp.group(1).split(","):
                                tok = part.strip()
                                if tok and re.match(r"^[A-Za-z_][A-Za-z0-9_.:]*$", tok) and tok not in seen_exprs:
                                    seen_exprs.add(tok)
                                    relations.append((tok, "implements"))
                        if relations:
                            continue

                    cleaned = re.sub(r"\b(extends|implements|public|protected|private|virtual)\b", " ", raw_text)
                    cleaned = cleaned.strip().lstrip(":(").rstrip(")")
                    cleaned = re.sub(r"<[^>]+>", "", cleaned)
                    for part in cleaned.split(","):
                        token = part.strip()
                        if not token or "=" in token:
                            continue
                        short_base = re.split(r"[.:]+", token)[-1].strip()
                        if short_base and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", short_base):
                            edge_k = (
                                "implements"
                                if (len(short_base) >= 2 and short_base[0] == "I" and short_base[1].isupper())
                                else "inherits"
                            )
                            if token not in seen_exprs:
                                seen_exprs.add(token)
                                relations.append((token, edge_k))
        except Exception:
            pass
        return relations

    def _extract_raw_definition_items(
        self,
        matches: List[Tuple[int, Dict[str, List[Any]]]],
        lines: List[str],
    ) -> List[Dict[str, Any]]:
        """Stage 1: Extract raw symbol definitions from query matches and run dialect hooks."""
        raw_items: List[Dict[str, Any]] = []
        for match_elem in matches:
            if len(match_elem) == 3:
                prov_id, _, captures = match_elem  # type: ignore[misc]
            else:
                _, captures = match_elem
                prov_id = f"ast:{self.language_name}/default.scm"

            def_capture_keys = sorted(
                k
                for k, v in captures.items()
                if v and (k.startswith("definition.") or k.startswith("def."))
            )
            if not def_capture_keys:
                continue

            def_capture_key = def_capture_keys[0]
            def_kind = def_capture_key.split(".", 1)[1]
            all_def_nodes = [n for k in def_capture_keys for n in captures[k]]
            if not all_def_nodes:
                continue
            def_node = max(all_def_nodes, key=lambda n: int(n.end_byte) - int(n.start_byte))
            union_def_span = self._node_to_span(all_def_nodes[0])
            for dn_cand in all_def_nodes[1:]:
                union_def_span = union_def_span.union(self._node_to_span(dn_cand))

            raw_b = def_node.text
            nl = raw_b.find(b"\n")
            first_line = (raw_b[:nl] if nl != -1 else raw_b).decode("utf-8", errors="replace").rstrip("\r").strip()

            name_nodes = (
                captures.get("symbol.name")
                or captures.get("name")
                or captures.get("part.name")
                or []
            )
            name_node = name_nodes[0] if name_nodes else None
            name = ""
            if name_node is not None:
                name = name_node.text.decode("utf-8", errors="replace").strip()
            if not name:
                name = first_line[:60].strip()

            if first_line.endswith("{") or first_line.endswith(":"):
                first_line = first_line[:-1].strip()

            sig_nodes = (
                captures.get("symbol.signature")
                or captures.get("part.parameters")
                or captures.get("part.signature")
                or []
            )
            captured_sig = ""
            if sig_nodes:
                captured_sig = sig_nodes[0].text.decode("utf-8", errors="replace").strip()

            signature = self.dialect.format_signature(
                first_line=first_line,
                captured_signature=captured_sig,
                name=name,
                def_kind=def_kind,
            )

            ret_nodes = captures.get("symbol.return_type") or captures.get("part.return_type") or []
            return_type = ""
            if ret_nodes:
                return_type = ret_nodes[0].text.decode("utf-8", errors="replace").strip()
                if return_type.startswith("->"):
                    return_type = return_type[2:].strip()
                if return_type.startswith(":"):
                    return_type = return_type[1:].strip()

            doc_cap_key = (
                "symbol.docstring"
                if captures.get("symbol.docstring")
                else ("doc" if captures.get("doc") else ("part.doc" if captures.get("part.doc") else ""))
            )
            doc_nodes = list(captures.get(doc_cap_key) or []) if doc_cap_key else []
            q_dirs = self._query_directives.get(prov_id, {})
            if doc_nodes and q_dirs.get("select_adjacent"):
                if any(
                    adj_doc == doc_cap_key and (adj_def in def_capture_keys or adj_def.startswith("definition.") or adj_def.startswith("def."))
                    for adj_doc, adj_def in q_dirs["select_adjacent"]
                ):
                    doc_nodes = self._apply_select_adjacent_nodes(doc_nodes, def_node)

            docstring = ""
            if doc_nodes:
                raw_doc = "\n".join(dn.text.decode("utf-8", errors="replace") for dn in doc_nodes)
                strip_rxs = (q_dirs.get("strip") or {}).get(doc_cap_key) or []
                if strip_rxs:
                    raw_doc = self._apply_strip_directives(raw_doc, strip_rxs)
                docstring = self.dialect.clean_docstring(raw_doc)
            if not docstring:
                docstring = self._extract_preceding_comment(def_node)

            start_line = union_def_span.start_line
            end_line = union_def_span.end_line

            parts_spans: Dict[str, Span] = {}
            if name_node is not None:
                parts_spans["name"] = self._node_to_span(name_node)
            if sig_nodes:
                parts_spans["parameters"] = self._node_to_span(sig_nodes[0])
            if ret_nodes:
                parts_spans["return_type"] = self._node_to_span(ret_nodes[0])
            if doc_nodes:
                doc_sp = self._node_to_span(doc_nodes[0])
                for dn in doc_nodes[1:]:
                    doc_sp = doc_sp.union(self._node_to_span(dn))
                parts_spans["doc"] = doc_sp
            for cap_k, cap_nodes in captures.items():
                if cap_k.startswith("part.") and cap_nodes:
                    slot = cap_k.split(".", 1)[1]
                    slot_sp = self._node_to_span(cap_nodes[0])
                    for cn in cap_nodes[1:]:
                        slot_sp = slot_sp.union(self._node_to_span(cn))
                    parts_spans[slot] = parts_spans[slot].union(slot_sp) if slot in parts_spans else slot_sp

            captured_facets: Dict[str, Any] = {}
            for cap_k, cap_nodes in captures.items():
                if cap_k.startswith("facet.") and cap_nodes:
                    fkey = cap_k.split(".", 1)[1]
                    captured_facets[fkey] = cap_nodes[0].text.decode("utf-8", errors="replace").strip()

            all_kinds = {k.split(".", 1)[1] for k in def_capture_keys}
            prov_steps = [
                ProvenanceStep(provider_id=prov_id, action="extract", rule_or_hook=f"@{k}")
                for k in def_capture_keys
            ]

            item = {
                "short_name": name,
                "kind": def_kind,
                "kinds": all_kinds,
                "signature": signature,
                "return_type": return_type,
                "docstring": docstring,
                "start_line": start_line,
                "end_line": end_line,
                "start_byte": union_def_span.start_byte,
                "end_byte": union_def_span.end_byte,
                "span": union_def_span,
                "name_span": parts_spans.get("name"),
                "parts": parts_spans,
                "facets": captured_facets,
                "provenance": prov_steps,
                "node": def_node,
                "is_static": self.dialect.is_static_symbol(
                    def_node=def_node,
                    signature=signature,
                    lines=lines,
                    start_line=start_line,
                ),
            }
            self.dialect.post_process_raw_item(item, def_node)
            if item.get("kind"):
                item["kinds"].add(item["kind"])
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
    ) -> Optional[Tuple[bytes, List[Any]]]:
        """Parse `content` across all compiled peer `.scm` queries or reuse thread-safe `_last_parse_cache`."""
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
                all_matches: List[Any] = []
                active_queries = self._queries if self._queries else (
                    [(f"ast:{self.language_name}/default.scm", self._query)] if self._query is not None else []
                )
                for prov_id, q_obj in active_queries:
                    cursor = tree_sitter.QueryCursor(q_obj)
                    for pat_idx, cap_dict in cursor.matches(tree.root_node):
                        all_matches.append((prov_id, pat_idx, cap_dict))
            except Exception as exc:
                log_warn(f"TreeSitterDriver: parse error on '{normalized_path}': {exc}", stream="stderr")
                return None
            self._last_parse_cache = (normalized_path, len(content), content, content_bytes, all_matches)
            return content_bytes, all_matches

    @staticmethod
    def _select_primary_kind(kinds: Set[str]) -> str:
        """Select a deterministic primary structural kind from a `kinds` set (independent of merge order)."""
        if not kinds:
            return "variable"
        priority_order = (
            "class",
            "struct",
            "interface",
            "enum",
            "namespace",
            "module",
            "constructor",
            "method",
            "function",
            "property",
            "field",
        )
        for pk in priority_order:
            if pk in kinds:
                return pk
        return sorted(kinds)[0]

    @staticmethod
    def _commutatively_merge_raw_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Commutatively merge peer `.scm` captures sharing the same `@name` physical `Span(start_byte, end_byte)`.
        Guarantees order-independence ($A \\cup B = B \\cup A$) across kinds, bounding-box span, parts, facets, and provenance.
        """
        merged_by_anchor: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
        for item in raw_items:
            name_sp: Optional[Span] = item.get("name_span")
            if name_sp is not None:
                anchor_key = (name_sp.start_byte, name_sp.end_byte, item["short_name"])
            else:
                anchor_key = (item["start_byte"], item["end_byte"], item["short_name"])

            item_sp: Span = item.get("span") or Span(
                start_byte=item["start_byte"],
                end_byte=item["end_byte"],
                start_line=item["start_line"],
                start_col=0,
                end_line=item["end_line"],
                end_col=0,
            )
            item_kinds = set(item.get("kinds") or {item["kind"]})
            item_parts = dict(item.get("parts") or {})
            item_facets = dict(item.get("facets") or {})
            item_prov = list(item.get("provenance") or [])

            existing = merged_by_anchor.get(anchor_key)
            if existing is None:
                cloned = dict(item)
                cloned["span"] = item_sp
                cloned["kinds"] = item_kinds
                cloned["kind"] = TreeSitterDriver._select_primary_kind(item_kinds)
                cloned["parts"] = item_parts
                cloned["facets"] = item_facets
                cloned["provenance"] = item_prov
                merged_by_anchor[anchor_key] = cloned
                continue

            # 1. Span bounding-box union
            union_sp = existing["span"].union(item_sp)
            existing["span"] = union_sp
            existing["start_byte"] = union_sp.start_byte
            existing["end_byte"] = union_sp.end_byte
            existing["start_line"] = union_sp.start_line
            existing["end_line"] = union_sp.end_line

            # 2. Kinds set union (deterministic primary kind for legacy compat)
            existing["kinds"].update(item_kinds)
            existing["kind"] = TreeSitterDriver._select_primary_kind(existing["kinds"])

            # 3. Parts dictionary union
            ex_parts: Dict[str, Span] = existing["parts"]
            for slot, sp_val in item_parts.items():
                ex_parts[slot] = ex_parts[slot].union(sp_val) if slot in ex_parts else sp_val

            # 4. Facets deterministic merge
            ex_facets: Dict[str, Any] = existing["facets"]
            for fk, fv in item_facets.items():
                if fk not in ex_facets or not ex_facets[fk]:
                    ex_facets[fk] = fv
                elif isinstance(ex_facets[fk], (set, frozenset, list, tuple)) and isinstance(fv, (set, frozenset, list, tuple)):
                    ex_facets[fk] = tuple(sorted({str(x) for x in (*ex_facets[fk], *fv)}))
                elif str(fv) > str(ex_facets[fk]):
                    # Deterministic tie-breaker for scalar strings
                    ex_facets[fk] = fv

            # Deterministic longest non-empty signature / docstring / return_type selection
            for text_field in ("signature", "docstring", "return_type"):
                cand_val = str(item.get(text_field) or "")
                curr_val = str(existing.get(text_field) or "")
                if (len(cand_val), cand_val) > (len(curr_val), curr_val):
                    existing[text_field] = cand_val

            existing["is_static"] = bool(existing.get("is_static") or item.get("is_static"))

            # Prefer the wider CST node for base_types / modifier extraction
            ex_node = existing.get("node")
            cand_node = item.get("node")
            if cand_node is not None and (
                ex_node is None
                or (int(cand_node.end_byte) - int(cand_node.start_byte))
                > (int(ex_node.end_byte) - int(ex_node.start_byte))
            ):
                existing["node"] = cand_node

            # 5. Provenance set union
            existing["provenance"].extend(item_prov)

        out_list = list(merged_by_anchor.values())
        out_list.sort(key=lambda x: (x["start_byte"], -x["end_byte"], x["short_name"]))
        return out_list

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

        merged_items = self._commutatively_merge_raw_items(raw_items)
        dedup_items, scope_sep = self._build_symbol_hierarchy(merged_items, normalized_path, space)
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

        for match_elem in matches:
            captures = match_elem[2] if len(match_elem) == 3 else match_elem[1]
            name_nodes = captures.get("call.name") or captures.get("name") or []
            has_call_ref = any(k.startswith("reference.call") or k.startswith("edge.calls") for k in captures)
            if "call.name" not in captures and not has_call_ref:
                continue
            if not name_nodes:
                continue

            name_node = name_nodes[0]
            callee_name = name_node.text.decode("utf-8", errors="replace").strip()
            line_no = name_node.start_point[0] + 1

            prefix = ""
            call_candidates = (
                captures.get("call.site")
                or captures.get("reference.call")
                or captures.get("edge.calls")
                or [name_node]
            )
            call_node = call_candidates[0]
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

    def _build_recursive_symbol_nodes(
        self,
        merged_items: List[Dict[str, Any]],
        normalized_path: str,
        content_bytes: bytes,
    ) -> Tuple[Tuple[SymbolNode, ...], List[Dict[str, Any]]]:
        """Build an infinite-depth recursive `SymbolNode` hierarchy using a `Span` containment stack."""
        scope_sep = self.dialect.scope_separator
        stack: List[Dict[str, Any]] = []
        root_items: List[Dict[str, Any]] = []
        type_container_kinds = {"class", "struct", "interface"}
        callable_kinds = {"method", "function", "constructor"}

        for item in merged_items:
            while stack and not (
                stack[-1]["start_byte"] <= item["start_byte"] and item["end_byte"] <= stack[-1]["end_byte"]
            ):
                stack.pop()

            item_kinds_set: Set[str] = set(item.get("kinds") or {item["kind"]})
            item["kinds"] = item_kinds_set
            if stack:
                parent = stack[-1]
                parent_kinds_set: Set[str] = set(parent.get("kinds") or {parent["kind"]})
                if (item_kinds_set & {"field", "property"}) and (parent_kinds_set & callable_kinds):
                    for ancestor in reversed(stack[:-1]):
                        anc_kinds = set(ancestor.get("kinds") or {ancestor["kind"]})
                        if anc_kinds & type_container_kinds:
                            parent = ancestor
                            parent_kinds_set = anc_kinds
                            break
                parent_primary_kind = next(
                    (k for k in ("interface", "class", "struct") if k in parent_kinds_set),
                    parent["kind"],
                )
                item["parent_kind"] = parent_primary_kind
                item["scope_path"] = list(parent["scope_path"]) + [parent["short_name"]]
                if "function" in item["kinds"] and (parent_kinds_set & type_container_kinds):
                    item["kinds"].add("method")
                    item["kind"] = self._select_primary_kind(item["kinds"])
                parent["children_items"].append(item)
            else:
                item["parent_kind"] = None
                item["scope_path"] = []
                root_items.append(item)

            short_name_val, parent_scope_val, resolved_kind = self.dialect.resolve_out_of_line_scope(
                name=item["short_name"],
                parent_scope=item["scope_path"][-1] if item["scope_path"] else "",
                kind=item["kind"],
            )
            item["short_name"] = short_name_val
            if parent_scope_val and not item["scope_path"]:
                item["scope_path"] = [p for p in parent_scope_val.split(scope_sep) if p]
            item["kinds"].add(resolved_kind)
            item["kind"] = self._select_primary_kind(item["kinds"])
            item["fqn"] = scope_sep.join(item["scope_path"] + [item["short_name"]])
            item["children_items"] = []
            stack.append(item)

        fqn_counts: Dict[str, int] = {}
        for item in merged_items:
            fqn_counts[item["fqn"]] = fqn_counts.get(item["fqn"], 0) + 1

        for item in merged_items:
            overload_suffix = ""
            if fqn_counts.get(item["fqn"], 0) > 1:
                param_sp: Optional[Span] = item["parts"].get("parameters")
                if param_sp is not None:
                    overload_suffix = self._extract_overload_param_suffix(param_sp.slice_text(content_bytes))
                else:
                    overload_suffix = self._extract_overload_param_suffix(str(item.get("signature") or ""))
            item["canonical_id"] = SymbolNode.compute_canonical_id(
                file_path=normalized_path,
                fqn=item["fqn"],
                overload_suffix=overload_suffix,
            )

        def _to_symbol_node(it: Dict[str, Any]) -> SymbolNode:
            child_nodes = tuple(_to_symbol_node(c) for c in it["children_items"])
            vis = self.dialect.extract_visibility(
                node=it.get("node"),
                source_bytes=content_bytes,
                parent_kind=it.get("parent_kind"),
                default_vis="public",
                short_name=it["short_name"],
                kind=it["kind"],
            )
            facets_dict = dict(it.get("facets") or {})
            facets_dict.setdefault("visibility", vis)
            facets_dict.setdefault("scope_separator", scope_sep)
            if it.get("signature"):
                facets_dict.setdefault("signature", it["signature"])
            if it.get("docstring"):
                facets_dict.setdefault("docstring", it["docstring"])
            if it.get("return_type"):
                facets_dict.setdefault("return_type", it["return_type"])
            if it.get("is_static"):
                facets_dict["is_static"] = True

            if (it["kinds"] & type_container_kinds) and it.get("node") is not None:
                b_types = self._extract_base_types(it["node"])
                if b_types:
                    facets_dict["base_types"] = tuple(b_types)
                mods = self.dialect.extract_modifiers(it["node"])
                if mods:
                    facets_dict["modifiers"] = tuple(mods)
                if "partial" in mods:
                    facets_dict["is_partial"] = True
                field_types_map: Dict[str, str] = {}
                for c_it in it["children_items"]:
                    c_kinds = set(c_it.get("kinds") or {c_it["kind"]})
                    if (c_kinds & {"field", "property"}) and c_it.get("return_type"):
                        raw_t = re.sub(r"<[^>]+>", "", str(c_it["return_type"])).strip().rstrip("?[]")
                        if raw_t:
                            field_types_map[c_it["short_name"]] = raw_t
                if field_types_map:
                    facets_dict["field_types"] = field_types_map

            return SymbolNode(
                id=it["canonical_id"],
                name=it["short_name"],
                scope_path=tuple(it["scope_path"]),
                kinds=frozenset(it["kinds"]),
                language=self.language_name,
                span=it["span"],
                parts=it["parts"],
                facets=facets_dict,
                children=child_nodes,
                provenance=tuple(it["provenance"]),
            )

        root_nodes = tuple(_to_symbol_node(r) for r in root_items)
        return root_nodes, merged_items

    @staticmethod
    def _extract_call_arg_count(site_node: Any, target_node: Any, content_bytes: bytes) -> Optional[int]:
        """Extract call-site argument count from the argument list slice following `target_node`."""
        try:
            start_b = int(target_node.end_byte)
            end_b = int(site_node.end_byte)
            if end_b <= start_b:
                return None
            tail = content_bytes[start_b:end_b].decode("utf-8", errors="replace").strip()
            lpar = tail.find("(")
            rpar = tail.rfind(")")
            if lpar == -1 or rpar == -1 or rpar < lpar:
                return None
            inner = tail[lpar + 1 : rpar].strip()
            if not inner:
                return 0
            depth = 0
            count = 1
            in_str: Optional[str] = None
            for ch in inner:
                if in_str:
                    if ch == in_str:
                        in_str = None
                    continue
                if ch in ("'", '"'):
                    in_str = ch
                elif ch in ("(", "[", "{", "<"):
                    depth += 1
                elif ch in (")", "]", "}", ">"):
                    depth = max(0, depth - 1)
                elif ch == "," and depth == 0:
                    count += 1
            return count
        except Exception:
            return None

    def _extract_relation_edges(
        self,
        matches: List[Any],
        merged_items: List[Dict[str, Any]],
        normalized_path: str,
        content: str,
        content_bytes: bytes,
    ) -> Tuple[RelationEdge, ...]:
        """Extract `RelationEdge` instances (imports, inherits, implements, calls, references, documents) in a single pass."""
        edges: List[RelationEdge] = []
        seen_edges = set()
        file_root_id = f"{normalized_path}::<module>"
        default_prov = (ProvenanceStep(provider_id=f"ast:{self.language_name}/default.scm", action="extract", rule_or_hook="@edge"),)

        # Sort items by narrowest byte range to find the tightest enclosing symbol
        enclosing_candidates = sorted(
            merged_items,
            key=lambda x: (x["end_byte"] - x["start_byte"], x["start_byte"]),
        )

        def _find_enclosing_id(byte_offset: int) -> str:
            for cand in enclosing_candidates:
                if cand["start_byte"] <= byte_offset <= cand["end_byte"]:
                    return str(cand["canonical_id"])
            return file_root_id

        # 1. Inheritance and implementation edges from class/struct/interface items
        for item in merged_items:
            if (set(item.get("kinds") or {item["kind"]}) & {"class", "struct", "interface"}) and item.get("node") is not None:
                base_rels = self._extract_base_type_relations(item["node"])
                for bt_expr, edge_k in base_rels:
                    ekey = (item["canonical_id"], bt_expr, edge_k, item["span"].start_byte)
                    if ekey not in seen_edges:
                        seen_edges.add(ekey)
                        edges.append(
                            RelationEdge(
                                source_id=item["canonical_id"],
                                target_expr=bt_expr,
                                edge_kind=edge_k,
                                span=item["span"],
                                provenance=tuple(item["provenance"]) or default_prov,
                            )
                        )

        # 2. Import edges (dialect + query captures)
        dialect_imports = self.dialect.extract_imports(content, file_path=normalized_path)
        for alias, target_mod in dialect_imports.items():
            alias_str = str(alias).strip()
            target_str = str(target_mod or alias).strip()
            if not target_str:
                continue
            if alias_str.startswith("*:") or alias_str == "*":
                expr = f"*={target_str}"
            elif alias_str.startswith("export*:"):
                expr = f"export*={target_str}"
            elif alias_str and alias_str != target_str:
                expr = f"{alias_str}={target_str}"
            else:
                expr = target_str
            ekey = (file_root_id, expr, "imports", 0)
            if ekey not in seen_edges:
                seen_edges.add(ekey)
                edges.append(
                    RelationEdge(
                        source_id=file_root_id,
                        target_expr=expr,
                        edge_kind="imports",
                        span=Span(start_byte=0, end_byte=0, start_line=1, start_col=0, end_line=1, end_col=0),
                        provenance=default_prov,
                    )
                )

        # 3. Query-captured call / reference / edge matches
        for match_elem in matches:
            if len(match_elem) == 3:
                prov_id, _, captures = match_elem
            else:
                _, captures = match_elem
                prov_id = f"ast:{self.language_name}/default.scm"

            # Check @call.name, @reference.<kind>, @edge.<kind>
            edge_kind_matched: Optional[str] = None
            rule_tag = ""
            target_node: Optional[Any] = None
            site_node: Optional[Any] = None

            if "call.name" in captures and captures["call.name"]:
                edge_kind_matched = "calls"
                rule_tag = "@call.name"
                target_node = captures["call.name"][0]
                site_node = (captures.get("call.site") or [target_node])[0]
            else:
                for cap_k, cap_nodes in captures.items():
                    if not cap_nodes:
                        continue
                    if cap_k.startswith("reference."):
                        ref_sub = cap_k.split(".", 1)[1]
                        edge_kind_matched = "calls" if ref_sub == "call" else "references"
                        rule_tag = f"@{cap_k}"
                        site_node = cap_nodes[0]
                        name_cands = captures.get("name") or captures.get("part.name") or cap_nodes
                        target_node = name_cands[0]
                        break
                    if cap_k.startswith("edge."):
                        edge_kind_matched = cap_k.split(".", 1)[1]
                        rule_tag = f"@{cap_k}"
                        site_node = cap_nodes[0]
                        name_cands = captures.get("name") or captures.get("part.name") or cap_nodes
                        target_node = name_cands[0]
                        break

            if edge_kind_matched is None or target_node is None or site_node is None:
                continue

            raw_name = target_node.text.decode("utf-8", errors="replace").strip()
            if not raw_name:
                continue

            prefix = ""
            if edge_kind_matched == "calls" and site_node.start_byte < target_node.start_byte:
                raw_prefix = content_bytes[site_node.start_byte : target_node.start_byte].decode(
                    "utf-8", errors="replace"
                ).strip()
                prefix = self.dialect.normalize_call_receiver(raw_prefix)

            target_expr = f"{prefix}.{raw_name}" if prefix else raw_name
            arg_count_val = (
                self._extract_call_arg_count(site_node, target_node, content_bytes)
                if edge_kind_matched == "calls"
                else None
            )
            detail_val = f"arg_count={arg_count_val}" if arg_count_val is not None else None
            src_id = _find_enclosing_id(site_node.start_byte)
            edge_span = self._node_to_span(site_node)
            ekey = (src_id, target_expr, edge_kind_matched, edge_span.start_byte, edge_span.end_byte)
            if ekey not in seen_edges:
                seen_edges.add(ekey)
                edges.append(
                    RelationEdge(
                        source_id=src_id,
                        target_expr=target_expr,
                        edge_kind=edge_kind_matched,
                        span=edge_span,
                        provenance=(
                            ProvenanceStep(
                                provider_id=prov_id,
                                action="extract",
                                rule_or_hook=rule_tag,
                                detail=detail_val,
                            ),
                        ),
                    )
                )

        # 4. Markdown `documents` edges (`[Label](path#Symbol)` and `` `Class.method` ``)
        if self.language_name == "markdown" and content:
            from .base import build_line_byte_offsets, span_from_lines
            from .markdown import _FENCE_RE, _MD_BACKTICK_DOC_RE, _MD_LINK_DOC_RE

            line_offsets = build_line_byte_offsets(content_bytes)
            total_bytes = len(content_bytes)
            doc_prov = (
                ProvenanceStep(
                    provider_id=f"ast:{self.language_name}/default.scm",
                    action="extract",
                    rule_or_hook="@edge.documents",
                ),
            )
            active_fence: Optional[str] = None
            for idx_ln, line_str in enumerate(content.splitlines(), start=1):
                stripped_ln = line_str.strip()
                fm = _FENCE_RE.match(stripped_ln)
                if fm:
                    fence_marker = fm.group(1)
                    if active_fence is None:
                        active_fence = fence_marker
                    elif stripped_ln.startswith(active_fence[0] * len(active_fence)):
                        active_fence = None
                    continue
                if active_fence is not None:
                    continue

                ln_span = span_from_lines(idx_ln, idx_ln, line_offsets, total_bytes)
                src_id = _find_enclosing_id(ln_span.start_byte)
                if src_id == file_root_id and merged_items:
                    preceding_headings = [
                        it for it in merged_items
                        if str(it.get("kind", "")).startswith("doc_heading") and it["start_byte"] <= ln_span.start_byte
                    ]
                    if preceding_headings:
                        src_id = str(preceding_headings[-1]["canonical_id"])
                for m_link in _MD_LINK_DOC_RE.finditer(line_str):
                    link_label = m_link.group(1).strip().strip("`")
                    link_target = m_link.group(2).strip()
                    if link_target.startswith(("http://", "https://", "mailto:")):
                        continue
                    if "#" in link_target:
                        path_part, anchor_part = link_target.split("#", 1)
                        if re.match(r"^L?\d+(?:-\d+)?$", anchor_part) and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", link_label):
                            doc_expr = f"{path_part}#{link_label}"
                        else:
                            doc_expr = link_target
                    elif re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", link_label) and "." in link_label:
                        doc_expr = f"{link_target}#{link_label}"
                    else:
                        doc_expr = link_target
                    dkey = (src_id, doc_expr, "documents", ln_span.start_byte, ln_span.end_byte)
                    if dkey not in seen_edges:
                        seen_edges.add(dkey)
                        edges.append(
                            RelationEdge(
                                source_id=src_id,
                                target_expr=doc_expr,
                                edge_kind="documents",
                                span=ln_span,
                                provenance=doc_prov,
                            )
                        )
                for m_bt in _MD_BACKTICK_DOC_RE.finditer(line_str):
                    bt_sym = m_bt.group(1).strip()
                    dkey = (src_id, bt_sym, "documents", ln_span.start_byte, ln_span.end_byte)
                    if dkey not in seen_edges:
                        seen_edges.add(dkey)
                        edges.append(
                            RelationEdge(
                                source_id=src_id,
                                target_expr=bt_sym,
                                edge_kind="documents",
                                span=ln_span,
                                provenance=doc_prov,
                            )
                        )

        return tuple(edges)

    def extract_file_graph(
        self,
        file_path: str,
        content: str,
        *,
        space: str = "unified",
    ) -> FileSymbolGraph:
        """Extract an immutable `FileSymbolGraph` in a single CST pass with commutative `.scm` merging and `SymbolProcessor` refinement."""
        normalized_path = str(file_path).replace("\\", "/")
        content_bytes = (content or "").encode("utf-8", errors="replace")
        c_hash = compute_content_hash(content_bytes)
        if not content or not content.strip():
            return FileSymbolGraph(
                file_path=normalized_path,
                content_hash=c_hash,
                language=self.language_name,
            )

        if self._parser is None or (self._query is None and not self._queries):
            return super().extract_file_graph(file_path=normalized_path, content=content, space=space)

        parsed_res = self._get_bytes_and_matches(normalized_path, content)
        if parsed_res is None:
            return FileSymbolGraph(
                file_path=normalized_path,
                content_hash=c_hash,
                language=self.language_name,
            )
        content_bytes, matches = parsed_res
        lines = content.splitlines()
        raw_items = self._extract_raw_definition_items(matches, lines)
        merged_items = self._commutatively_merge_raw_items(raw_items)
        root_nodes, enriched_items = self._build_recursive_symbol_nodes(
            merged_items=merged_items,
            normalized_path=normalized_path,
            content_bytes=content_bytes,
        )
        edges = self._extract_relation_edges(
            matches=matches,
            merged_items=enriched_items,
            normalized_path=normalized_path,
            content=content,
            content_bytes=content_bytes,
        )
        graph = FileSymbolGraph(
            file_path=normalized_path,
            content_hash=c_hash,
            language=self.language_name,
            root_nodes=root_nodes,
            outgoing_edges=edges,
        )
        for proc in self._processors:
            try:
                graph = proc.refine_file_graph(graph, content_bytes)
            except Exception as exc:
                log_warn(
                    f"TreeSitterDriver: SymbolProcessor '{getattr(proc, 'provider_id', proc)}' failed on '{normalized_path}': {exc}",
                    stream="stderr",
                )
        return graph
