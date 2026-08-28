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
        print("  python yscb.py knowledge-db search <query>       多欄位 BM25 語意檢索")
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
                pat_str = f" [patterns: {', '.join(sp['file_patterns'])}]" if sp['file_patterns'] else " [all files]"
                idx_str = "已建立" if sp['has_index'] else "未建立"
                print(f"  - 空間: {name} (來源: {sp['origin']}){pat_str}")
                if sp["description"]:
                    print(f"    說明: {sp['description']}")
                print(f"    來源目錄數: {sp['include_count']}, 指紋快取檔案: {sp['cached_files']} 檔, 倒排索引: {idx_str}")
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
            limit = 10

            for a in sub_argv:
                if a.startswith("--space="):
                    space_filter = a.split("=", 1)[1]
                elif a.startswith("--kind="):
                    kind_filter = [a.split("=", 1)[1]]
                elif a.startswith("--lang="):
                    lang_filter = [a.split("=", 1)[1]]
                elif a.startswith("--limit="):
                    try:
                        limit = int(a.split("=", 1)[1])
                    except ValueError:
                        pass

            results = engine.search(
                query=query_str,
                space=space_filter,
                kinds=kind_filter,
                languages=lang_filter,
                limit=limit,
            )

            print(f"[knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 筆結果):")
            print("=" * 85)
            for rank, res in enumerate(results, start=1):
                sym = res.symbol
                print(f"#{rank:02d} [{res.score:05.2f}] {sym.kind.upper()}: {sym.name} ({sym.language})")
                print(f"     檔案: {sym.file_path}:{sym.line_number}")
                if sym.signature:
                    print(f"     簽名: {sym.signature}")
                if res.snippet:
                    print(f"     說明: {res.snippet}")
                print(f"     命中詞: {', '.join(res.matched_terms)}")
                print("-" * 85)
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
