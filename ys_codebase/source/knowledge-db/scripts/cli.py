"""
CLI router entry point for module:knowledge-db.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""

import json
import sys
from typing import Any, Dict, Union

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
import knowledge_db  # noqa: F401
import knowledge_db.config as kdb_config
from knowledge_db.engine import get_engine
from knowledge_db.exceptions import KnowledgeDBError
from knowledge_db.formatter import TerminalStyler
from file_space import FileSpaceNotFoundError


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
    """查看知識庫後台服務、核心索引、AST 水位線、檢索模式、組態與空間游標同步詳盡統計。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "status")
    engine = get_engine()

    try:
        targets = bags.args
        space_target = bags.get_option_value("space") or (targets[0] if targets and not (bags.has_option("all") or bags.has_option("a")) else None)

        st = engine.status(space=space_target)
        if bags.has_option("json"):
            print(json.dumps(dict(st), indent=2, ensure_ascii=False))
            return 0
        styler = TerminalStyler(sys.stdout)
        worker_info = st.get("worker") or {}
        indices_info = st.get("indices") or {}
        bm25_info = indices_info.get("bm25") or {}
        vec_info = indices_info.get("vector") or {}

        print(f"[knowledge-db] 系統狀態摘要 (共 {st['total_spaces']} 個空間):")
        print(f"  - 存儲空間根目錄: {styler.path(st['storage_dir'])}")

        # 1. 後台服務與忙碌探針
        w_running = bool(worker_info.get("running"))
        w_busy_ms = int(worker_info.get("busy_elapsed_ms", 0) or 0)
        w_phase = worker_info.get("phase", "idle")
        w_prog = worker_info.get("progress", "")
        if w_running:
            w_run_str = styler.symbol(f"運行中 (knowledge-db-worker, PID: {worker_info.get('pid') or 'in-process'})")
        else:
            w_run_str = styler.line("未啟動 (Standalone 前台模式)")
        if w_busy_ms > 0:
            prog_suffix = f" | {w_prog}" if w_prog else ""
            w_busy_str = styler.warn(f"忙碌中 (已運行 {w_busy_ms} ms | 階段: {w_phase}{prog_suffix})")
        else:
            w_busy_str = styler.symbol("空閒 (0 ms)")
        print(f"  - 後台常駐服務  : {w_run_str} | 探針狀態: {w_busy_str}")

        # 2. 生效檢索模式與原因
        ret_mode = st.get("retrieval_mode", "lexical_bm25")
        ret_reason = st.get("retrieval_reason", "")
        if str(ret_mode).startswith("hybrid_rrf"):
            mode_str = styler.symbol(f"{ret_mode} — {ret_reason}")
        else:
            mode_str = styler.warn(f"{ret_mode} — {ret_reason}")
        print(f"  - 當前檢索模式  : {mode_str}")

        # 3. 核心索引與 AST 水位指標
        ast_gen = st.get("ast_generation", 0)
        acked_ast_gen = st.get("acked_ast_generation", 0)
        if st.get("has_unified_index"):
            unified_str = styler.symbol(
                f"已建立 ({bm25_info.get('symbol_count', 0)} 個符號, "
                f"{bm25_info.get('term_count', 0)} 個詞條, "
                f"AST gen {acked_ast_gen}/{ast_gen}, "
                f"{bm25_info.get('size_kb', 0.0)} KB)"
            )
        else:
            unified_str = styler.warn("未建立")
        print(f"  - 全域倒排索引  : {unified_str}")

        vec_status = vec_info.get("status", "missing")
        emb_cnt = vec_info.get("embedded_count", 0)
        tot_cnt = vec_info.get("total_symbols", 0)
        cov_pct = vec_info.get("coverage_pct", 0.0)
        miss_cnt = vec_info.get("missing_count", 0)
        vec_dim = vec_info.get("dimension", 512)
        vec_kb = vec_info.get("size_kb", 0.0)

        if not st.get("enable_vector_search"):
            vec_str = styler.line("已停用 (依組態停用向量檢索)")
        elif vec_status == "ready" or (st.get("has_vector_index") and miss_cnt == 0 and emb_cnt > 0):
            vec_str = styler.symbol(
                f"已建立 ({emb_cnt}/{tot_cnt} 向量, 覆蓋率 {cov_pct}%, 維度 {vec_dim}, {vec_kb} KB)"
            )
        elif st.get("has_vector_index") and emb_cnt > 0:
            vec_str = styler.warn(
                f"部分建立/同步中 ({emb_cnt}/{tot_cnt} 向量, 覆蓋率 {cov_pct}%, 待補 {miss_cnt} 個, 維度 {vec_dim}, {vec_kb} KB)"
            )
        else:
            vec_str = styler.warn(f"未建立 (0/{tot_cnt} 向量, 待補 {miss_cnt} 個)")
        print(f"  - 向量特徵索引  : {vec_str}")

        # 4. 向量模型與執行期組態
        if st.get("model_downloaded"):
            model_str = styler.symbol(f"已下載 ({st.get('embedding_model')})")
        elif w_running and st.get("enable_vector_search"):
            model_str = styler.warn(f"未下載 ({st.get('embedding_model')} — 後台 Worker 將自動下載)")
        else:
            model_str = styler.warn(f"未下載 ({st.get('embedding_model')} — 離線時自動降級 BM25)")
        print(f"  - 向量模型權重  : {model_str}")
        print(
            f"  - 執行期組態參數: 容差等待/熔斷={st.get('jit_vector_timeout_ms', 3000)} ms, "
            f"微批次大小={st.get('vector_batch_size', 32)}, "
            f"執行緒預算={st.get('max_threads', 1)}"
        )

        print("-" * 80)
        for name, sp in st["spaces"].items():
            pat_str = f" [patterns: {', '.join(sp['file_patterns'])}]" if sp.get("file_patterns") else " [all files]"
            is_idx = sp.get("has_index") or st.get("has_unified_index")
            idx_str = styler.symbol("已建立") if is_idx else styler.warn("未建立")
            head_gen = sp.get("head_generation", 0)
            acked_gen = sp.get("acked_generation", 0)
            sync_str = (
                styler.symbol(f"已對齊 (gen {acked_gen}/{head_gen})")
                if sp.get("in_sync")
                else styler.warn(f"待同步 (acked {acked_gen} / head {head_gen})")
            )
            print(f"  - 空間: {styler.path(name)} (來源: {sp.get('origin', 'unknown')}, 權重: {sp.get('weight', 1.0)}){pat_str}")
            if sp.get("description"):
                print(f"    說明: {sp['description']}")
            print(
                f"    來源目錄數: {sp.get('include_count', 0)}, "
                f"納管檔案: {sp.get('cached_files', 0)} 檔, "
                f"倒排索引: {idx_str}, "
                f"游標水位: {sync_str}"
            )
        print("-" * 80)
        return 0
    except FileSpaceNotFoundError as e:
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
        export_arg = bags.get_option_value("export")

        indices = engine.build_index(space=space_target, force=force, interactive=True, export_path=export_arg)
        print(f"[knowledge-db] 倒排索引建置完成 (共 {len(indices)} 個空間):")
        for sp_name, idx in indices.items():
            print(f"  - 空間 '{sp_name}': {idx.doc_count} 篇文檔符號，{len(idx.index)} 個 Term 索引詞")
        if export_arg:
            print(f"  - 語意 Bundle 已導出至: {export_arg}")
        return 0
    except FileSpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def model(cmd_bags: Any) -> int:
    """向量模型管理群組分發器。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "model")
    sub_cmd = bags.args[0] if bags.args else "status"
    if sub_cmd == "status":
        sub_bags = CmdBags(raw_cmd=bags.raw_cmd, command="status", args=bags.args[1:], options=bags.options)
        return model_status(sub_bags)
    elif sub_cmd in ("download", "pull"):
        sub_bags = CmdBags(raw_cmd=bags.raw_cmd, command="download", args=bags.args[1:], options=bags.options)
        return model_download(sub_bags)
    else:
        print(f"[knowledge-db] 未知 model 子指令: '{sub_cmd}'。可用子指令: status, download", file=sys.stderr)
        return 1


def model_status(cmd_bags: Any) -> int:
    """檢視本地向量模型權重快取目錄、檔案狀態與維度。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "model status")
    engine = get_engine()
    try:
        st = engine.model_status()
        if bags.has_option("json"):
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return 0

        styler = TerminalStyler(sys.stdout)
        print("[knowledge-db] 向量推論模型狀態:")
        print(f"  - 模型名稱: {styler.bold(st['model_name'])}")
        print(f"  - 快取目錄: {styler.path(st['cache_dir'])}")
        dl_str = styler.symbol("已就緒") if st.get("is_downloaded") else styler.warn("未下載")
        print(f"  - 本地權重: {dl_str}")
        av_str = styler.symbol("可用") if st.get("is_available") else styler.warn("不可用 (將降級至 BM25)")
        print(f"  - 服務狀態: {av_str}")
        print(f"  - 向量維度: {st['dimension']}")
        return 0
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def model_download(cmd_bags: Any) -> int:
    """顯式下載 FastEmbed 向量模型權重至本地快取。"""
    guard_dispatch("knowledge-db")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "model download")
    engine = get_engine()
    try:
        force = bags.has_option("force") or bags.has_option("f")
        print(f"[knowledge-db] 開始準備下載/載入向量模型 '{engine.embedding_service.model_name}' (force={force})...")
        success = engine.model_download(force=force)
        if success:
            st = engine.model_status()
            print(f"[knowledge-db] 向量模型下載成功，已就緒可用 (維度: {st['dimension']})。")
            return 0
        else:
            print("[knowledge-db] 向量模型下載未完成。", file=sys.stderr)
            return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 下載失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def search(cmd_bags: Any) -> int:
    """對全空間或指定空間符號進行多欄位加權 BM25 與向量混合語意檢索。"""
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
        space_filter = bags.get_option_value("space")
        kind_filter = [bags.get_option_value("kind")] if bags.get_option_value("kind") else None
        lang_filter = [bags.get_option_value("lang")] if bags.get_option_value("lang") else None
        ftype_filter = bags.get_option_value("ftype")
        lexical_only = bags.has_option("lexical-only")

        opts = _parse_common_display_options(bags)
        tier = opts["tier"]
        limit_val = opts["limit_val"]
        is_json = opts["is_json"]
        is_md = opts["is_md"]
        file_uri = opts["file_uri"]
        is_snippet = opts["is_snippet"]
        detail_mode = opts["detail_mode"]
        if limit_val == "auto":
            fetch_limit = 10 if (is_json and tier == "snippet") else 50
        else:
            fetch_limit = max(1, int(limit_val))

        max_snippet_lines = 40
        msl_opt = bags.get_option_value("max-snippet-lines")
        if msl_opt:
            try:
                max_snippet_lines = max(5, int(str(msl_opt).strip()))
            except ValueError:
                max_snippet_lines = 40

        def _cap_json_snippet(cs: Any) -> Dict[str, Any]:
            if not cs or not getattr(cs, "lines", None):
                return {}
            raw_lines = cs.lines
            if tier == "snippet" and len(raw_lines) > max_snippet_lines:
                kept = raw_lines[:max_snippet_lines]
                s_ln = kept[0][0]
                e_ln = kept[-1][0]
                full_end = getattr(cs, "end_line", raw_lines[-1][0])
                omitted_count = len(raw_lines) - max_snippet_lines
                if kdb_config.is_agents_workflow_installed():
                    try:
                        from core import locale as core_locale
                        trunc_suffix = core_locale.t(
                            "cli.search.snippet_truncated_hint",
                            module="knowledge-db",
                            omitted=omitted_count,
                            start_line=cs.start_line,
                            end_line=full_end,
                        )
                    except Exception:
                        trunc_suffix = (
                            f"\n... [truncated {omitted_count} lines; "
                            f"target spans lines {cs.start_line}-{full_end}, use native file reader with line range to view]"
                        )
                else:
                    trunc_suffix = (
                        f"\n... [truncated {omitted_count} lines; "
                        f"target spans lines {cs.start_line}-{full_end}]"
                    )
                code_str = "\n".join(txt for _, txt in kept) + trunc_suffix
                return {
                    "code": code_str,
                    "code_lines": [s_ln, e_ln],
                    "full_code_lines": [cs.start_line, full_end],
                    "truncated": True,
                }
            return {
                "code": cs.get_raw_code(),
                "code_lines": [cs.start_line, cs.end_line],
            }

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
            adaptive_limit=(not is_json and limit_val == "auto"),
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
                        "spaces": getattr(res, "spaces", []),
                        "items": [
                            {
                                "id": itm.symbol.id,
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                "matched_terms": getattr(itm, "matched_terms", []),
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
                        **({"file_uri": engine.to_file_uri(res.file_path, line=res.items[0].symbol.line_number if res.items else None)} if file_uri else {}),
                        "total_score": round(res.total_score, 2),
                        "language": res.language,
                        "items": [
                            {
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                **({"signature": itm.symbol.signature} if itm.symbol.signature else {}),
                                **({"summary": itm.snippet or (itm.code_snippet.docstring_summary if itm.code_snippet else "")} if (itm.snippet or (itm.code_snippet and itm.code_snippet.docstring_summary)) else {}),
                                **_cap_json_snippet(itm.code_snippet),
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
                        **({"file_uri": engine.to_file_uri(res.file_path, line=res.items[0].symbol.line_number if res.items else None)} if file_uri else {}),
                        "total_score": round(res.total_score, 2),
                        "language": res.language,
                        "items": [
                            {
                                "name": itm.symbol.name,
                                "kind": itm.symbol.kind,
                                "line_number": itm.symbol.line_number,
                                "end_line": itm.symbol.end_line,
                                "score": round(itm.score, 2),
                                **({"signature": itm.symbol.signature} if itm.symbol.signature else {}),
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
            file_uri=file_uri,
        )
        print(formatted_output)
        return 0
    except FileSpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1


def _parse_common_display_options(bags: CmdBags) -> Dict[str, Any]:
    """解析查詢命令共用之 tier / limit / json / md 顯示選項。"""
    tier = "auto"
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
        l_val = str(l_opt).strip()
        if l_val.lower() == "auto":
            limit_val = "auto"
        else:
            try:
                limit_val = int(l_val)
            except ValueError:
                limit_val = "auto"

    is_snippet = (tier in ("snippet", "detail")) or bags.has_option("s") or bags.has_option("snippet") or bags.has_option("preview")
    return {
        "tier": tier,
        "is_json": is_json,
        "is_md": is_md,
        "file_uri": file_uri,
        "limit_val": limit_val,
        "is_snippet": is_snippet,
        "detail_mode": "detail" if tier == "detail" else ("simple" if tier == "simple" else "auto"),
        "fmt_type": "md" if is_md else "text",
    }


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
    except FileSpaceNotFoundError as e:
        print(f"[knowledge-db] 空間不存在: {e}", file=sys.stderr)
        return 1
    except KnowledgeDBError as e:
        print(f"[knowledge-db] 操作失敗: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[knowledge-db] 執行異常: {e}", file=sys.stderr)
        return 1
