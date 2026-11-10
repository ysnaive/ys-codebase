"""
Presentation & Formatting Hub for `module:ast` (`ast_engine/formatter.py`).
Renders:
- Single-file physical vs. cross-file merged AST `outline` (`[Partial Siblings]` indicators).
- Upstream `callers`, downstream `callees`, and N-hop `impact` analysis (with Overload Group & Ambiguity cards).
- `TerminalStyler` for ANSI coloring and clickable `file://` URI formatting.
"""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.context import get_env, get_virtual_cwd
from .schema import OutlineResult


class TerminalStyler:
    """ANSI terminal color styler with TTY detection and `NO_COLOR` gate."""

    def __init__(self, stream: Any = None):
        if stream is None:
            stream = sys.stdout
        self.stream = stream
        is_atty = getattr(stream, "isatty", lambda: False)()
        no_color = bool(get_env("NO_COLOR", ""))
        self.enabled = is_atty and not no_color

    def path(self, text: str) -> str:
        return f"\033[94m{text}\033[0m" if self.enabled else text

    def symbol(self, text: str) -> str:
        return f"\033[92m{text}\033[0m" if self.enabled else text

    def kind(self, text: str) -> str:
        return f"\033[93m{text}\033[0m" if self.enabled else text

    def line(self, text: str) -> str:
        return f"\033[96m{text}\033[0m" if self.enabled else text

    def warn(self, text: str) -> str:
        return f"\033[1;93m{text}\033[0m" if self.enabled else text

    def err(self, text: str) -> str:
        return f"\033[1;91m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.enabled else text


def format_json(data: Any, indent: Optional[int] = 2) -> str:
    """Serialize payload to JSON string."""
    if indent is None:
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(data, indent=indent, ensure_ascii=False)


class ASTResultFormatter:
    """
    Formatter for `module:ast` CLI and programmatic outputs (`outline`, `callers`, `callees`, `impact`, `status`).
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        styler: Optional[TerminalStyler] = None,
        file_uri: bool = False,
    ):
        self.workspace_root = workspace_root
        self.styler = styler or TerminalStyler()
        self.file_uri = bool(file_uri)

    def get_workspace_root(self) -> Path:
        if self.workspace_root:
            return self.workspace_root
        try:
            from core import uri

            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                return Path(p_res).resolve()
        except Exception:
            pass
        return Path(get_virtual_cwd()).resolve()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        raw = str(file_path).replace("\\", "/")
        if "://" in raw:
            scheme, rest = raw.split("://", 1)
            if scheme.lower() == "file":
                raw = rest[1:] if (len(rest) >= 3 and rest[0] == "/" and rest[2] == ":") else rest
            else:
                raw = rest.lstrip("/")
        p = Path(raw)
        ws = self.get_workspace_root()
        try:
            if p.is_absolute():
                real_p = Path(os.path.realpath(str(p)))
                real_ws = Path(os.path.realpath(str(ws)))
                try:
                    rel = real_p.relative_to(real_ws)
                    return str(rel).replace("\\", "/")
                except ValueError:
                    norm_p = Path(os.path.normcase(str(real_p)))
                    norm_ws = Path(os.path.normcase(str(real_ws)))
                    norm_rel = norm_p.relative_to(norm_ws)
                    if not norm_rel.parts:
                        return "."
                    preserved = real_p.parts[len(real_ws.parts) :]
                    if preserved:
                        return "/".join(preserved).replace("\\", "/")
                    return str(norm_rel).replace("\\", "/")
        except Exception:
            pass
        return raw

    def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str:
        raw = str(file_path).replace("\\", "/")
        if "://" in raw:
            scheme, rest = raw.split("://", 1)
            if scheme.lower() == "file":
                raw = rest[1:] if (len(rest) >= 3 and rest[0] == "/" and rest[2] == ":") else rest
            else:
                raw = rest.lstrip("/")
        p = Path(raw)
        if not p.is_absolute():
            resolved = None
            try:
                from core import uri

                resolved = uri.resolve(f"project://{raw}", interactive=False)
            except Exception:
                pass
            if resolved and not str(resolved).startswith("!undefined"):
                p = Path(str(resolved)).resolve()
            else:
                ws = self.get_workspace_root()
                p = (ws / p).resolve()
        else:
            p = p.resolve()

        posix_path = p.as_posix()
        if not posix_path.startswith("/"):
            posix_path = "/" + posix_path
        uri_str = f"file://{posix_path}"
        if line is not None:
            uri_str += f"#L{line}"
        return uri_str

    def format_file_link(
        self,
        file_path: Union[str, Path],
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        use_basename: bool = True,
        file_uri: Optional[bool] = None,
    ) -> str:
        use_uri = self.file_uri if file_uri is None else bool(file_uri)
        if not use_uri:
            base_label = self.normalize_workspace_path(file_path)
            if line is not None:
                if end_line is not None and end_line > line:
                    return f"{base_label}:L{line}-{end_line}"
                return f"{base_label}:L{line}"
            return base_label

        base_label = Path(str(file_path)).name if use_basename else self.normalize_workspace_path(file_path)
        if line is not None:
            if end_line is not None and end_line > line:
                label = f"{base_label}:L{line}-{end_line}"
            else:
                label = f"{base_label}:L{line}"
        else:
            label = base_label
        uri_str = self.to_file_uri(file_path, line=line)
        return f"[{label}]({uri_str})"

    def format_outline_output(
        self,
        result: Union[OutlineResult, Dict[str, Any]],
        as_json: bool = False,
        detail: bool = False,
        file_uri: Optional[bool] = None,
    ) -> str:
        data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if as_json:
            if detail:
                return format_json(data, indent=2)

            def _compact_outline_node(node: Dict[str, Any]) -> Dict[str, Any]:
                out_n: Dict[str, Any] = {
                    "name": node.get("name", ""),
                    "kind": node.get("kind", "symbol"),
                    "line_number": node.get("line_number", 1),
                    "end_line": node.get("end_line", node.get("line_number", 1)),
                    "signature": node.get("signature", ""),
                    "visibility": node.get("visibility", "public"),
                }
                if node.get("fqn") and node.get("fqn") != node.get("name"):
                    out_n["fqn"] = node["fqn"]
                if node.get("is_partial"):
                    out_n["is_partial"] = True
                if node.get("is_static"):
                    out_n["is_static"] = True
                raw_children = node.get("members") or node.get("children") or []
                if raw_children:
                    out_n["members"] = [
                        _compact_outline_node(c.to_dict() if hasattr(c, "to_dict") else dict(c))
                        for c in raw_children
                    ]
                return out_n

            compact_payload: Dict[str, Any] = {
                "file_path": data.get("file_path", ""),
                "language": data.get("language", "unknown"),
                "merged": bool(data.get("merged", False)),
                "symbols": [
                    _compact_outline_node(s.to_dict() if hasattr(s, "to_dict") else dict(s))
                    for s in (data.get("symbols") or [])
                ],
            }
            if data.get("partial_siblings"):
                compact_payload["partial_siblings"] = data["partial_siblings"]
            if data.get("filters"):
                compact_payload["filters"] = data["filters"]
            if data.get("warnings"):
                compact_payload["warnings"] = data["warnings"]
            if data.get("error"):
                compact_payload["error"] = data["error"]
            return format_json(compact_payload, indent=None)

        file_path = data.get("file_path", "")
        lang = data.get("language", "unknown")
        merged = bool(data.get("merged", False))
        filters = data.get("filters") or {}
        mode_tag = "merged cross-file partial view" if merged else "single-file physical view"
        if filters and isinstance(filters, dict):
            f_parts = [f"{k}={v}" for k, v in filters.items() if v]
            if f_parts:
                mode_tag = f"{mode_tag}, filters: {', '.join(f_parts)}"
        file_link = self.format_file_link(file_path, use_basename=False, file_uri=file_uri)

        lines: List[str] = [
            f"[ast] 檔案大綱 (Outline): {self.styler.path(file_link)} ({lang}, {mode_tag}):",
            "-" * 85,
        ]

        if data.get("error"):
            lines.append(f"  {self.styler.err(str(data['error']))}")

        symbols = data.get("symbols") or []
        partial_siblings_map: Dict[str, List[Dict[str, Any]]] = data.get("partial_siblings") or {}

        if not symbols:
            lines.append("  (未解析出任何結構化 AST 符號)")
        else:
            self._render_outline_nodes(symbols, partial_siblings_map, lines, indent=0)

        # Recursively collect all rendered `is_partial` FQNs/names so nested partial nodes are not duplicated at bottom
        rendered_fqns: Set[str] = set()

        def _collect_rendered_partial_fqns(node_list: List[Any]) -> None:
            for item in node_list:
                d = item.to_dict() if hasattr(item, "to_dict") else (item if isinstance(item, dict) else {})
                if d.get("is_partial"):
                    if d.get("fqn"):
                        rendered_fqns.add(str(d["fqn"]))
                    if d.get("name"):
                        rendered_fqns.add(str(d["name"]))
                children = d.get("members") or d.get("children") or []
                if children:
                    _collect_rendered_partial_fqns(children)

        _collect_rendered_partial_fqns(symbols)
        unrendered_siblings = {
            k: v for k, v in partial_siblings_map.items() if k not in rendered_fqns and v
        }
        if unrendered_siblings:
            lines.append("")
            lines.append("  [Partial Siblings]:")
            for fqn, sib_list in unrendered_siblings.items():
                for sib in sib_list:
                    s_fp = sib.get("file_path", "")
                    s_l1 = sib.get("line_number", 1)
                    s_l2 = sib.get("end_line", s_l1)
                    m_cnt = sib.get("member_count", 0)
                    lines.append(f"    ~ {fqn} -> {s_fp}:L{s_l1}-L{s_l2} ({m_cnt} member(s))")

        return "\n".join(lines)

    def _render_outline_nodes(
        self,
        nodes: List[Dict[str, Any]],
        partial_siblings_map: Dict[str, List[Dict[str, Any]]],
        lines: List[str],
        indent: int = 0,
    ) -> None:
        prefix = "  " * (indent + 1)
        for idx, node in enumerate(nodes):
            if hasattr(node, "to_dict"):
                node = node.to_dict()
            kind = str(node.get("kind", "symbol"))
            name = str(node.get("name", ""))
            fqn = str(node.get("fqn") or name)
            sig = str(node.get("signature") or name)
            vis = str(node.get("visibility") or "public")
            l1 = int(node.get("line_number", 1))
            l2 = int(node.get("end_line", l1))
            is_partial = bool(node.get("is_partial", False))
            is_static = bool(node.get("is_static", False))

            is_last = idx == len(nodes) - 1
            branch = "└──" if is_last else "├──"
            partial_badge = " [partial]" if is_partial else ""
            static_badge = " [static]" if is_static else ""
            line_tag = f"L{l1}-L{l2}" if l2 > l1 else f"L{l1}"

            lines.append(
                f"{prefix}{branch} [{vis}]{static_badge} {self.styler.kind(kind.upper())}: "
                f"{self.styler.symbol(name)} ({self.styler.line(line_tag)}){partial_badge} :: {sig}"
            )

            children = node.get("members") or node.get("children") or []
            if children:
                self._render_outline_nodes(children, partial_siblings_map, lines, indent=indent + 1)

            # Render `[Partial Siblings]` if this node is a partial type with sibling files
            sibs = (
                partial_siblings_map.get(fqn)
                or partial_siblings_map.get(name)
                or (node.get("metadata") or {}).get("partial_siblings")
                or []
            )
            if is_partial and sibs:
                sib_prefix = "  " * (indent + 2)
                lines.append(
                    f"{sib_prefix}[Partial Siblings] (尚有 {len(sibs)} 個同名分部檔案；加 `--merged` 檢視合併成員):"
                )
                for sib in sibs:
                    s_fp = sib.get("file_path", "")
                    s_l1 = sib.get("line_number", 1)
                    s_l2 = sib.get("end_line", s_l1)
                    m_cnt = sib.get("member_count", 0)
                    lines.append(f"{sib_prefix}  ~ {s_fp}:L{s_l1}-L{s_l2} ({m_cnt} member(s))")

    def _format_ambiguous_output(
        self,
        title: str,
        result: Dict[str, Any],
        is_md: bool = False,
        file_uri: Optional[bool] = None,
    ) -> str:
        eff_file_uri = True if is_md else (self.file_uri if file_uri is None else bool(file_uri))
        query = result.get("target_query") or result.get("query") or ""
        candidates = result.get("candidates") or []
        if is_md:
            lines = [
                f"### {title}: `{query}` (偵測到跨型別同名歧義 - 共 {len(candidates)} 個候選符號)",
                "",
                "> 請使用精確選擇器語法 `[kind] [scope.]name[(param_types...)]` 指定目標：",
                "",
            ]
            for c in candidates:
                link = self.format_file_link(
                    c.get("file_path", ""),
                    line=c.get("line_number", 1),
                    end_line=c.get("end_line"),
                    file_uri=eff_file_uri,
                )
                lines.append(
                    f"- `{c.get('kind', '')}` **{c.get('fqn') or c.get('name', '')}** — `{c.get('signature', '')}` ({link})"
                )
            return "\n".join(lines)

        lines = [
            f"[ast] Ambiguous symbol '{query}': 命中多個不同父型別之同名符號 (共 {len(candidates)} 個候選):",
            "請使用 `[kind] [scope.]name[(param_types...)]` 消除歧義：",
        ]
        for c in candidates:
            link = self.format_file_link(
                c.get("file_path", ""),
                line=c.get("line_number", 1),
                end_line=c.get("end_line"),
                file_uri=eff_file_uri,
            )
            lines.append(
                f"  - [{c.get('kind', '')}] {c.get('fqn') or c.get('name', '')} :: {c.get('signature', '')} ({link})"
            )
        return "\n".join(lines)

    @staticmethod
    def _coerce_symbol_dict(sym: Any) -> Dict[str, Any]:
        if isinstance(sym, dict):
            return sym
        if hasattr(sym, "to_dict"):
            return sym.to_dict()
        return {
            "id": getattr(sym, "id", ""),
            "name": getattr(sym, "name", ""),
            "fqn": getattr(sym, "fqn", ""),
            "kind": getattr(sym, "kind", ""),
            "file_path": getattr(sym, "file_path", ""),
            "line_number": getattr(sym, "line_number", 1),
            "end_line": getattr(sym, "end_line", 1),
            "signature": getattr(sym, "signature", ""),
            "docstring": getattr(sym, "docstring", ""),
            "language": getattr(sym, "language", ""),
        }

    def _format_topology_tree(
        self,
        direction: str,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
        file_uri: Optional[bool] = None,
    ) -> str:
        is_md = format_type == "md"
        eff_file_uri = True if is_md else (self.file_uri if file_uri is None else bool(file_uri))
        is_callers = direction == "callers"
        title = "調用源查詢" if is_callers else "下游被調用者查詢"

        if result.get("status") == "ambiguous" or result.get("ambiguous"):
            return self._format_ambiguous_output(title, result, is_md=is_md, file_uri=eff_file_uri)

        raw_target = result.get("target_symbol") or result.get("target")
        if not raw_target:
            q = result.get("target_query") or result.get("query") or ""
            if is_md:
                return f"###  {title}: `{q}` (未找到相符符號)"
            return f"[ast] 查無相符目標符號: '{q}'"

        target = self._coerce_symbol_dict(raw_target)
        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        items_key = "callers" if is_callers else "callees"
        raw_items = result.get(items_key, [])
        total_items = len(raw_items)
        target_link = self.format_file_link(
            target["file_path"],
            line=target["line_number"],
            end_line=target.get("end_line"),
            file_uri=eff_file_uri,
        )

        filtered_items = raw_items
        if isinstance(limit_mode, int) and limit_mode > 0:
            filtered_items = raw_items[:limit_mode]

        overloads = result.get("overloads") or []
        overload_tag = f" [Overload Group: {len(overloads)} overloads]" if len(overloads) > 1 else ""

        if is_md:
            if is_callers:
                header = f"###  調用源追蹤 (Callers): `{target['name']}`{overload_tag} (共找到 {total_items} 個調用來源):\n\n"
            else:
                header = f"###  下游被調用者追蹤 (Callees): `{target['name']}`{overload_tag} (共調用 {total_items} 個內部組件):\n\n"
            header += f"- ** 目標符號**: `{target['name']}` ({target['kind']}) 檔案: {target_link}"
            if target.get("signature"):
                header += f"\n  - **簽名**: `{target['signature']}`"
            lines = [header]
            if len(overloads) > 1:
                lines.append("  - **重載群組 (Overload Group)**:")
                for ov in overloads:
                    ov_d = self._coerce_symbol_dict(ov)
                    lines.append(f"    - `{ov_d.get('signature') or ov_d.get('name')}` (L{ov_d.get('line_number', 1)})")
            lines.append("")
        else:
            if is_callers:
                header = f"[ast] 符號 '{target['name']}'{overload_tag} 之上游調用者清單 (Callers - 共 {total_items} 個來源):"
            else:
                header = f"[ast] 符號 '{target['name']}'{overload_tag} 之內部下游依賴清單 (Callees - 共 {total_items} 個被調用項):"
            lines = [
                header,
                "-" * 85,
                f" 目標符號: `{target['name']}` ({target['kind']}) 檔案: {target_link}",
            ]
            if len(overloads) > 1:
                lines.append(f" [Overload Group] 共聚合 {len(overloads)} 個同型別方法重載:")
                for ov in overloads:
                    ov_d = self._coerce_symbol_dict(ov)
                    lines.append(f"   * {ov_d.get('signature') or ov_d.get('name')} ({ov_d.get('file_path')}:L{ov_d.get('line_number', 1)})")
            elif mode == "detail" and target.get("signature"):
                lines.append(f"   簽名: {target['signature']}")
            lines.append("")

        if not filtered_items:
            empty_msg = "  (目前尚無靜態調用關係)" if not is_md else "> *(目前尚無靜態調用關係)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        for idx, item in enumerate(filtered_items, start=1):
            sym = self._coerce_symbol_dict(item["symbol"])
            sites = item.get("call_sites", [])
            if is_callers:
                primary_line = sites[0].get("line_number", sym["line_number"]) if sites else sym["line_number"]
                link_str = self.format_file_link(sym["file_path"], line=primary_line, file_uri=eff_file_uri)
            else:
                link_str = self.format_file_link(
                    sym["file_path"],
                    line=sym["line_number"],
                    end_line=sym.get("end_line"),
                    file_uri=eff_file_uri,
                )
            is_last = idx == len(filtered_items)
            branch = "└──" if is_last else "├──"
            pipe = "   " if is_last else "│  "
            code_snip = item.get("code_snippet")

            site_strs = [f"L{s.get('line_number', s.get('line'))}" for s in sites if s.get("line_number") or s.get("line")]
            site_info = f" [調用點: {', '.join(site_strs)}]" if site_strs else ""

            if is_md:
                lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym['kind']}`: **{sym['name']}**){site_info}")
                if snippet and code_snip and hasattr(code_snip, "get_lines"):
                    snip_lines = code_snip.get_lines(15)
                    if snip_lines:
                        lines.append(f"  ```{sym.get('language') or ''}")
                        for ln, code in snip_lines:
                            mark = ">" if ln == code_snip.target_line else " "
                            lines.append(f"  {mark} {ln:5d} | {code}")
                        lines.append("  ```")
            else:
                lines.append(
                    f"{branch} #{idx:02d} 檔案: {self.styler.path(link_str)} "
                    f"({self.styler.kind(sym['kind'])}:{self.styler.symbol(sym['name'])}){site_info}"
                )
                if mode == "detail" and sym.get("signature"):
                    lines.append(f"{pipe}   簽名: {sym['signature']}")
                if snippet and code_snip and hasattr(code_snip, "format_text"):
                    formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=15)
                    if formatted_snip:
                        lines.append(formatted_snip)

        return "\n".join(lines)

    def format_callers_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
        file_uri: Optional[bool] = None,
    ) -> str:
        return self._format_topology_tree(
            direction="callers",
            result=result,
            detail_mode=detail_mode,
            snippet=snippet,
            format_type=format_type,
            limit_mode=limit_mode,
            file_uri=file_uri,
        )

    def format_callees_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
        file_uri: Optional[bool] = None,
    ) -> str:
        return self._format_topology_tree(
            direction="callees",
            result=result,
            detail_mode=detail_mode,
            snippet=snippet,
            format_type=format_type,
            limit_mode=limit_mode,
            file_uri=file_uri,
        )

    def format_impact_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
        file_uri: Optional[bool] = None,
    ) -> str:
        is_md = format_type == "md"
        eff_file_uri = True if is_md else (self.file_uri if file_uri is None else bool(file_uri))
        if result.get("status") == "ambiguous" or result.get("ambiguous"):
            return self._format_ambiguous_output("影響面拓撲查詢", result, is_md=is_md, file_uri=eff_file_uri)

        raw_target = result.get("target_symbol") or result.get("target")
        if not raw_target:
            q = result.get("target_query") or result.get("query") or ""
            if is_md:
                return f"###  影響面拓撲查詢: `{q}` (未找到相符符號)"
            return f"[ast] 查無相符目標符號: '{q}'"

        target = self._coerce_symbol_dict(raw_target)
        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        target_link = self.format_file_link(target["file_path"], line=target["line_number"], end_line=target.get("end_line"), file_uri=eff_file_uri)
        depth = result.get("max_depth", result.get("depth", 2))
        total_syms = result.get("total_impacted_symbols", result.get("total_affected_symbols", 0))
        total_files = result.get("total_impacted_files", len(result.get("affected_files") or []))
        overloads = result.get("overloads") or []
        overload_tag = f" [Overload Group: {len(overloads)} overloads]" if len(overloads) > 1 else ""

        if is_md:
            header = f"###  重構影響面擴散拓撲 (Impact Analysis): `{target['name']}`{overload_tag}\n\n"
            header += f"- ** 目標核心符號**: `{target['name']}` ({target['kind']}) 檔案: {target_link}\n"
            if mode == "detail" and target.get("signature"):
                header += f"  - **簽名**: `{target['signature']}`\n"
            header += f"- ** 影響半徑**: 擴散深度 `{depth}` 階，波及 `{total_syms}` 個符號 / `{total_files}` 個實體檔案"
            lines = [header, ""]
        else:
            header = (
                f"[ast] 符號 '{target['name']}'{overload_tag} 重構影響面擴散拓撲 "
                f"(Blast Radius: {depth} 階深度, 影響 {total_syms} 個符號 / {total_files} 個檔案):"
            )
            lines = [
                header,
                "-" * 85,
                f" 目標核心符號: `{target['name']}` ({target['kind']}) 檔案: {target_link}",
            ]
            if len(overloads) > 1:
                lines.append(f" [Overload Group] 共聚合 {len(overloads)} 個同型別方法重載:")
                for ov in overloads:
                    ov_d = self._coerce_symbol_dict(ov)
                    lines.append(f"   * {ov_d.get('signature') or ov_d.get('name')} ({ov_d.get('file_path')}:L{ov_d.get('line_number', 1)})")
            elif mode == "detail" and target.get("signature"):
                lines.append(f"   簽名: {target['signature']}")
            lines.append("")

        layers = result.get("layers", {})
        if not layers:
            empty_msg = "  (未發現上游依賴影響點，修改安全)" if not is_md else "> *(未發現上游依賴影響點，修改安全)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        sorted_depths = sorted(layers.keys(), key=lambda x: int(x))
        max_items = limit_mode if (isinstance(limit_mode, int) and limit_mode > 0) else None
        effective_layers: List[Tuple[Any, List[Any]]] = []
        remaining = max_items
        for d in sorted_depths:
            syms_list = list(layers[d] or [])
            if not syms_list:
                continue
            if remaining is not None:
                if remaining <= 0:
                    break
                syms_list = syms_list[:remaining]
                remaining -= len(syms_list)
            if syms_list:
                effective_layers.append((d, syms_list))

        if not effective_layers:
            empty_msg = "  (未發現上游依賴影響點，修改安全)" if not is_md else "> *(未發現上游依賴影響點，修改安全)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        for d_idx, (d, syms) in enumerate(effective_layers):
            is_last_depth = d_idx == len(effective_layers) - 1
            depth_branch = "└──" if is_last_depth else "├──"
            hop_int = int(d)
            tag_name = f"{hop_int} 階直接影響 (Direct Callers)" if hop_int == 1 else f"{hop_int} 階間接影響 (Transitive Callers Level {hop_int})"

            if is_md:
                lines.append(f"#### 階層 {hop_int}：{tag_name} ({len(syms)} 個符號)")
            else:
                icon = "[SAFE]" if hop_int == 1 else "[CONDITIONAL]"
                lines.append(f"{depth_branch} {icon} {tag_name} - {len(syms)} 個符號:")

            sub_prefix = "    " if is_last_depth else "│   "
            for s_idx, raw_s in enumerate(syms):
                s = self._coerce_symbol_dict(raw_s)
                is_last_sym = s_idx == len(syms) - 1
                sub_branch = "└──" if is_last_sym else "├──"
                sym_pipe = "   " if is_last_sym else "│  "
                link_str = self.format_file_link(s["file_path"], line=s["line_number"], end_line=s.get("end_line"), file_uri=eff_file_uri)
                rendered_nodes += 1
                if is_md:
                    sig_suffix = f" — `{s['signature']}`" if (mode == "detail" and s.get("signature")) else ""
                    lines.append(f"- **#{rendered_nodes:02d}** 檔案: {link_str} (`{s['kind']}`: **{s['name']}**){sig_suffix}")
                else:
                    lines.append(
                        f"{sub_prefix}{sub_branch} #{rendered_nodes:02d} 檔案: {self.styler.path(link_str)} "
                        f"({self.styler.kind(s['kind'])}:{self.styler.symbol(s['name'])})"
                    )
                    if mode == "detail" and s.get("signature"):
                        lines.append(f"{sub_prefix}{sym_pipe}   簽名: {s['signature']}")

        return "\n".join(lines)

    def format_status_output(self, st: Dict[str, Any], as_json: bool = False) -> str:
        if as_json:
            return format_json(st)
        lines = [
            f"[ast] AST 引擎狀態摘要 (世代 ast_generation={st.get('ast_generation', 0)}):",
            f"  - 存儲空間根目錄: {self.styler.path(str(st.get('storage_dir', '')))}",
            f"  - 統一符號快照  : {'已建立' if st.get('has_symbols_index') or st.get('index_exists') else '未建立'} ({st.get('total_symbols', 0)} 個符號)",
            f"  - 雙向呼叫圖譜  : {'已建立' if st.get('has_graph_index') or st.get('index_exists') else '未建立'} ({st.get('total_edges', 0)} 條呼叫邊)",
        ]
        if st.get("building_in_progress"):
            b_prog = st.get("build_progress") or st.get("build_phase") or "working"
            lines.append(f"  - 當前建圖狀態  : 建圖進行中 ({b_prog})")
        langs = st.get("registered_languages") or []
        if langs:
            lines.append(f"  - 已註冊解析器  : {len(langs)} 種語言 ({', '.join(langs)})")
        space_gens = st.get("space_generations") or {}
        if space_gens:
            lines.append("  - 空間世代水位  :")
            for sp, gen in sorted(space_gens.items()):
                lines.append(f"    * {sp}: gen={gen}")
        return "\n".join(lines)

    def format_slice_output(
        self,
        target_query: str,
        part: str,
        sliced_text: str,
        as_json: bool = False,
    ) -> str:
        if as_json:
            return format_json(
                {
                    "status": "matched",
                    "target_query": target_query,
                    "part": part,
                    "content": sliced_text,
                }
            )
        return sliced_text

    def format_traverse_output(
        self,
        target_query: str,
        result: Dict[str, Any],
        as_json: bool = False,
        file_uri: Optional[bool] = None,
    ) -> str:
        eff_file_uri = self.file_uri if file_uri is None else bool(file_uri)
        if as_json:
            payload = {
                "status": "matched" if result.get("seed_ids") else "not_found",
                "target_query": target_query,
                "seed_ids": list(result.get("seed_ids") or ()),
                "direction": result.get("direction", "out"),
                "depth": result.get("depth", 1),
                "edge_kinds": list(result.get("edge_kinds") or ()),
                "total_reached_nodes": result.get("total_reached_nodes", 0),
                "layers": {
                    str(d): [n.to_dict() if hasattr(n, "to_dict") else n for n in nodes]
                    for d, nodes in (result.get("layers") or {}).items()
                },
                "edges": [e.to_dict() if hasattr(e, "to_dict") else e for e in (result.get("edges") or ())],
            }
            return format_json(payload)

        seeds = result.get("seed_nodes") or ()
        if not seeds:
            return f"[ast] 查無相符起始符號: '{target_query}'"

        dir_str = result.get("direction", "out")
        depth = result.get("depth", 1)
        kinds_str = ", ".join(result.get("edge_kinds") or ()) or "all"
        total_reached = result.get("total_reached_nodes", 0)
        lines = [
            f"[ast] 圖譜有向遍歷 (Traverse: query='{target_query}', direction={dir_str}, depth={depth}, kinds={kinds_str}, reached={total_reached}):",
            "-" * 85,
        ]
        layers = result.get("layers") or {}
        if not layers:
            lines.append("  (無符合條件之相鄰節點)")
            return "\n".join(lines)

        for d, nodes in sorted(layers.items()):
            lines.append(f"  [Depth {d}] ({len(nodes)} nodes):")
            for n in nodes:
                f_link = self.format_file_link(
                    n.file_path,
                    line=n.span.start_line,
                    end_line=n.span.end_line,
                    file_uri=eff_file_uri,
                )
                k_label = "/".join(sorted(n.kinds))
                lines.append(f"    - [{k_label}] {n.fqn} ({f_link})")
        return "\n".join(lines)


__all__ = [
    "ASTResultFormatter",
    "TerminalStyler",
    "format_json",
]
