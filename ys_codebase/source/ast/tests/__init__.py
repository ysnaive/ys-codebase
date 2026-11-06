"""
Shared AST test fixtures, deterministic offline Tree-sitter fallback, and global state isolation for `module:ast`.
"""

import ast as _py_stdlib_ast
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import types
from typing import Any, Dict, List, Optional, Tuple

from dev.testing import Requirement, YSCBTestCase, require

_AST_ROOT = Path(__file__).resolve().parents[1]
if str(_AST_ROOT) not in sys.path:
    sys.path.insert(0, str(_AST_ROOT))


def load_ast_script(rel_path: str, module_name: str) -> Any:
    """Dynamically load an AST script module (such as `scripts/cli.py` or hooks) by relative path."""
    script_path = _AST_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load script spec from {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FallbackNode:
    """Lightweight deterministic AST node emulating `tree_sitter.Node` when C extensions are absent."""

    def __init__(
        self,
        node_type: str,
        text: bytes,
        start_point: Tuple[int, int],
        end_point: Tuple[int, int],
        start_byte: int,
        end_byte: int,
        children: Optional[List["_FallbackNode"]] = None,
        parent: Optional["_FallbackNode"] = None,
        prev_named_sibling: Optional["_FallbackNode"] = None,
    ) -> None:
        self.type = node_type
        self.text = text
        self.start_point = start_point
        self.end_point = end_point
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.children: List[_FallbackNode] = list(children or [])
        self.parent = parent
        self.prev_named_sibling = prev_named_sibling
        for c in self.children:
            c.parent = self


class _FallbackTree:
    def __init__(self, root_node: _FallbackNode) -> None:
        self.root_node = root_node


class _FallbackLanguage:
    def __init__(self, raw_lang: Any) -> None:
        if isinstance(raw_lang, _FallbackLanguage):
            self.lang_key = raw_lang.lang_key
        elif isinstance(raw_lang, dict) and "lang_key" in raw_lang:
            self.lang_key = str(raw_lang["lang_key"])
        elif isinstance(raw_lang, str):
            self.lang_key = raw_lang
        else:
            raise TypeError(f"Invalid language capsule: {raw_lang!r}")


class _FallbackParser:
    def __init__(self, language: Optional[_FallbackLanguage] = None) -> None:
        self.language = language

    def parse(self, content_bytes: bytes) -> _FallbackTree:
        lang_key = self.language.lang_key if self.language else "generic"
        root = _FallbackNode(
            node_type="module",
            text=content_bytes,
            start_point=(0, 0),
            end_point=(content_bytes.count(b"\n"), 0),
            start_byte=0,
            end_byte=len(content_bytes),
        )
        root._lang_key = lang_key  # type: ignore[attr-defined]
        return _FallbackTree(root)


class _FallbackQuery:
    def __init__(self, language: _FallbackLanguage, query_scm: str) -> None:
        if not isinstance(query_scm, str) or not query_scm.strip():
            raise ValueError("Empty query string")
        if query_scm.count("(") != query_scm.count(")"):
            raise ValueError("Unbalanced parentheses in S-Expression query")
        self.language = language
        self.query_scm = query_scm


def _line_byte_offsets(content_bytes: bytes) -> List[int]:
    offsets = [0]
    for idx, b in enumerate(content_bytes):
        if b == 10:
            offsets.append(idx + 1)
    return offsets


def _byte_to_point(byte_idx: int, line_offsets: List[int]) -> Tuple[int, int]:
    lo, hi = 0, len(line_offsets) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if line_offsets[mid] <= byte_idx:
            lo = mid + 1
        else:
            hi = mid - 1
    line_no = max(0, hi)
    return (line_no, max(0, byte_idx - line_offsets[line_no]))


def _find_matching_brace_end(text: str, open_pos: int) -> int:
    depth = 0
    in_str: Optional[str] = None
    idx = open_pos
    while idx < len(text):
        ch = text[idx]
        if in_str:
            if ch == "\\" and idx + 1 < len(text):
                idx += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return idx + 1
        idx += 1
    return len(text)


def _extract_preceding_comment_node(
    lines: List[str],
    line_offsets: List[int],
    content_bytes: bytes,
    start_line_0: int,
) -> Optional[_FallbackNode]:
    comment_lines: List[str] = []
    curr = start_line_0 - 1
    first_comment_line = start_line_0 - 1
    while curr >= 0:
        s = lines[curr].strip()
        if s.startswith(("//", "/*", "*", "*/", "#")) and not s.startswith("#include"):
            comment_lines.insert(0, lines[curr])
            first_comment_line = curr
            curr -= 1
        elif s.startswith("[") and s.endswith("]"):
            curr -= 1
        else:
            break
    if not comment_lines:
        return None
    sb = line_offsets[first_comment_line]
    eb = line_offsets[start_line_0] - 1 if start_line_0 < len(line_offsets) else len(content_bytes)
    raw = "\n".join(comment_lines).encode("utf-8", errors="replace")
    return _FallbackNode(
        node_type="comment",
        text=raw,
        start_point=(first_comment_line, 0),
        end_point=(start_line_0 - 1, len(lines[start_line_0 - 1])),
        start_byte=max(0, sb),
        end_byte=max(sb, eb),
    )


def _build_python_matches(content_bytes: bytes) -> List[Tuple[int, Dict[str, List[_FallbackNode]]]]:
    text = content_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()
    line_offsets = _line_byte_offsets(content_bytes)
    matches: List[Tuple[int, Dict[str, List[_FallbackNode]]]] = []
    try:
        tree = _py_stdlib_ast.parse(text)
    except Exception:
        return matches

    def _emit_field(f_ln: int, f_name: str, ret_type_name: str = "") -> None:
        f_sb = line_offsets[f_ln - 1]
        f_eb = line_offsets[f_ln] - 1 if f_ln < len(line_offsets) else len(content_bytes)
        f_node = _FallbackNode("assignment", content_bytes[f_sb:f_eb], (f_ln - 1, 0), (f_ln - 1, 0), f_sb, f_eb)
        fn_b = f_name.encode("utf-8")
        f_cap: Dict[str, List[_FallbackNode]] = {
            "definition.field": [f_node],
            "symbol.name": [_FallbackNode("identifier", fn_b, (f_ln - 1, 0), (f_ln - 1, len(fn_b)), f_sb, f_sb + len(fn_b))],
        }
        if ret_type_name:
            rt_b = ret_type_name.encode("utf-8")
            f_cap["symbol.return_type"] = [_FallbackNode("type", rt_b, (f_ln - 1, 0), (f_ln - 1, len(rt_b)), f_sb, f_sb + len(rt_b))]
        matches.append((1, f_cap))

    def _visit(nodes: List[_py_stdlib_ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, _py_stdlib_ast.ClassDef):
                s_ln = max(1, getattr(node, "lineno", 1))
                e_ln = max(s_ln, getattr(node, "end_lineno", s_ln) or s_ln)
                sb = line_offsets[s_ln - 1]
                eb = line_offsets[e_ln] - 1 if e_ln < len(line_offsets) else len(content_bytes)
                children: List[_FallbackNode] = []
                if node.bases:
                    base_names = []
                    for b in node.bases:
                        if isinstance(b, _py_stdlib_ast.Name):
                            base_names.append(b.id)
                        elif isinstance(b, _py_stdlib_ast.Attribute):
                            base_names.append(b.attr)
                    if base_names:
                        b_bytes = f"({', '.join(base_names)})".encode("utf-8")
                        children.append(_FallbackNode("argument_list", b_bytes, (s_ln - 1, 0), (s_ln - 1, len(b_bytes)), sb, sb + len(b_bytes)))
                def_node = _FallbackNode(
                    "class_definition",
                    content_bytes[sb:eb],
                    (s_ln - 1, getattr(node, "col_offset", 0)),
                    (e_ln - 1, 0),
                    sb,
                    eb,
                    children=children,
                    prev_named_sibling=_extract_preceding_comment_node(lines, line_offsets, content_bytes, s_ln - 1),
                )
                name_b = node.name.encode("utf-8")
                name_node = _FallbackNode("identifier", name_b, (s_ln - 1, 0), (s_ln - 1, len(name_b)), sb, sb + len(name_b))
                cap: Dict[str, List[_FallbackNode]] = {"definition.class": [def_node], "symbol.name": [name_node]}
                doc = _py_stdlib_ast.get_docstring(node, clean=False)
                if doc is not None:
                    doc_b = f'"""{doc}"""'.encode("utf-8")
                    cap["symbol.docstring"] = [_FallbackNode("string", doc_b, (s_ln, 0), (s_ln, len(doc_b)), sb, sb + len(doc_b))]
                matches.append((0, cap))

                for item in node.body:
                    if isinstance(item, _py_stdlib_ast.AnnAssign) and isinstance(item.target, _py_stdlib_ast.Name):
                        f_ln = getattr(item, "lineno", s_ln)
                        rt = item.annotation.id if isinstance(item.annotation, _py_stdlib_ast.Name) else ""
                        _emit_field(f_ln, item.target.id, rt)
                    elif isinstance(item, _py_stdlib_ast.Assign):
                        for tgt in item.targets:
                            if isinstance(tgt, _py_stdlib_ast.Name):
                                _emit_field(getattr(item, "lineno", s_ln), tgt.id)
                _visit(node.body)

            elif isinstance(node, (_py_stdlib_ast.FunctionDef, _py_stdlib_ast.AsyncFunctionDef)):
                s_ln = max(1, getattr(node, "lineno", 1))
                e_ln = max(s_ln, getattr(node, "end_lineno", s_ln) or s_ln)
                sb = line_offsets[s_ln - 1]
                eb = line_offsets[e_ln] - 1 if e_ln < len(line_offsets) else len(content_bytes)
                node_slice = content_bytes[sb:eb].decode("utf-8", errors="replace")
                p_start = node_slice.find("(")
                p_end = -1
                if p_start != -1:
                    depth = 0
                    for idx in range(p_start, len(node_slice)):
                        if node_slice[idx] == "(":
                            depth += 1
                        elif node_slice[idx] == ")":
                            depth -= 1
                            if depth == 0:
                                p_end = idx + 1
                                break
                sig_str = node_slice[p_start:p_end] if (p_start != -1 and p_end != -1) else "()"
                def_node = _FallbackNode(
                    "function_definition",
                    content_bytes[sb:eb],
                    (s_ln - 1, getattr(node, "col_offset", 0)),
                    (e_ln - 1, 0),
                    sb,
                    eb,
                    prev_named_sibling=_extract_preceding_comment_node(lines, line_offsets, content_bytes, s_ln - 1),
                )
                if getattr(node, "decorator_list", None):
                    dec_children: List[_FallbackNode] = []
                    for d in node.decorator_list:
                        d_name = d.id if isinstance(d, _py_stdlib_ast.Name) else (d.attr if isinstance(d, _py_stdlib_ast.Attribute) else "")
                        if d_name:
                            db = f"@{d_name}".encode("utf-8")
                            dec_children.append(_FallbackNode("decorator", db, (s_ln - 1, 0), (s_ln - 1, len(db)), sb, sb + len(db)))
                    dec_children.append(def_node)
                    _FallbackNode("decorated_definition", content_bytes[sb:eb], (s_ln - 1, 0), (e_ln - 1, 0), sb, eb, children=dec_children)

                name_b = node.name.encode("utf-8")
                sig_b = sig_str.encode("utf-8")
                cap = {
                    "definition.function": [def_node],
                    "symbol.name": [_FallbackNode("identifier", name_b, (s_ln - 1, 0), (s_ln - 1, len(name_b)), sb, sb + len(name_b))],
                    "symbol.signature": [_FallbackNode("parameters", sig_b, (s_ln - 1, 0), (s_ln - 1, len(sig_b)), sb, sb + len(sig_b))],
                }
                doc = _py_stdlib_ast.get_docstring(node, clean=False)
                if doc is not None:
                    doc_b = f'"""{doc}"""'.encode("utf-8")
                    cap["symbol.docstring"] = [_FallbackNode("string", doc_b, (s_ln, 0), (s_ln, len(doc_b)), sb, sb + len(doc_b))]
                matches.append((2, cap))

                # Extract self.<field> assignments inside methods
                for sub in _py_stdlib_ast.walk(node):
                    if isinstance(sub, _py_stdlib_ast.AnnAssign) and isinstance(sub.target, _py_stdlib_ast.Attribute):
                        if isinstance(sub.target.value, _py_stdlib_ast.Name) and sub.target.value.id == "self":
                            rt = sub.annotation.id if isinstance(sub.annotation, _py_stdlib_ast.Name) else ""
                            _emit_field(getattr(sub, "lineno", s_ln), sub.target.attr, rt)
                    elif isinstance(sub, _py_stdlib_ast.Assign):
                        for tgt in sub.targets:
                            if isinstance(tgt, _py_stdlib_ast.Attribute) and isinstance(tgt.value, _py_stdlib_ast.Name) and tgt.value.id == "self":
                                _emit_field(getattr(sub, "lineno", s_ln), tgt.attr)

                _visit(node.body)

    _visit(tree.body)

    for node in _py_stdlib_ast.walk(tree):
        if isinstance(node, _py_stdlib_ast.Call):
            ln = max(1, getattr(node, "lineno", 1))
            col = getattr(node, "col_offset", 0)
            sb = line_offsets[ln - 1] + col
            callee = ""
            prefix = ""
            if isinstance(node.func, _py_stdlib_ast.Name):
                callee = node.func.id
            elif isinstance(node.func, _py_stdlib_ast.Attribute):
                callee = node.func.attr
                if isinstance(node.func.value, _py_stdlib_ast.Name):
                    prefix = node.func.value.id + "."
                elif (
                    isinstance(node.func.value, _py_stdlib_ast.Call)
                    and isinstance(node.func.value.func, _py_stdlib_ast.Name)
                ):
                    prefix = f"{node.func.value.func.id}()."
                elif isinstance(node.func.value, _py_stdlib_ast.Attribute) and isinstance(node.func.value.value, _py_stdlib_ast.Name):
                    prefix = f"{node.func.value.value.id}.{node.func.value.attr}."
            if callee:
                p_bytes = prefix.encode("utf-8")
                c_bytes = callee.encode("utf-8")
                site_b = p_bytes + c_bytes + b"()"
                call_node = _FallbackNode("call", site_b, (ln - 1, col), (ln - 1, col + len(site_b)), sb, sb + len(site_b))
                name_node = _FallbackNode(
                    "identifier",
                    c_bytes,
                    (ln - 1, col + len(p_bytes)),
                    (ln - 1, col + len(p_bytes) + len(c_bytes)),
                    sb + len(p_bytes),
                    sb + len(p_bytes) + len(c_bytes),
                )
                matches.append((3, {"call.site": [call_node], "call.name": [name_node]}))
    return matches


def _build_brace_language_matches(
    lang_key: str,
    content_bytes: bytes,
) -> List[Tuple[int, Dict[str, List[_FallbackNode]]]]:
    text = content_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()
    line_offsets = _line_byte_offsets(content_bytes)
    matches: List[Tuple[int, Dict[str, List[_FallbackNode]]]] = []

    if lang_key == "markdown":
        fence_re = re.compile(r"^(`{3,}|~{3,})")
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        in_fence = False
        fence_char = ""
        for idx, line in enumerate(lines):
            s = line.strip()
            fm = fence_re.match(s)
            if fm:
                if not in_fence:
                    in_fence = True
                    fence_char = fm.group(1)[0]
                elif s.startswith(fence_char * 3):
                    in_fence = False
                    fence_char = ""
                continue
            if in_fence:
                continue
            hm = heading_re.match(s)
            if hm:
                sb = line_offsets[idx]
                eb = sb + len(line.encode("utf-8"))
                h_b = line.encode("utf-8")
                t_b = hm.group(2).strip().encode("utf-8")
                matches.append((
                    0,
                    {
                        "definition.heading": [_FallbackNode("atx_heading", h_b, (idx, 0), (idx, len(line)), sb, eb)],
                        "symbol.name": [_FallbackNode("inline", t_b, (idx, 0), (idx, len(t_b)), sb, eb)],
                    },
                ))
        return matches

    def _make_mod_children(mod_str: str, pt: Tuple[int, int], sb: int) -> List[_FallbackNode]:
        out: List[_FallbackNode] = []
        for tok in (mod_str or "").split():
            tl = tok.strip().lower()
            if tl in ("public", "private", "protected", "internal", "partial", "static", "abstract", "virtual", "override", "async", "readonly", "export"):
                tb = tl.encode("utf-8")
                out.append(_FallbackNode("modifier", tb, pt, pt, sb, sb + len(tb)))
        return out

    # 1. File-scoped and block namespaces
    for m in re.finditer(r"(?m)^[ \t]*namespace[ \t]+([A-Za-z_][A-Za-z0-9_.:]*)[ \t]*(;|{)", text):
        ns_name = m.group(1).strip()
        delim = m.group(2)
        sb_char = m.start()
        eb_char = len(text) if delim == ";" else _find_matching_brace_end(text, m.end() - 1)
        sb = len(text[:sb_char].encode("utf-8"))
        eb = len(text[:eb_char].encode("utf-8"))
        sp = _byte_to_point(sb, line_offsets)
        ep = _byte_to_point(eb, line_offsets)
        ntype = "file_scoped_namespace_declaration" if delim == ";" else "namespace_declaration"
        def_node = _FallbackNode(ntype, content_bytes[sb:eb], sp, ep, sb, eb)
        nb = ns_name.encode("utf-8")
        matches.append((0, {"definition.namespace": [def_node], "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))]}))

    # 2. Type definitions (class / struct / interface / enum / record)
    type_ranges: List[Tuple[int, int]] = []
    type_rx = re.compile(
        r"(?m)^([ \t]*(?:(?:export|public|private|protected|internal|static|abstract|sealed|partial)[ \t]+)*)"
        r"(class|struct|interface|enum|record)[ \t]+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>{\n]*>)?"
        r"([ \t]*(?::|extends|implements)[ \t]*[^{;\n]+)?[ \t]*\{"
    )
    for m in type_rx.finditer(text):
        mods_str = m.group(1) or ""
        kind_raw = m.group(2)
        kind = "struct" if kind_raw == "record" else kind_raw
        t_name = m.group(3).strip()
        bases_raw = (m.group(4) or "").strip()
        sb_char = m.start()
        brace_pos = m.end() - 1
        eb_char = _find_matching_brace_end(text, brace_pos)
        sb = len(text[:sb_char].encode("utf-8"))
        eb = len(text[:eb_char].encode("utf-8"))
        type_ranges.append((sb, eb))
        sp = _byte_to_point(sb, line_offsets)
        ep = _byte_to_point(eb, line_offsets)
        children = _make_mod_children(mods_str, sp, sb)
        if bases_raw:
            bb = bases_raw.encode("utf-8")
            children.append(_FallbackNode("base_list", bb, sp, sp, sb, sb + len(bb)))
        def_node = _FallbackNode(
            f"{kind}_declaration",
            content_bytes[sb:eb],
            sp,
            ep,
            sb,
            eb,
            children=children,
            prev_named_sibling=_extract_preceding_comment_node(lines, line_offsets, content_bytes, sp[0]),
        )
        nb = t_name.encode("utf-8")
        matches.append((1, {f"definition.{kind}": [def_node], "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))]}))

    # 3. TypeScript type alias
    if lang_key in ("typescript", "javascript"):
        for m in re.finditer(r"(?m)^[ \t]*(?:export[ \t]+)?type[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*=", text):
            t_name = m.group(1)
            sb = len(text[:m.start()].encode("utf-8"))
            line_end = text.find("\n", m.end())
            eb = len(text[: (line_end if line_end != -1 else len(text))].encode("utf-8"))
            sp = _byte_to_point(sb, line_offsets)
            ep = _byte_to_point(eb, line_offsets)
            nb = t_name.encode("utf-8")
            matches.append((
                2,
                {
                    "definition.type": [_FallbackNode("type_alias_declaration", content_bytes[sb:eb], sp, ep, sb, eb)],
                    "symbol.name": [_FallbackNode("type_identifier", nb, sp, sp, sb, sb + len(nb))],
                },
            ))

    # Track C++ access specifiers by line
    cpp_access_by_line: List[Tuple[int, str]] = []
    if lang_key in ("cpp", "c"):
        for idx, ln_str in enumerate(lines):
            am = re.match(r"^[ \t]*(public|protected|private)[ \t]*:[ \t]*$", ln_str)
            if am:
                cpp_access_by_line.append((idx, am.group(1)))

    # 4. Functions, methods, constructors, arrow functions
    method_body_ranges: List[Tuple[int, int]] = []
    if lang_key in ("javascript", "typescript"):
        fn_rx = re.compile(
            r"(?m)^([ \t]*(?:(?:export|public|private|protected|static|async)[ \t]+)*)"
            r"(?:function[ \t]+)?(#?[A-Za-z_$][A-Za-z0-9_$]*)[ \t]*\(([^)\n]*)\)"
            r"(?:[ \t]*:[ \t]*([^{;\n=]+))?[ \t]*(?:\{|=>)"
        )
        arrow_rx = re.compile(
            r"(?m)^([ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+)([A-Za-z_$][A-Za-z0-9_$]*)[ \t]*=[ \t]*(?:async[ \t]*)?\(([^)\n]*)\)[ \t]*(?::[ \t]*([^=\n]+))?[ \t]*=>"
        )
        for rx in (fn_rx, arrow_rx):
            for m in rx.finditer(text):
                mods_str = m.group(1) or ""
                fname = m.group(2).strip()
                if fname in ("if", "for", "while", "switch", "catch", "return", "class", "interface"):
                    continue
                params_str = f"({m.group(3).strip()})"
                ret_str = (m.group(4) or "").strip()
                sb_char = m.start()
                if m.group(0).endswith("{"):
                    eb_char = _find_matching_brace_end(text, m.end() - 1)
                else:
                    nl_pos = text.find("\n", m.end())
                    eb_char = nl_pos if nl_pos != -1 else len(text)
                sb = len(text[:sb_char].encode("utf-8"))
                eb = len(text[:eb_char].encode("utf-8"))
                method_body_ranges.append((sb, eb))
                sp = _byte_to_point(sb, line_offsets)
                ep = _byte_to_point(eb, line_offsets)
                def_node = _FallbackNode(
                    "function_declaration",
                    content_bytes[sb:eb],
                    sp,
                    ep,
                    sb,
                    eb,
                    children=_make_mod_children(mods_str, sp, sb),
                    prev_named_sibling=_extract_preceding_comment_node(lines, line_offsets, content_bytes, sp[0]),
                )
                nb = fname.encode("utf-8")
                pb = params_str.encode("utf-8")
                cap: Dict[str, List[_FallbackNode]] = {
                    "definition.function": [def_node],
                    "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))],
                    "symbol.signature": [_FallbackNode("formal_parameters", pb, sp, sp, sb, sb + len(pb))],
                }
                if ret_str:
                    rb = ret_str.encode("utf-8")
                    cap["symbol.return_type"] = [_FallbackNode("type_annotation", rb, sp, sp, sb, sb + len(rb))]
                matches.append((3, cap))
    else:
        c_fn_rx = re.compile(
            r"(?m)^([ \t]*(?:(?:public|private|protected|internal|static|virtual|override|abstract|async|inline|explicit|constexpr)[ \t]+)*)"
            r"(?:([A-Za-z_][A-Za-z0-9_<>,:.*& \t]*?)[ \t]+)?"
            r"([A-Za-z_~][A-Za-z0-9_<>:]*)[ \t]*\(([^)\n]*)\)[ \t]*(?:const[ \t]*)?(?:\{|;|=>[^;\n]*;)"
        )
        for m in c_fn_rx.finditer(text):
            mods_str = (m.group(1) or "").strip()
            ret_str = (m.group(2) or "").strip()
            fname = m.group(3).strip()
            matched_txt = m.group(0)
            if fname in ("if", "for", "while", "switch", "catch", "return", "sizeof", "new", "delete") or ret_str in ("return", "new", "else"):
                continue
            # A bare `Foo(args);` with no return type and no modifier is a function call statement, not a declaration
            if not ret_str and not mods_str and not fname.startswith("~") and not matched_txt.rstrip().endswith("{"):
                continue
            params_str = f"({m.group(4).strip()})"
            sb_char = m.start()
            if matched_txt.endswith("{"):
                eb_char = _find_matching_brace_end(text, m.end() - 1)
                method_body_ranges.append((len(text[: m.end() - 1].encode("utf-8")), len(text[:eb_char].encode("utf-8"))))
            else:
                eb_char = m.end()
            sb = len(text[:sb_char].encode("utf-8"))
            eb = len(text[:eb_char].encode("utf-8"))
            sp = _byte_to_point(sb, line_offsets)
            ep = _byte_to_point(eb, line_offsets)
            prev_sib = _extract_preceding_comment_node(lines, line_offsets, content_bytes, sp[0])
            if prev_sib is None and cpp_access_by_line:
                acc = [v for ln_i, v in cpp_access_by_line if ln_i < sp[0]]
                if acc:
                    ab = f"{acc[-1]}:".encode("utf-8")
                    prev_sib = _FallbackNode("access_specifier", ab, sp, sp, sb, sb + len(ab))
            is_ctor = not ret_str
            def_key = "definition.constructor" if (is_ctor and lang_key == "c_sharp") else ("definition.method" if lang_key == "c_sharp" else "definition.function")
            def_node = _FallbackNode(
                "method_declaration" if lang_key == "c_sharp" else "function_definition",
                content_bytes[sb:eb],
                sp,
                ep,
                sb,
                eb,
                children=_make_mod_children(mods_str, sp, sb),
                prev_named_sibling=prev_sib,
            )
            nb = fname.encode("utf-8")
            pb = params_str.encode("utf-8")
            cap = {
                def_key: [def_node],
                "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))],
                "symbol.signature": [_FallbackNode("parameter_list", pb, sp, sp, sb, sb + len(pb))],
            }
            if ret_str:
                rb = ret_str.encode("utf-8")
                cap["symbol.return_type"] = [_FallbackNode("type", rb, sp, sp, sb, sb + len(rb))]
            matches.append((3, cap))

        if lang_key == "c_sharp":
            prop_rx = re.compile(
                r"(?m)^([ \t]*(?:(?:public|private|protected|internal|static|virtual|override|abstract)[ \t]+)*)"
                r"([A-Za-z_][A-Za-z0-9_<>,?.\[\]]*)[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*\{[ \t]*(?:get|set)\b[^}\n]*\}"
            )
            for m in prop_rx.finditer(text):
                mods_str, rtype, pname = m.group(1) or "", m.group(2).strip(), m.group(3).strip()
                sb = len(text[:m.start()].encode("utf-8"))
                eb = len(text[:m.end()].encode("utf-8"))
                sp = _byte_to_point(sb, line_offsets)
                ep = _byte_to_point(eb, line_offsets)
                def_node = _FallbackNode("property_declaration", content_bytes[sb:eb], sp, ep, sb, eb, children=_make_mod_children(mods_str, sp, sb))
                nb, rb = pname.encode("utf-8"), rtype.encode("utf-8")
                matches.append((
                    4,
                    {
                        "definition.property": [def_node],
                        "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))],
                        "symbol.return_type": [_FallbackNode("type", rb, sp, sp, sb, sb + len(rb))],
                    },
                ))

        if lang_key in ("c_sharp", "cpp", "c"):
            field_rx = re.compile(
                r"(?m)^([ \t]*(?:(?:public|private|protected|internal|static|readonly|const|mutable)[ \t]+)*)"
                r"([A-Za-z_][A-Za-z0-9_<>,?.\[\]*&]*)[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*(?:=[ \t]*[^;\n]+)?;"
            )
            for m in field_rx.finditer(text):
                mods_str, rtype, fname = m.group(1) or "", m.group(2).strip(), m.group(3).strip()
                if rtype in ("using", "namespace", "return", "class", "struct", "interface", "enum", "delete", "typedef", "typename"):
                    continue
                sb = len(text[:m.start()].encode("utf-8"))
                eb = len(text[:m.end()].encode("utf-8"))
                if not any(tsb < sb and eb <= teb for tsb, teb in type_ranges):
                    continue
                if any(msb <= sb and eb <= meb for msb, meb in method_body_ranges):
                    continue
                sp = _byte_to_point(sb, line_offsets)
                ep = _byte_to_point(eb, line_offsets)
                prev_sib = None
                if cpp_access_by_line:
                    acc = [v for ln_i, v in cpp_access_by_line if ln_i < sp[0]]
                    if acc:
                        ab = f"{acc[-1]}:".encode("utf-8")
                        prev_sib = _FallbackNode("access_specifier", ab, sp, sp, sb, sb + len(ab))
                def_node = _FallbackNode(
                    "field_declaration",
                    content_bytes[sb:eb],
                    sp,
                    ep,
                    sb,
                    eb,
                    children=_make_mod_children(mods_str, sp, sb),
                    prev_named_sibling=prev_sib,
                )
                nb, rb = fname.encode("utf-8"), rtype.encode("utf-8")
                matches.append((
                    5,
                    {
                        "definition.field": [def_node],
                        "symbol.name": [_FallbackNode("identifier", nb, sp, sp, sb, sb + len(nb))],
                        "symbol.return_type": [_FallbackNode("type", rb, sp, sp, sb, sb + len(rb))],
                    },
                ))

    # 5. Call sites outside declaration headers
    call_rx = re.compile(
        r"(?<![A-Za-z0-9_])((?:(?:this|base|super|[A-Za-z_][A-Za-z0-9_]*)(?:<[^>\n]+>)?(?:\([^)\n]*\))?(?:\?\.|->|::|\.))*)([A-Za-z_][A-Za-z0-9_]*)(?:<[^>\n]+>)?\s*\("
    )
    for line_idx, line_str in enumerate(lines):
        s_line = line_str.strip()
        if not s_line or s_line.startswith(("//", "/*", "*", "#", "using ", "import ", "namespace ")):
            continue
        if re.match(r"^(?:public|private|protected|internal|static|virtual|override|abstract|async|function|def|class|struct|interface)\b", s_line) and "=" not in s_line and "=>" not in s_line:
            continue
        line_sb = line_offsets[line_idx]
        for cm in call_rx.finditer(line_str):
            raw_prefix = cm.group(1) or ""
            callee = cm.group(2)
            if callee in ("if", "for", "while", "switch", "catch", "return", "sizeof", "typeof", "nameof", "new"):
                continue
            prefix_b = raw_prefix.encode("utf-8")
            callee_b = callee.encode("utf-8")
            c_sb = line_sb + len(line_str[:cm.start()].encode("utf-8"))
            n_sb = c_sb + len(prefix_b)
            n_eb = n_sb + len(callee_b)
            c_eb = len(line_str[:cm.end()].encode("utf-8")) + line_sb
            sp = (line_idx, cm.start())
            call_node = _FallbackNode("call_expression", content_bytes[c_sb:c_eb], sp, sp, c_sb, c_eb)
            name_node = _FallbackNode("identifier", callee_b, sp, sp, n_sb, n_eb)
            matches.append((6, {"call.site": [call_node], "call.name": [name_node]}))

    return matches


class _FallbackQueryCursor:
    def __init__(self, query: _FallbackQuery) -> None:
        self.query = query

    def matches(self, root_node: _FallbackNode) -> List[Tuple[int, Dict[str, List[_FallbackNode]]]]:
        lang_key = getattr(root_node, "_lang_key", None) or self.query.language.lang_key
        if lang_key == "python":
            return _build_python_matches(root_node.text)
        return _build_brace_language_matches(lang_key, root_node.text)


def _install_offline_treesitter_fallback_if_needed() -> None:
    """
    Install deterministic pure-Python `tree_sitter` and `tree_sitter_*` shims ONLY when
    the C-extension packages are absent from the runtime environment.
    """
    try:
        import tree_sitter as _real_ts  # noqa: F401
        import tree_sitter_c_sharp as _real_cs  # noqa: F401
        return
    except ImportError:
        pass

    ts_mod = types.ModuleType("tree_sitter")
    ts_mod.Language = _FallbackLanguage  # type: ignore[attr-defined]
    ts_mod.Parser = _FallbackParser  # type: ignore[attr-defined]
    ts_mod.Query = _FallbackQuery  # type: ignore[attr-defined]
    ts_mod.QueryCursor = _FallbackQueryCursor  # type: ignore[attr-defined]
    sys.modules["tree_sitter"] = ts_mod

    grammar_defs = {
        "tree_sitter_python": ("language", "python"),
        "tree_sitter_c_sharp": ("language", "c_sharp"),
        "tree_sitter_cpp": ("language", "cpp"),
        "tree_sitter_c": ("language", "c"),
        "tree_sitter_javascript": ("language", "javascript"),
        "tree_sitter_typescript": ("language_typescript", "typescript"),
        "tree_sitter_markdown": ("language", "markdown"),
    }
    for mod_name, (fn_name, lang_key) in grammar_defs.items():
        if mod_name not in sys.modules:
            g_mod = types.ModuleType(mod_name)
            setattr(g_mod, fn_name, lambda lk=lang_key: {"lang_key": lk})
            if fn_name != "language":
                setattr(g_mod, "language", lambda lk=lang_key: {"lang_key": lk})
            sys.modules[mod_name] = g_mod

    for target_mod_name in ("ast_engine.provisioner", "ast_engine.parsers.treesitter"):
        loaded = sys.modules.get(target_mod_name)
        if loaded is not None:
            setattr(loaded, "tree_sitter", ts_mod)

    try:
        from core.pip_manager import PipManager
        from dev.testing.sandbox import SandboxProvisioner

        manifest_path = _AST_ROOT / "manifest.json"
        if manifest_path.is_file():
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            specs = PipManager.parse_pip_dependencies(m_data.get("pip_dependencies"))
            SandboxProvisioner._ADAPTED_SPECS.update(specs)
    except Exception:
        pass


_install_offline_treesitter_fallback_if_needed()


class ASTTestCase(YSCBTestCase):
    """
    Base test fixture for `module:ast`.
    Enforces strict reset and restoration of all 7 AST global/class-level states across every test method.
    """

    def setUp(self) -> None:
        super().setUp()
        _install_offline_treesitter_fallback_if_needed()
        from ast_engine import bundler
        from ast_engine.dialects import _DIALECT_INSTANCES
        from ast_engine.engine import reset_default_engine
        from ast_engine.linker import _LAST_LINKER_CACHE
        from ast_engine.provisioner import GrammarProvisioner

        self._saved_auto_install = GrammarProvisioner.auto_install_enabled
        self._saved_dialects = dict(_DIALECT_INSTANCES)
        self._saved_linker_cache = dict(_LAST_LINKER_CACHE)
        self._saved_worker_registry = bundler._worker_registry
        self._saved_sys_modules_keys = set(sys.modules.keys())

        from ast_engine.dialects import (
            CDialect,
            CppDialect,
            CSharpDialect,
            JavaScriptDialect,
            MarkdownDialect,
            PythonDialect,
            TypeScriptDialect,
        )

        reset_default_engine()
        GrammarProvisioner.reset_cache()
        GrammarProvisioner.auto_install_enabled = False
        _DIALECT_INSTANCES.clear()
        _DIALECT_INSTANCES.update(
            {
                "python": PythonDialect(),
                "c_sharp": CSharpDialect(),
                "csharp": CSharpDialect(),
                "cpp": CppDialect(),
                "c": CDialect(),
                "javascript": JavaScriptDialect(),
                "typescript": TypeScriptDialect(),
                "markdown": MarkdownDialect(),
            }
        )
        _LAST_LINKER_CACHE.update(
            {
                "symbols_map_id": None,
                "symbols_count": 0,
                "symbols_fingerprint": 0,
                "class_bases": None,
                "base_derived": None,
                "methods_by_class_and_short": None,
            }
        )
        bundler._worker_registry = None

    def tearDown(self) -> None:
        from ast_engine import bundler
        from ast_engine.dialects import _DIALECT_INSTANCES
        from ast_engine.engine import reset_default_engine
        from ast_engine.linker import _LAST_LINKER_CACHE
        from ast_engine.provisioner import GrammarProvisioner

        reset_default_engine()
        GrammarProvisioner.reset_cache()
        GrammarProvisioner.auto_install_enabled = getattr(self, "_saved_auto_install", False)
        _DIALECT_INSTANCES.clear()
        if hasattr(self, "_saved_dialects"):
            _DIALECT_INSTANCES.update(self._saved_dialects)
        if hasattr(self, "_saved_linker_cache"):
            _LAST_LINKER_CACHE.clear()
            _LAST_LINKER_CACHE.update(self._saved_linker_cache)
        bundler._worker_registry = getattr(self, "_saved_worker_registry", None)

        saved_keys = getattr(self, "_saved_sys_modules_keys", None)
        if saved_keys is not None:
            for k in list(sys.modules.keys()):
                if k not in saved_keys or k.startswith("_yscb_custom_parser_"):
                    sys.modules.pop(k, None)

        super().tearDown()


__all__ = [
    "ASTTestCase",
    "Requirement",
    "YSCBTestCase",
    "_AST_ROOT",
    "load_ast_script",
    "require",
]
