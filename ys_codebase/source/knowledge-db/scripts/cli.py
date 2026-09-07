"""
CLI router entry point for module:knowledge-db.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""

import json
import os
import sys
from typing import Any, List, Optional, Union

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
from knowledge_db.engine import KnowledgeEngine, get_engine
from knowledge_db.exceptions import KnowledgeDBError, SpaceNotFoundError
from knowledge_db.formatter import TerminalStyler


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """容錯正規化：若傳入 List[str] 則包裝為 CmdBags，支援內部測試直呼。"""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (list, tuple)):
        args = list(cmd_bags)
        raw_cmd = " ".join(args)
        opts = {}
        pos = []
        for a in args:
            if a.startswith("--"):
                k = a[2:]
                v = True
                if "=" in k:
                    k, val = k.split("=", 1)
                    v = val
                opts[k] = CmdOption(name=k, params=v)
            elif a.startswith("-") and len(a) > 1:
                k = a[1:]
                opts[k] = CmdOption(name=k, params=True)
            else:
                pos.append(a)
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    return CmdBags(raw_cmd="", command=default_cmd, args=[], options={})


def _setup_stream_encodings():
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


def status(cmd_bags: Any) -> int:
    """查看知識庫空間狀態、指紋快取、同義詞與索引統計。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "status")
    engine = get_engine()

    try:
        st = engine.status()
        styler = TerminalStyler(sys.stdout)
        print(f"[knowledge-db] 系統狀態摘要 (共 {st['total_spaces']} 個空間，{st['thesaurus_groups']} 組同義詞):")
        print(f"  - 存儲空間根目錄: {styler.path(st['storage_dir'])}")
        unified_str = styler.symbol("已建立") if st.get("has_unified_index") else styler.warn("未建立")
        print(f"  - 全域倒排索引: {unified_str}")
        if not st.get("enable_vector_search"):
            vec_str = styler.line("已停用 (依組態停用向量檢索)")
        elif st.get("has_vector_index"):
            vec_str = styler.symbol(f"已建立 (模型: {st.get('embedding_model')})")
        else:
            vec_str = styler.warn("未建立")
        print(f"  - 向量特徵索引: {vec_str}")
        print("-" * 80)
        for name, sp in st["spaces"].items():
            pat_str = f" [patterns: {', '.join(sp['file_patterns'])}]" if sp.get('file_patterns') else " [all files]"
            is_idx = sp.get('has_index') or sp.get('index_cached') or st.get("has_unified_index")
            idx_str = styler.symbol("已建立") if is_idx else styler.warn("未建立")
            print(f"  - 空間: {styler.path(name)} (來源: {sp.get('origin', 'unknown')}){pat_str}")
            if sp.get("description"):
                print(f"    說明: {sp['description']}")
            print(f"    來源目錄數: {sp.get('include_count', 0)}, 快取檔案: {sp.get('cached_files', sp.get('fingerprint_cached_files', 0))} 檔, 倒排索引: {idx_str}")
        print("-" * 80)
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def scan(cmd_bags: Any) -> int:
    """執行指定空間或全空間聯集增量指紋掃描。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "scan")
    engine = get_engine()

    try:
        force = bags.has_option("force")
        targets = bags.args
        space_target = targets[0] if targets and not (bags.has_option("all") or bags.has_option("a")) else None

        results = engine.scan(space=space_target, force=force)
        scope_desc = f"空間 '{space_target}'" if space_target else f"全空間聯集 ({len(results)} 個空間)"
        print(f"[knowledge-db] {scope_desc} 增量指紋掃描完成:")
        for sp_name, diff in results.items():
            print(
                f"  - {sp_name}: Added={len(diff.added)}, Modified={len(diff.modified)}, "
                f"Deleted={len(diff.deleted)}, Unchanged={len(diff.unchanged)}"
            )
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def bundle(cmd_bags: Any) -> int:
    """執行指定空間或全空間聯集之多語言語意打包與導出。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "bundle")
    engine = get_engine()

    try:
        targets = bags.args
        space_target = targets[0] if targets and not (bags.has_option("all") or bags.has_option("a")) else None
        out_arg = str(bags.get_option("output")) if bags.get_option("output") else None

        bundles = engine.bundle(space=space_target, export_path=out_arg)
        print(f"[knowledge-db] 語意打包完成 (共 {len(bundles)} 個空間):")
        for b in bundles:
            print(f"  - 空間 '{b.space_name}': 打包 {len(b.symbols)} 個符號，{len(b.thesaurus)} 組同義詞")
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def index(cmd_bags: Any) -> int:
    """建置與快取指定空間或全空間聯集之多欄位倒排索引。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "index")
    engine = get_engine()

    try:
        force = bags.has_option("force") or bags.has_option("f")
        targets = bags.args
        space_target = targets[0] if targets and not (bags.has_option("all") or bags.has_option("a")) else None

        indices = engine.build_index(space=space_target, force=force, interactive=True)
        print(f"[knowledge-db] 倒排索引建置完成 (共 {len(indices)} 個空間):")
        for sp_name, idx in indices.items():
            print(f"  - 空間 '{sp_name}': {idx.doc_count} 篇文檔符號，{len(idx.index)} 個 Term 索引詞")
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def search(cmd_bags: Any) -> int:
    """對全空間或指定空間符號進行多欄位加權 BM25 語意檢索。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "search")
    engine = get_engine()

    try:
        queries = bags.args
        if not queries:
            print("[knowledge-db] 錯誤: 請輸入檢索查詢詞。例如: python yscb.py knowledge-db search 'InvertedIndex' -s", file=sys.stderr)
            return 1

        query_str = " ".join(queries)
        space_filter = str(bags.get_option("space")) if bags.get_option("space") else None
        kind_filter = [str(bags.get_option("kind"))] if bags.get_option("kind") else None
        lang_filter = [str(bags.get_option("lang"))] if bags.get_option("lang") else None
        ftype_filter = str(bags.get_option("ftype")) if bags.get_option("ftype") else None
        
        limit_val: Union[int, str] = "auto"
        l_opt = bags.get_option("limit")
        if l_opt:
            l_val = str(l_opt).strip()
            if l_val.lower() == "auto":
                limit_val = "auto"
            else:
                try:
                    limit_val = int(l_val)
                except ValueError:
                    limit_val = "auto"

        tier = "simple"
        if bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose"):
            tier = "detail"
        elif bags.has_option("snippet") or bags.has_option("s") or bags.has_option("preview"):
            tier = "snippet"
        elif bags.has_option("simple"):
            tier = "simple"

        is_json = bags.has_option("json")
        is_md = bags.has_option("md") or bags.has_option("markdown")
        lexical_only = bags.has_option("lexical-only")

        is_snippet = (tier == "snippet") or (tier == "detail" and (bags.has_option("s") or bags.has_option("snippet") or bags.has_option("preview")))
        detail_mode = "detail" if tier == "detail" else ("auto" if tier == "snippet" else "simple")
        fetch_limit = 50 if limit_val == "auto" else max(1, int(limit_val))

        from knowledge_db.selector import SymbolSelector
        parsed_sel = SymbolSelector.parse(query_str)
        search_query = query_str
        if parsed_sel.target_kinds and not kind_filter:
            kind_filter = list(parsed_sel.target_kinds)
            search_query = f"{parsed_sel.scope}.{parsed_sel.identifier}" if parsed_sel.scope else parsed_sel.identifier
        elif parsed_sel.is_callable and not kind_filter:
            kind_filter = ["function", "method"]
            search_query = f"{parsed_sel.scope}.{parsed_sel.identifier}" if parsed_sel.scope else parsed_sel.identifier

        results = engine.search(
            query=search_query,
            space=space_filter,
            kinds=kind_filter,
            languages=lang_filter,
            ftypes=ftype_filter,
            limit=fetch_limit,
            snippet=is_snippet,
            lexical_only=lexical_only,
        )

        if is_json:
            filtered_results = [res for res in results if res.items]
            if tier == "detail":
                data = [
                    {
                        "file_path": engine.normalize_workspace_path(res.file_path),
                        "file_uri": engine.to_file_uri(res.file_path, line=res.items[0].symbol.line_number if res.items else None),
                        "total_score": round(res.total_score, 2),
                        "language": res.language,
                        "items": [
                            {
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                "signature": itm.symbol.signature,
                                "summary": itm.snippet or (itm.code_snippet.docstring_summary if itm.code_snippet else ""),
                                **({"code": itm.code_snippet.get_raw_code(), "code_lines": [itm.code_snippet.start_line, itm.code_snippet.end_line]} if (itm.code_snippet and itm.code_snippet.lines) else {}),
                            }
                            for itm in res.items
                        ],
                    }
                    for res in filtered_results
                ]
                print(json.dumps({"query": query_str, "tier": "detail", "total": len(data), "results": data}, indent=2, ensure_ascii=False))
            elif tier == "snippet":
                data = [
                    {
                        "file_path": engine.normalize_workspace_path(res.file_path),
                        "file_uri": engine.to_file_uri(res.file_path, line=res.items[0].symbol.line_number if res.items else None),
                        "total_score": round(res.total_score, 2),
                        "language": res.language,
                        "items": [
                            {
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                "signature": itm.symbol.signature,
                                "summary": itm.snippet or (itm.code_snippet.docstring_summary if itm.code_snippet else ""),
                                **({"code": itm.code_snippet.get_raw_code(), "code_lines": [itm.code_snippet.start_line, itm.code_snippet.end_line]} if (itm.code_snippet and itm.code_snippet.lines) else {}),
                            }
                            for itm in res.items
                        ],
                    }
                    for res in filtered_results
                ]
                print(json.dumps({"query": query_str, "tier": "preview", "total": len(data), "results": data}, separators=(',', ':'), ensure_ascii=False))
            else:
                data = [
                    {
                        "file_path": engine.normalize_workspace_path(res.file_path),
                        "file_uri": engine.to_file_uri(res.file_path, line=res.items[0].symbol.line_number if res.items else None),
                        "total_score": round(res.total_score, 2),
                        "language": res.language,
                        "items": [
                            {
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                "signature": itm.symbol.signature,
                            }
                            for itm in res.items
                        ],
                    }
                    for res in filtered_results
                ]
                print(json.dumps({"query": query_str, "tier": "simple", "total": len(data), "results": data}, separators=(',', ':'), ensure_ascii=False))
            return 0

        fmt_type = "md" if is_md else "text"
        formatted_output = engine.format_search_output(
            results=results,
            query=query_str,
            detail_mode=detail_mode,
            snippet=is_snippet,
            format_type=fmt_type,
            limit_mode=limit_val,
        )
        print(formatted_output)
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def callers(cmd_bags: Any) -> int:
    """查詢調用指定函式/類別之所有上游調用者 (Callers) 與代碼切片。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "callers")
    engine = get_engine()

    try:
        targets = bags.args
        if not targets:
            print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db callers 'InvertedIndex.load_binary'", file=sys.stderr)
            return 1
        query_str = targets[0]
        space_target = str(bags.get_option("space")) if bags.get_option("space") else None
        
        tier = "simple"
        if bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose"):
            tier = "detail"
        elif bags.has_option("snippet") or bags.has_option("s") or bags.has_option("preview"):
            tier = "snippet"
        elif bags.has_option("simple"):
            tier = "simple"

        is_json = bags.has_option("json")
        is_md = bags.has_option("md") or bags.has_option("markdown")
        limit_val: Union[int, str] = "auto"
        l_opt = bags.get_option("limit")
        if l_opt:
            try:
                limit_val = int(str(l_opt).strip())
            except ValueError:
                limit_val = "auto"

        is_snippet = (tier == "snippet") or (tier == "detail" and (bags.has_option("s") or bags.has_option("snippet") or bags.has_option("preview")))
        detail_mode = "detail" if tier == "detail" else "simple"

        res = engine.act_callers(target_query=query_str, space=space_target, snippet=is_snippet)
        if is_json:
            tsym = res.get("target_symbol")
            raw_callers = res.get("callers", [])
            filtered_callers = raw_callers
            if isinstance(limit_val, int) and limit_val > 0:
                filtered_callers = raw_callers[:limit_val]

            if tier == "detail":
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "detail",
                    "target_symbol": {
                        "id": tsym.id,
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "file_uri": engine.to_file_uri(tsym.file_path, line=tsym.line_number),
                        "line_number": tsym.line_number,
                        "end_line": tsym.end_line,
                        "signature": tsym.signature,
                    } if tsym else None,
                    "total_callers": len(filtered_callers),
                    "callers": [
                        {
                            "caller_symbol": {
                                "id": c["caller_symbol"].id,
                                "name": c["caller_symbol"].name,
                                "kind": c["caller_symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["caller_symbol"].file_path),
                                "file_uri": engine.to_file_uri(c["caller_symbol"].file_path, line=c["caller_symbol"].line_number),
                                "line_number": c["caller_symbol"].line_number,
                                "end_line": c["caller_symbol"].end_line,
                                "signature": c["caller_symbol"].signature,
                            },
                            "call_sites": [
                                {
                                    "line_number": s.get("line_number"),
                                    "scope": s.get("scope"),
                                    "file_uri": engine.to_file_uri(c["caller_symbol"].file_path, line=s.get("line_number")),
                                }
                                for s in c.get("call_sites", [])
                            ],
                            **({"code_snippet": c["code_snippet"].to_dict()} if (is_snippet and c.get("code_snippet")) else {}),
                        }
                        for c in filtered_callers
                    ],
                }, indent=2, ensure_ascii=False))
            elif tier == "snippet":
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "preview",
                    "target_symbol": {
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "file_uri": engine.to_file_uri(tsym.file_path, line=tsym.line_number),
                        "line_number": tsym.line_number,
                        "end_line": tsym.end_line,
                        "signature": tsym.signature,
                    } if tsym else None,
                    "total_callers": len(filtered_callers),
                    "callers": [
                        {
                            "caller_symbol": {
                                "name": c["caller_symbol"].name,
                                "kind": c["caller_symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["caller_symbol"].file_path),
                                "line_number": c["caller_symbol"].line_number,
                                "end_line": c["caller_symbol"].end_line,
                            },
                            "call_sites": [s.get("line_number") for s in c.get("call_sites", []) if s.get("line_number")],
                            **({"code": c["code_snippet"].get_raw_code(), "code_lines": [c["code_snippet"].start_line, c["code_snippet"].end_line]} if (c.get("code_snippet") and c["code_snippet"].lines) else {}),
                        }
                        for c in filtered_callers
                    ],
                }, separators=(',', ':'), ensure_ascii=False))
            else:
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "simple",
                    "target_symbol": {
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "line_number": tsym.line_number,
                    } if tsym else None,
                    "total_callers": len(filtered_callers),
                    "callers": [
                        {
                            "caller_symbol": {
                                "name": c["caller_symbol"].name,
                                "kind": c["caller_symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["caller_symbol"].file_path),
                                "line_number": c["caller_symbol"].line_number,
                            },
                            "call_sites": [s.get("line_number") for s in c.get("call_sites", []) if s.get("line_number")],
                        }
                        for c in filtered_callers
                    ],
                }, separators=(',', ':'), ensure_ascii=False))
            return 0

        fmt_type = "md" if is_md else "text"
        print(engine.format_callers_output(
            result=res,
            detail_mode=detail_mode,
            snippet=is_snippet,
            format_type=fmt_type,
            limit_mode=limit_val,
        ))
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def callees(cmd_bags: Any) -> int:
    """查詢指定函式/類別內部調用了哪些下游方法 (Callees) 與依賴。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "callees")
    engine = get_engine()

    try:
        targets = bags.args
        if not targets:
            print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db callees 'InvertedIndex.patch_incremental'", file=sys.stderr)
            return 1
        query_str = targets[0]
        space_target = str(bags.get_option("space")) if bags.get_option("space") else None

        tier = "simple"
        if bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose"):
            tier = "detail"
        elif bags.has_option("snippet") or bags.has_option("s") or bags.has_option("preview"):
            tier = "snippet"
        elif bags.has_option("simple"):
            tier = "simple"

        is_json = bags.has_option("json")
        is_md = bags.has_option("md") or bags.has_option("markdown")
        limit_val: Union[int, str] = "auto"
        l_opt = bags.get_option("limit")
        if l_opt:
            try:
                limit_val = int(str(l_opt).strip())
            except ValueError:
                limit_val = "auto"

        is_snippet = (tier == "snippet") or (tier == "detail" and (bags.has_option("s") or bags.has_option("snippet") or bags.has_option("preview")))
        detail_mode = "detail" if tier == "detail" else "simple"

        res = engine.act_callees(target_query=query_str, space=space_target, snippet=is_snippet)
        if is_json:
            tsym = res.get("target_symbol")
            raw_callees = res.get("callees", [])
            filtered_callees = raw_callees
            if isinstance(limit_val, int) and limit_val > 0:
                filtered_callees = raw_callees[:limit_val]

            if tier == "detail":
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "detail",
                    "target_symbol": {
                        "id": tsym.id,
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "file_uri": engine.to_file_uri(tsym.file_path, line=tsym.line_number),
                        "line_number": tsym.line_number,
                        "end_line": tsym.end_line,
                        "signature": tsym.signature,
                    } if tsym else None,
                    "total_callees": len(filtered_callees),
                    "callees": [
                        {
                            "symbol": {
                                "id": c["symbol"].id,
                                "name": c["symbol"].name,
                                "kind": c["symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["symbol"].file_path),
                                "file_uri": engine.to_file_uri(c["symbol"].file_path, line=c["symbol"].line_number),
                                "line_number": c["symbol"].line_number,
                                "end_line": c["symbol"].end_line,
                                "signature": c["symbol"].signature,
                            },
                            "call_sites": [
                                {
                                    "line_number": s.get("line_number"),
                                    "scope": s.get("scope"),
                                    "file_uri": engine.to_file_uri(tsym.file_path if tsym else c["symbol"].file_path, line=s.get("line_number")),
                                }
                                for s in c.get("call_sites", [])
                            ],
                            **({"code_snippet": c["code_snippet"].to_dict()} if (is_snippet and c.get("code_snippet")) else {}),
                        }
                        for c in filtered_callees
                    ],
                }, indent=2, ensure_ascii=False))
            elif tier == "snippet":
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "preview",
                    "target_symbol": {
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "file_uri": engine.to_file_uri(tsym.file_path, line=tsym.line_number),
                        "line_number": tsym.line_number,
                        "end_line": tsym.end_line,
                        "signature": tsym.signature,
                    } if tsym else None,
                    "total_callees": len(filtered_callees),
                    "callees": [
                        {
                            "symbol": {
                                "name": c["symbol"].name,
                                "kind": c["symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["symbol"].file_path),
                                "line_number": c["symbol"].line_number,
                                "end_line": c["symbol"].end_line,
                            },
                            "call_sites": [s.get("line_number") for s in c.get("call_sites", []) if s.get("line_number")],
                            **({"code": c["code_snippet"].get_raw_code(), "code_lines": [c["code_snippet"].start_line, c["code_snippet"].end_line]} if (c.get("code_snippet") and c["code_snippet"].lines) else {}),
                        }
                        for c in filtered_callees
                    ],
                }, separators=(',', ':'), ensure_ascii=False))
            else:
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "simple",
                    "target_symbol": {
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "line_number": tsym.line_number,
                    } if tsym else None,
                    "total_callees": len(filtered_callees),
                    "callees": [
                        {
                            "symbol": {
                                "name": c["symbol"].name,
                                "kind": c["symbol"].kind,
                                "file_path": engine.normalize_workspace_path(c["symbol"].file_path),
                                "line_number": c["symbol"].line_number,
                            },
                            "call_sites": [s.get("line_number") for s in c.get("call_sites", []) if s.get("line_number")],
                        }
                        for c in filtered_callees
                    ],
                }, separators=(',', ':'), ensure_ascii=False))
            return 0

        fmt_type = "md" if is_md else "text"
        print(engine.format_callees_output(
            result=res,
            detail_mode=detail_mode,
            snippet=is_snippet,
            format_type=fmt_type,
            limit_mode=limit_val,
        ))
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def impact(cmd_bags: Any) -> int:
    """評估符號變更或重構時向上擴散之多階調用影響面 (Blast Radius)。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "impact")
    engine = get_engine()

    try:
        targets = bags.args
        if not targets:
            print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db impact 'InvertedIndex.patch_incremental' --depth=2", file=sys.stderr)
            return 1
        query_str = targets[0]
        space_target = str(bags.get_option("space")) if bags.get_option("space") else None
        depth = 2
        d_opt = bags.get_option("depth")
        if d_opt:
            try:
                depth = int(str(d_opt).strip())
            except ValueError:
                depth = 2

        tier = "simple"
        if bags.has_option("detail") or bags.has_option("d") or bags.has_option("verbose"):
            tier = "detail"
        elif bags.has_option("simple"):
            tier = "simple"

        is_json = bags.has_option("json")
        is_md = bags.has_option("md") or bags.has_option("markdown")
        limit_val: Union[int, str] = "auto"
        l_opt = bags.get_option("limit")
        if l_opt:
            try:
                limit_val = int(str(l_opt).strip())
            except ValueError:
                limit_val = "auto"

        detail_mode = "detail" if tier == "detail" else "simple"
        res = engine.act_impact(target_query=query_str, depth=depth, space=space_target)
        if is_json:
            tsym = res.get("target_symbol")
            if tier == "detail":
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "detail",
                    "target_symbol": {
                        "id": tsym.id,
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "file_uri": engine.to_file_uri(tsym.file_path, line=tsym.line_number),
                        "line_number": tsym.line_number,
                        "end_line": tsym.end_line,
                        "signature": tsym.signature,
                    } if tsym else None,
                    "max_depth": res.get("max_depth", depth),
                    "total_impacted_symbols": res.get("total_impacted_symbols", 0),
                    "total_impacted_files": res.get("total_impacted_files", 0),
                    "layers": {
                        str(d): [
                            {
                                "id": s.id,
                                "name": s.name,
                                "kind": s.kind,
                                "file_path": engine.normalize_workspace_path(s.file_path),
                                "file_uri": engine.to_file_uri(s.file_path, line=s.line_number),
                                "line_number": s.line_number,
                                "end_line": s.end_line,
                                "signature": s.signature,
                            }
                            for s in syms
                        ]
                        for d, syms in res.get("layers", {}).items()
                    },
                    "call_chains": res.get("call_chains", {}),
                }, indent=2, ensure_ascii=False))
            else:
                print(json.dumps({
                    "target_query": res.get("target_query"),
                    "tier": "simple",
                    "target_symbol": {
                        "name": tsym.name,
                        "kind": tsym.kind,
                        "file_path": engine.normalize_workspace_path(tsym.file_path),
                        "line_number": tsym.line_number,
                    } if tsym else None,
                    "max_depth": res.get("max_depth", depth),
                    "total_impacted_symbols": res.get("total_impacted_symbols", 0),
                    "total_impacted_files": res.get("total_impacted_files", 0),
                    "layers": {
                        str(d): [
                            {
                                "name": s.name,
                                "kind": s.kind,
                                "file_path": engine.normalize_workspace_path(s.file_path),
                                "line_number": s.line_number,
                            }
                            for s in syms
                        ]
                        for d, syms in res.get("layers", {}).items()
                    },
                }, separators=(',', ':'), ensure_ascii=False))
            return 0

        fmt_type = "md" if is_md else "text"
        print(engine.format_impact_output(
            result=res,
            detail_mode=detail_mode,
            format_type=fmt_type,
            limit_mode=limit_val,
        ))
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def clean(cmd_bags: Any) -> int:
    """清理指定空間或全空間之指紋、Bundle 與倒排索引快取。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "clean")
    engine = get_engine()

    try:
        targets = bags.args
        space_target = targets[0] if targets and not (bags.has_option("all") or bags.has_option("a")) else None

        engine.clean(space=space_target)
        target_str = f"空間 '{space_target}'" if space_target else "全空間"
        print(f"[knowledge-db] 成功清理 {target_str} 之指紋、Bundle 與倒排索引快取。")
        return 0
    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1
