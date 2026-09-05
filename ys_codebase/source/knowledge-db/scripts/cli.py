"""
CLI router entry point for module:knowledge-db.
"""

import json
import os
import sys
from typing import List

# Windows 控制台 UTF-8 編碼保護
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

current_dir = os.path.dirname(os.path.abspath(__file__))
module_dir = os.path.dirname(current_dir)
modules_root = os.path.dirname(module_dir)

if os.path.isdir(modules_root):
    for m in os.listdir(modules_root):
        m_p = os.path.join(modules_root, m)
        if os.path.isdir(m_p) and m_p not in sys.path:
            sys.path.insert(0, m_p)

if module_dir not in sys.path:
    sys.path.insert(0, module_dir)

from knowledge_db.engine import KnowledgeEngine
from knowledge_db.exceptions import KnowledgeDBError, SpaceNotFoundError


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[knowledge-db] YS-Codebase Knowledge Database & Semantic Retrieval")
        print("Usage:")
        print("  python yscb.py knowledge-db status               列出所有註冊空間、快取與索引狀態")
        print("  python yscb.py knowledge-db scan [space | --all] 執行增量/全量檔案指紋掃描")
        print("  python yscb.py knowledge-db bundle [space|--all] 打包空間符號為 SemanticBundle")
        print("  python yscb.py knowledge-db search <query> [--preview|-s | --detail|-d | --simple] [--limit=auto|N] [--lexical-only] [--[json|md]] 多欄位複合/語意檢索 (預設 simple 大綱)")
        print("  python yscb.py knowledge-db callers <symbol> [--preview|-s | --detail|-d | --simple] [--space=X] [--[json|md]] 查詢上游調用者 (Who calls me?)")
        print("  python yscb.py knowledge-db callees <symbol> [--preview|-s | --detail|-d | --simple] [--space=X] [--[json|md]] 查詢下游被調用者 (Whom do I call?)")
        print("  python yscb.py knowledge-db impact <symbol> [--depth=N] [--detail|-d | --simple] [--space=X] [--[json|md]] 分析重構影響面擴散拓撲")
        print("  python yscb.py knowledge-db clean [space | --all] 清理指定或全空間快取檔案")
        return 0

    subcmd = argv[0]
    sub_argv = argv[1:]
    engine = KnowledgeEngine()

    try:
        if subcmd == "status":
            st = engine.status()
            print(f"[knowledge-db] 系統狀態摘要 (共 {st['total_spaces']} 個空間，{st['thesaurus_groups']} 組同義詞):")
            print(f"  - 存儲空間根目錄: {st['storage_dir']}")
            print("-" * 80)
            for name, sp in st["spaces"].items():
                pat_str = f" [patterns: {', '.join(sp['file_patterns'])}]" if sp.get('file_patterns') else " [all files]"
                idx_str = "已建立" if (sp.get('has_index') or sp.get('index_cached')) else "未建立"
                print(f"  - 空間: {name} (來源: {sp.get('origin', 'unknown')}){pat_str}")
                if sp.get("description"):
                    print(f"    說明: {sp['description']}")
                print(f"    來源目錄數: {sp.get('include_count', 0)}, 指紋快取檔案: {sp.get('cached_files', sp.get('fingerprint_cached_files', 0))} 檔, 倒排索引: {idx_str}")
            print("-" * 80)
            return 0

        elif subcmd == "scan":
            force = "--force" in sub_argv
            targets = [a for a in sub_argv if not a.startswith("-")]
            space_target = targets[0] if targets and "--all" not in sub_argv else None

            results = engine.scan(space=space_target, force=force)
            scope_desc = f"空間 '{space_target}'" if space_target else f"全空間聯集 ({len(results)} 個空間)"
            print(f"[knowledge-db] {scope_desc} 增量指紋掃描完成:")
            for sp_name, diff in results.items():
                print(
                    f"  - {sp_name}: Added={len(diff.added)}, Modified={len(diff.modified)}, "
                    f"Deleted={len(diff.deleted)}, Unchanged={len(diff.unchanged)}"
                )
            return 0

        elif subcmd == "bundle":
            targets = [a for a in sub_argv if not a.startswith("-")]
            space_target = targets[0] if targets and "--all" not in sub_argv else None
            out_arg = None
            for a in sub_argv:
                if a.startswith("--output="):
                    out_arg = a.split("=", 1)[1]

            bundles = engine.bundle(space=space_target, export_path=out_arg)
            print(f"[knowledge-db] 語意打包完成 (共 {len(bundles)} 個空間):")
            for b in bundles:
                print(f"  - 空間 '{b.space_name}': 打包 {len(b.symbols)} 個符號，{len(b.thesaurus)} 組同義詞")
            return 0

        elif subcmd == "index":
            force = "--force" in sub_argv
            targets = [a for a in sub_argv if not a.startswith("-")]
            space_target = targets[0] if targets and "--all" not in sub_argv else None

            indices = engine.build_index(space=space_target, force=force)
            print(f"[knowledge-db] 倒排索引建置完成 (共 {len(indices)} 個空間):")
            for sp_name, idx in indices.items():
                print(f"  - 空間 '{sp_name}': {idx.doc_count} 篇文檔符號，{len(idx.index)} 個 Term 索引詞")
            return 0

        elif subcmd == "search":
            queries = [a for a in sub_argv if not a.startswith("-")]
            if not queries:
                print("[knowledge-db] 錯誤: 請輸入檢索查詢詞。例如: python yscb.py knowledge-db search 'InvertedIndex' -s", file=sys.stderr)
                return 1

            query_str = " ".join(queries)
            space_filter = None
            kind_filter = None
            lang_filter = None
            ftype_filter = None
            limit_val: Union[int, str] = "auto"
            tier = "simple"
            is_json = False
            is_md = False
            no_auto = "--no-auto-rebuild" in sub_argv or "-n" in sub_argv

            for a in sub_argv:
                if a.startswith("--space="):
                    space_filter = a.split("=", 1)[1]
                elif a.startswith("--kind="):
                    kind_filter = [a.split("=", 1)[1]]
                elif a.startswith("--lang="):
                    lang_filter = [a.split("=", 1)[1]]
                elif a.startswith("--ftype="):
                    ftype_filter = a.split("=", 1)[1]
                elif a.startswith("--limit="):
                    l_val = a.split("=", 1)[1].strip()
                    if l_val.lower() == "auto":
                        limit_val = "auto"
                    else:
                        try:
                            limit_val = int(l_val)
                        except ValueError:
                            limit_val = "auto"
                elif a in ("--detail", "-d", "--verbose"):
                    tier = "detail"
                elif a in ("--snippet", "-s", "--preview"):
                    tier = "snippet"
                elif a == "--simple":
                    tier = "simple"
                elif a == "--json":
                    is_json = True
                elif a in ("--md", "--markdown"):
                    is_md = True

            is_snippet = (tier == "snippet") or (tier == "detail" and any(x in sub_argv for x in ("-s", "--snippet", "--preview")))
            detail_mode = "detail" if tier == "detail" else ("auto" if tier == "snippet" else "simple")
            fetch_limit = 50 if limit_val == "auto" else max(1, int(limit_val))

            lexical_only = "--lexical-only" in sub_argv

            # 支援以 SymbolSelector 解析具有類型前綴或調用限定的結構化查詢 (FR-04)
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
                auto_rebuild=not no_auto,
                lexical_only=lexical_only,
            )

            if is_json:
                filtered_results = results
                if limit_val == "auto":
                    if results:
                        top_score = results[0].total_score
                        filtered_results = []
                        prev_score = top_score
                        for r in results:
                            if r.total_score < 0.20 * top_score:
                                break
                            if prev_score > 0 and (r.total_score / prev_score) < 0.35 and len(filtered_results) >= 3:
                                break
                            filtered_results.append(r)
                            prev_score = r.total_score
                elif isinstance(limit_val, int) and limit_val > 0:
                    filtered_results = results[:limit_val]

                if tier == "detail":
                    data = []
                    for res in filtered_results:
                        f_dict = {
                            "file_path": engine.normalize_workspace_path(res.file_path),
                            "file_uri": engine.to_file_uri(res.file_path),
                            "total_score": round(res.total_score, 2),
                            "language": res.language,
                            "spaces": res.spaces,
                            "item_count": len(res.items),
                            "items": [
                                {
                                    "id": itm.symbol.id,
                                    "name": itm.symbol.name,
                                    "kind": itm.symbol.kind,
                                    "line_number": itm.symbol.line_number,
                                    "end_line": itm.symbol.end_line,
                                    "score": round(itm.score, 2),
                                    "matched_terms": itm.matched_terms,
                                    "file_uri": engine.to_file_uri(itm.symbol.file_path, line=itm.symbol.line_number),
                                    "signature": itm.symbol.signature,
                                    "snippet": itm.snippet,
                                    **({"code_snippet": itm.code_snippet.to_dict()} if (is_snippet and itm.code_snippet) else {}),
                                }
                                for itm in res.items
                            ],
                        }
                        data.append(f_dict)
                    print(json.dumps({"query": query_str, "tier": "detail", "total": len(data), "results": data}, indent=2, ensure_ascii=False))
                elif tier == "snippet":
                    data = []
                    for res in filtered_results:
                        f_dict = {
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
                        data.append(f_dict)
                    print(json.dumps({"query": query_str, "tier": "preview", "total": len(data), "results": data}, separators=(',', ':'), ensure_ascii=False))
                else:
                    data = []
                    for res in filtered_results:
                        f_dict = {
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
                        data.append(f_dict)
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

        elif subcmd == "callers":
            targets = [a for a in sub_argv if not a.startswith("-")]
            if not targets:
                print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db callers 'InvertedIndex.load_binary'", file=sys.stderr)
                return 1
            query_str = targets[0]
            tier = "simple"
            is_json = False
            is_md = False
            limit_val = "auto"
            space_target = None

            for a in sub_argv:
                if a.startswith("--space="):
                    space_target = a.split("=", 1)[1]
                elif a.startswith("--limit="):
                    l_val = a.split("=", 1)[1].strip()
                    if l_val.lower() == "auto":
                        limit_val = "auto"
                    else:
                        try:
                            limit_val = int(l_val)
                        except ValueError:
                            limit_val = "auto"
                elif a in ("--detail", "-d", "--verbose"):
                    tier = "detail"
                elif a in ("--snippet", "-s", "--preview"):
                    tier = "snippet"
                elif a == "--simple":
                    tier = "simple"
                elif a == "--json":
                    is_json = True
                elif a in ("--md", "--markdown"):
                    is_md = True

            is_snippet = (tier == "snippet") or (tier == "detail" and any(x in sub_argv for x in ("-s", "--snippet", "--preview")))
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
                                        "file_uri": engine.to_file_uri(s.get("caller_file", c["symbol"].file_path), line=s.get("line_number")),
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
                                "symbol": {
                                    "name": c["symbol"].name,
                                    "kind": c["symbol"].kind,
                                    "file_path": engine.normalize_workspace_path(c["symbol"].file_path),
                                    "line_number": c["symbol"].line_number,
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

        elif subcmd == "callees":
            targets = [a for a in sub_argv if not a.startswith("-")]
            if not targets:
                print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db callees 'KnowledgeEngine.build_unified_index'", file=sys.stderr)
                return 1
            query_str = targets[0]
            tier = "simple"
            is_json = False
            is_md = False
            limit_val = "auto"
            space_target = None

            for a in sub_argv:
                if a.startswith("--space="):
                    space_target = a.split("=", 1)[1]
                elif a.startswith("--limit="):
                    l_val = a.split("=", 1)[1].strip()
                    if l_val.lower() == "auto":
                        limit_val = "auto"
                    else:
                        try:
                            limit_val = int(l_val)
                        except ValueError:
                            limit_val = "auto"
                elif a in ("--detail", "-d", "--verbose"):
                    tier = "detail"
                elif a in ("--snippet", "-s", "--preview"):
                    tier = "snippet"
                elif a == "--simple":
                    tier = "simple"
                elif a == "--json":
                    is_json = True
                elif a in ("--md", "--markdown"):
                    is_md = True

            is_snippet = (tier == "snippet") or (tier == "detail" and any(x in sub_argv for x in ("-s", "--snippet", "--preview")))
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

        elif subcmd == "impact":
            targets = [a for a in sub_argv if not a.startswith("-")]
            if not targets:
                print("[knowledge-db] 錯誤: 請指定目標符號名稱。例如: python yscb.py knowledge-db impact 'InvertedIndex.patch_incremental' --depth=2", file=sys.stderr)
                return 1
            query_str = targets[0]
            tier = "simple"
            is_json = False
            is_md = False
            limit_val = "auto"
            depth = 2
            space_target = None

            for a in sub_argv:
                if a.startswith("--depth="):
                    try:
                        depth = int(a.split("=", 1)[1])
                    except ValueError:
                        pass
                elif a.startswith("--space="):
                    space_target = a.split("=", 1)[1]
                elif a.startswith("--limit="):
                    l_val = a.split("=", 1)[1].strip()
                    if l_val.lower() == "auto":
                        limit_val = "auto"
                    else:
                        try:
                            limit_val = int(l_val)
                        except ValueError:
                            limit_val = "auto"
                elif a in ("--detail", "-d", "--verbose"):
                    tier = "detail"
                elif a == "--simple":
                    tier = "simple"
                elif a == "--json":
                    is_json = True
                elif a in ("--md", "--markdown"):
                    is_md = True

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

        elif subcmd == "clean":
            targets = [a for a in sub_argv if not a.startswith("-")]
            space_target = targets[0] if targets and "--all" not in sub_argv else None

            engine.clean(space=space_target)
            target_str = f"空間 '{space_target}'" if space_target else "全空間"
            print(f"[knowledge-db] 成功清理 {target_str} 之指紋、Bundle 與倒排索引快取。")
            return 0

        else:
            print(f"[knowledge-db] 未知指令: '{subcmd}'。輸入 -h 或 --help 查看用法。", file=sys.stderr)
            return 1

    except SpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
