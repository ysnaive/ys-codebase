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
        print("  python yscb.py knowledge-db index [space | --all] 建立/更新空間倒排索引快取")
        print("  python yscb.py knowledge-db search <query> [--snippet|-s] [--detail|-d] [--json] 多欄位 BM25 語意檢索")
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
                print("[knowledge-db] 錯誤: 請提供查詢字串 (例: python yscb.py knowledge-db search PIDController)", file=sys.stderr)
                return 1

            query_str = " ".join(queries)
            space_filter = None
            kind_filter = None
            lang_filter = None
            ftype_filter = None
            limit = 10
            is_detail = False
            is_snippet = False
            is_json = False
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
                    try:
                        limit = int(a.split("=", 1)[1])
                    except ValueError:
                        pass
                elif a in ("--detail", "-d", "--verbose"):
                    is_detail = True
                elif a in ("--snippet", "-s", "--preview"):
                    is_snippet = True
                elif a == "--json":
                    is_json = True

            results = engine.search(
                query=query_str,
                space=space_filter,
                kinds=kind_filter,
                languages=lang_filter,
                ftypes=ftype_filter,
                limit=limit,
                snippet=is_snippet,
                auto_rebuild=not no_auto,
            )

            if is_json:
                data = [
                    res.to_dict() if hasattr(res, "to_dict") else res
                    for res in results
                ]
                # 正規化路徑與注入 file_uri
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and "file_path" in entry:
                            f_path = entry["file_path"]
                            entry["file_path"] = engine.normalize_workspace_path(f_path)
                            entry["file_uri"] = engine.to_file_uri(f_path)
                            if "items" in entry and isinstance(entry["items"], list):
                                for item in entry["items"]:
                                    if isinstance(item, dict) and "symbol" in item and isinstance(item["symbol"], dict):
                                        sym_dict = item["symbol"]
                                        s_line = sym_dict.get("line_number")
                                        s_file = sym_dict.get("file_path", f_path)
                                        item["file_uri"] = engine.to_file_uri(s_file, line=s_line)
                print(json.dumps({"query": query_str, "total": len(results), "results": data}, indent=2, ensure_ascii=False))
                return 0

            if not results:
                print(f"[knowledge-db] 檢索查詢: '{query_str}' (未找到符合的結果)")
                return 0

            # 樹狀階層預覽輸出 (FR-06)
            if is_snippet:
                print(f"[knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 個檔案節點，預覽模式):")
                print("=" * 85)
                for rank, res in enumerate(results, start=1):
                    first_sym = res.items[0].symbol if res.items else None
                    first_line = first_sym.line_number if first_sym else None
                    first_end = first_sym.end_line if first_sym else None
                    file_link = engine.format_file_link(res.file_path, line=first_line, end_line=first_end)
                    print(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} ({len(res.items)} 個命中項目, {res.language})")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        print(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {sym.kind.upper()}: {sym.name} ({line_range})")
                        if sym.signature:
                            print(f"  {pipe}   簽名: {sym.signature}")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            print(f"  {pipe}   摘要: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            print(f"  {pipe}   摘要: {itm.snippet}")
                        if itm.code_snippet and itm.code_snippet.lines:
                            print(f"  {pipe}   代碼切片 ({line_range}):")
                            print(itm.code_snippet.format_text(prefix=f"  {pipe}     "))
                    print("-" * 85)
                return 0

            if is_detail:
                print(f"[knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 個檔案節點，詳細模式):")
                print("=" * 85)
                for rank, res in enumerate(results, start=1):
                    first_sym = res.items[0].symbol if res.items else None
                    first_line = first_sym.line_number if first_sym else None
                    first_end = first_sym.end_line if first_sym else None
                    file_link = engine.format_file_link(res.file_path, line=first_line, end_line=first_end)
                    print(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} ({len(res.items)} 個命中項目, {res.language})")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        print(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {sym.kind.upper()}: {sym.name} ({line_range})")
                        if sym.signature:
                            print(f"  {pipe}   簽名: {sym.signature}")
                        if itm.snippet:
                            print(f"  {pipe}   說明: {itm.snippet}")
                        if itm.matched_terms:
                            print(f"  {pipe}   命中詞: {', '.join(itm.matched_terms)}")
                    print("-" * 85)
                return 0

            # 簡易模式 (預設極簡樹狀排版)
            print(f"[knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 個檔案節點):")
            for rank, res in enumerate(results, start=1):
                if len(res.items) == 1:
                    sym = res.items[0].symbol
                    file_link = engine.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                    print(f"#{rank:02d} {file_link} ({sym.kind}:{sym.name}) [{res.total_score:05.2f}]")
                else:
                    first_sym = res.items[0].symbol if res.items else None
                    first_line = first_sym.line_number if first_sym else None
                    first_end = first_sym.end_line if first_sym else None
                    file_link = engine.format_file_link(res.file_path, line=first_line, end_line=first_end)
                    print(f"#{rank:02d} {file_link} (總分: {res.total_score:05.2f}, {len(res.items)} 項命中):")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        sym = itm.symbol
                        sym_link = engine.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                        print(f"  {branch} #{rank:02d}.{itm_idx} {sym_link} ({sym.kind}:{sym.name}) [{itm.score:05.2f}]")
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
