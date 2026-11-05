"""
CLI Router & Subcommand Entry Points for `module:ast@1.0.0.0`.
Aligned with `core.commands.CmdBags` contract and `contributes/core.json`.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Union

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """Normalize `cmd_bags` into `CmdBags` (supporting `CmdBags`, `list[str]`, or `dict` for test invocations)."""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (list, tuple)):
        args = list(cmd_bags)
        raw_cmd = " ".join(str(a) for a in args)
        opts: Dict[str, CmdOption] = {}
        pos: List[str] = []
        for a in args:
            a_str = str(a)
            if a_str.startswith("--"):
                k = a_str[2:]
                v: Any = True
                if "=" in k:
                    k, val = k.split("=", 1)
                    v = val
                opts[k] = CmdOption(name=k, params=v)
            elif a_str.startswith("-") and len(a_str) > 1:
                k = a_str[1:]
                opts[k] = CmdOption(name=k, params=True)
            else:
                pos.append(a_str)
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    if isinstance(cmd_bags, dict):
        # Support dict-style test bags `{"file": "...", "merged": True, "json": True}`
        inner = cmd_bags.get(default_cmd) if isinstance(cmd_bags.get(default_cmd), dict) else cmd_bags
        opts_dict: Dict[str, CmdOption] = {}
        pos_args: List[str] = []
        for k, v in inner.items():
            if k in ("file", "symbol") and isinstance(v, str) and v:
                pos_args.insert(0, v)
            elif v is True:
                opts_dict[k] = CmdOption(name=k, params=True)
            elif v not in (False, None):
                opts_dict[k] = CmdOption(name=k, params=v)
        return CmdBags(raw_cmd="", command=default_cmd, args=pos_args, options=opts_dict)
    return CmdBags(raw_cmd="", command=default_cmd, args=[], options={})


def _setup_stream_encodings() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _parse_common_display_options(bags: CmdBags) -> Dict[str, Any]:
    tier = "simple"
    if bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose"):
        tier = "detail"
    elif bags.has_option("snippet") or bags.has_option("s") or bags.has_option("preview"):
        tier = "snippet"
    elif bags.has_option("simple"):
        tier = "simple"

    is_json = bags.has_option("json")
    is_md = bags.has_option("md") or bags.has_option("markdown")
    file_uri = bags.has_option("file-uri") or bags.has_option("file_uri")
    limit_val: Union[int, str] = "auto"
    l_opt = bags.get_option_value("limit")
    if l_opt:
        l_str = str(l_opt).strip()
        if l_str.lower() == "auto":
            limit_val = "auto"
        else:
            try:
                limit_val = int(l_str)
            except ValueError:
                limit_val = "auto"

    is_snippet = (
        tier in ("snippet", "detail")
        or bags.has_option("s")
        or bags.has_option("snippet")
        or bags.has_option("preview")
    )
    return {
        "tier": tier,
        "is_json": is_json,
        "is_md": is_md,
        "file_uri": file_uri,
        "limit_val": limit_val,
        "is_snippet": is_snippet,
        "detail_mode": "detail" if tier == "detail" else "simple",
        "fmt_type": "md" if is_md else "text",
    }


def _get_engine() -> Any:
    from ast_engine.engine import get_engine

    return get_engine()


def _serialize_target_symbol(
    engine: Any, tsym: Any, tier: str, file_uri: bool = False
) -> Optional[Dict[str, Any]]:
    if not tsym:
        return None
    include_uri = (tier == "detail") or bool(file_uri)
    if isinstance(tsym, dict):
        fp = tsym.get("file_path", "")
        ln = int(tsym.get("line_number", 1))
        el = int(tsym.get("end_line", ln))
        if tier in ("detail", "snippet"):
            out = {
                "name": tsym.get("name", ""),
                "fqn": tsym.get("fqn") or tsym.get("name", ""),
                "kind": tsym.get("kind", ""),
                "file_path": engine.formatter.normalize_workspace_path(fp),
                **({"file_uri": engine.formatter.to_file_uri(fp, line=ln)} if include_uri else {}),
                "line_number": ln,
                "end_line": el,
                "signature": tsym.get("signature", ""),
            }
            if tier == "detail":
                out["id"] = tsym.get("id", "")
            return out
        return {
            "name": tsym.get("name", ""),
            "fqn": tsym.get("fqn") or tsym.get("name", ""),
            "kind": tsym.get("kind", ""),
            "file_path": engine.formatter.normalize_workspace_path(fp),
            **({"file_uri": engine.formatter.to_file_uri(fp, line=ln)} if include_uri else {}),
            "line_number": ln,
        }

    if tier in ("detail", "snippet"):
        out = {
            "name": tsym.name,
            "fqn": tsym.fqn or tsym.name,
            "kind": tsym.kind,
            "file_path": engine.formatter.normalize_workspace_path(tsym.file_path),
            **({"file_uri": engine.formatter.to_file_uri(tsym.file_path, line=tsym.line_number)} if include_uri else {}),
            "line_number": tsym.line_number,
            "end_line": tsym.end_line,
            "signature": tsym.signature,
        }
        if tier == "detail":
            out["id"] = tsym.id
        return out
    return {
        "name": tsym.name,
        "fqn": tsym.fqn or tsym.name,
        "kind": tsym.kind,
        "file_path": engine.formatter.normalize_workspace_path(tsym.file_path),
        **({"file_uri": engine.formatter.to_file_uri(tsym.file_path, line=tsym.line_number)} if include_uri else {}),
        "line_number": tsym.line_number,
    }


def outline(cmd_bags: Any) -> int:
    """Extract hierarchical AST outline for a single file (`yscb.py ast outline <file> [--merged] [--public|--private|...] [--static|--non-static] [--methods|--fields|--types] [--json]`)."""
    guard_dispatch("ast")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "outline")
    engine = _get_engine()

    try:
        if not bags.args:
            print("[ast] 錯誤: 請指定目標檔案路徑或語意 URI。例如: python yscb.py ast outline 'project://foo.py'", file=sys.stderr)
            return 1
        file_target = bags.args[0]
        merged = bags.has_option("merged") or bags.has_option("m")
        is_json = bags.has_option("json")

        vis_filter: Optional[str] = None
        for v_opt in ("public", "protected", "internal", "private", "non-private", "api"):
            if bags.has_option(v_opt):
                vis_filter = "non-private" if v_opt == "api" else v_opt
                break

        bind_filter: Optional[str] = None
        if bags.has_option("static"):
            bind_filter = "static"
        elif bags.has_option("non-static") or bags.has_option("nonstatic") or bags.has_option("instance"):
            bind_filter = "non-static"

        kind_filter: Optional[str] = None
        for k_opt in ("methods", "fields", "types"):
            if bags.has_option(k_opt):
                kind_filter = k_opt
                break

        res = engine.outline(
            file_or_uri=file_target,
            merged=merged,
            visibility=vis_filter,
            binding=bind_filter,
            member_kind=kind_filter,
        )
        is_detail = bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose")
        file_uri = bags.has_option("file-uri") or bags.has_option("file_uri")
        print(engine.formatter.format_outline_output(res, as_json=is_json, detail=is_detail, file_uri=file_uri))
        return 0
    except FileNotFoundError as exc:
        if bags.has_option("json"):
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[ast] 檔案不存在: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if bags.has_option("json"):
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[ast] 執行異常: {exc}", file=sys.stderr)
        return 1


def _serialize_ambiguous_json(res: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "status": "ambiguous",
            "ambiguous": True,
            "target_query": res.get("target_query"),
            "candidates": res.get("candidates", []),
        },
        indent=2,
        ensure_ascii=False,
    )


def _serialize_impact_json(engine: Any, res: Dict[str, Any], tier: str, depth: int, file_uri: bool = False) -> str:
    if res.get("status") == "ambiguous" or res.get("ambiguous"):
        return _serialize_ambiguous_json(res)
    tsym = res.get("target_symbol")
    payload = {
        "status": res.get("status", "matched"),
        "target_query": res.get("target_query"),
        "tier": "detail" if tier == "detail" else "simple",
        "target_symbol": _serialize_target_symbol(engine, tsym, tier, file_uri=file_uri),
        "overloads": [
            _serialize_target_symbol(engine, ov, tier, file_uri=file_uri)
            for ov in (res.get("overload_symbols") or res.get("overloads") or [])
        ],
        "max_depth": res.get("max_depth", depth),
        "total_impacted_symbols": res.get("total_impacted_symbols", 0),
        "total_impacted_files": res.get("total_impacted_files", 0),
        "layers": {
            str(d): [_serialize_target_symbol(engine, s, tier, file_uri=file_uri) for s in syms]
            for d, syms in res.get("layers", {}).items()
        },
    }
    if tier == "detail":
        payload["call_chains"] = res.get("call_chains", {})
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _serialize_call_edges_json(
    engine: Any,
    res: Dict[str, Any],
    is_callers: bool,
    tier: str,
    limit_val: Union[int, str],
    is_snippet: bool,
    file_uri: bool = False,
) -> str:
    if res.get("status") == "ambiguous" or res.get("ambiguous"):
        return _serialize_ambiguous_json(res)
    tsym = res.get("target_symbol")
    list_key = "callers" if is_callers else "callees"
    total_key = "total_callers" if is_callers else "total_callees"
    sym_key = "caller_symbol" if is_callers else "symbol"
    raw_items = res.get(list_key, [])
    filtered_items = raw_items[:limit_val] if (isinstance(limit_val, int) and limit_val > 0) else raw_items

    payload = {
        "status": res.get("status", "matched"),
        "target_query": res.get("target_query"),
        "tier": "detail" if tier == "detail" else ("preview" if tier == "snippet" else "simple"),
        "target_symbol": _serialize_target_symbol(engine, tsym, tier, file_uri=file_uri),
        "overloads": [
            _serialize_target_symbol(engine, ov, tier, file_uri=file_uri)
            for ov in (res.get("overload_symbols") or res.get("overloads") or [])
        ],
        total_key: len(filtered_items),
        list_key: [
            {
                sym_key: _serialize_target_symbol(engine, c["symbol"], tier, file_uri=file_uri),
                "call_sites": [
                    s.get("line_number")
                    for s in c.get("call_sites", [])
                    if s.get("line_number")
                ]
                if tier != "detail"
                else c.get("call_sites", []),
                **(
                    {
                        "code": c["code_snippet"].get_raw_code(),
                        "code_lines": [c["code_snippet"].start_line, c["code_snippet"].end_line],
                    }
                    if (is_snippet and c.get("code_snippet") and c["code_snippet"].lines)
                    else {}
                ),
            }
            for c in filtered_items
        ],
    }
    if tier == "detail":
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _run_topology_cli_command(cmd_name: str, cmd_bags: Any, example_usage: str) -> int:
    from ast_engine.exceptions import ASTError
    from file_space import FileSpaceNotFoundError

    guard_dispatch("ast")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, cmd_name)
    engine = _get_engine()

    try:
        targets = bags.args
        if not targets:
            print(f"[ast] 錯誤: 請指定目標符號名稱。例如: {example_usage}", file=sys.stderr)
            return 1
        query_str = " ".join(targets) if len(targets) > 1 else targets[0]
        space_target = bags.get_option_value("space")
        ftype_filter = bags.get_option_value("ftype")
        opts = _parse_common_display_options(bags)
        tier = opts["tier"]
        limit_val = opts["limit_val"]
        is_snippet = opts["is_snippet"]

        if cmd_name == "impact":
            depth = 2
            d_opt = bags.get_option_value("depth")
            if d_opt:
                try:
                    depth = int(str(d_opt).strip())
                except ValueError:
                    depth = 2
            res = engine.impact(target_query=query_str, depth=depth, space=space_target, ftypes=ftype_filter)
            if opts["is_json"]:
                print(_serialize_impact_json(engine, res, tier, depth, file_uri=opts["file_uri"]))
                return 0

            print(
                engine.formatter.format_impact_output(
                    result=res,
                    detail_mode=opts["detail_mode"],
                    format_type=opts["fmt_type"],
                    limit_mode=limit_val,
                    file_uri=opts["file_uri"],
                )
            )
            return 0

        is_callers = cmd_name == "callers"
        if is_callers:
            res = engine.callers(target_query=query_str, space=space_target, snippet=is_snippet, ftypes=ftype_filter)
        else:
            res = engine.callees(target_query=query_str, space=space_target, snippet=is_snippet, ftypes=ftype_filter)

        if opts["is_json"]:
            print(_serialize_call_edges_json(engine, res, is_callers, tier, limit_val, is_snippet, file_uri=opts["file_uri"]))
            return 0

        formatter_fn = engine.formatter.format_callers_output if is_callers else engine.formatter.format_callees_output
        print(
            formatter_fn(
                result=res,
                detail_mode=opts["detail_mode"],
                snippet=is_snippet,
                format_type=opts["fmt_type"],
                limit_mode=limit_val,
                file_uri=opts["file_uri"],
            )
        )
        return 0
    except FileSpaceNotFoundError as exc:
        print(f"[ast] 空間不存在: {exc}", file=sys.stderr)
        return 1
    except ASTError as exc:
        print(f"[ast] 操作失敗: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ast] 執行異常: {exc}", file=sys.stderr)
        return 1


def callers(cmd_bags: Any) -> int:
    """Query upstream callers (`yscb.py ast callers <symbol>`)."""
    return _run_topology_cli_command(
        "callers",
        cmd_bags,
        "python yscb.py ast callers 'Window.Open'",
    )


def callees(cmd_bags: Any) -> int:
    """Query downstream callees (`yscb.py ast callees <symbol>`)."""
    return _run_topology_cli_command(
        "callees",
        cmd_bags,
        "python yscb.py ast callees 'Window.Open'",
    )


def impact(cmd_bags: Any) -> int:
    """Analyze N-hop blast radius (`yscb.py ast impact <symbol> --depth=2`)."""
    return _run_topology_cli_command(
        "impact",
        cmd_bags,
        "python yscb.py ast impact 'Window.Open' --depth=2",
    )


def status(cmd_bags: Any) -> int:
    """Show AST snapshot generation, symbol/edge counts, and registered parsers."""
    guard_dispatch("ast")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "status")
    engine = _get_engine()

    try:
        targets = bags.args
        space_target = bags.get_option_value("space") or (targets[0] if targets else None)
        st = engine.status(space=space_target)
        print(engine.formatter.format_status_output(st, as_json=bags.has_option("json")))
        return 0
    except Exception as exc:
        print(f"[ast] 執行異常: {exc}", file=sys.stderr)
        return 1


def clean(cmd_bags: Any) -> int:
    """Clean AST snapshot and call graph caches and reset `file-space` cursor (`consumer='ast'`)."""
    guard_dispatch("ast")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "clean")
    engine = _get_engine()

    try:
        targets = bags.args
        space_target = bags.get_option_value("space") or (targets[0] if targets else None)
        res = engine.clean(space=space_target)
        if bags.has_option("json"):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            target_str = f"空間 '{space_target}'" if space_target else "全空間"
            print(f"[ast] 成功清理 {target_str} 之 AST 符號快照與呼叫圖譜快取。")
        return 0
    except Exception as exc:
        print(f"[ast] 執行異常: {exc}", file=sys.stderr)
        return 1


def dispatch_cli(cmd_bags: Any) -> int:
    """Unified entry point (`scripts/cli.py:dispatch_cli`)."""
    if isinstance(cmd_bags, CmdBags):
        cmd_map = {
            "outline": outline,
            "callers": callers,
            "callees": callees,
            "impact": impact,
            "status": status,
            "clean": clean,
        }
        fn = cmd_map.get(cmd_bags.command, status)
        return fn(cmd_bags)
    if isinstance(cmd_bags, dict):
        for name, fn in (
            ("outline", outline),
            ("callers", callers),
            ("callees", callees),
            ("impact", impact),
            ("status", status),
            ("clean", clean),
        ):
            if name in cmd_bags:
                return fn(cmd_bags)
    return status(cmd_bags)
