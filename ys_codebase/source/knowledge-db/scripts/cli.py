"""
CLI router entry point for module:knowledge-db.
"""

import os
import sys
from typing import List

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

from knowledge_db.bundler import SemanticBundler
from knowledge_db.exceptions import KnowledgeDBError, SpaceNotFoundError
from knowledge_db.retrieval import BM25Engine, InvertedIndex, QueryFilter
from knowledge_db.scanner import FingerprintScanner
from knowledge_db.space import SpaceManager
from knowledge_db.thesaurus import ThesaurusEngine
from knowledge_db.tokenizer import CodeTokenizer


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[knowledge-db] YS-Codebase Knowledge Database & Semantic Retrieval")
        print("Usage:")
        print("  python yscb.py knowledge-db status               列出所有註冊空間與狀態")
        print("  python yscb.py knowledge-db scan [space | --all] 執行增量指紋掃描")
        print("  python yscb.py knowledge-db bundle [space|--all] 打包空間符號為 SemanticBundle")
        print("  python yscb.py knowledge-db search <query>       多欄位 BM25 語意檢索")
        return 0

    subcmd = argv[0]
    sub_argv = argv[1:]

    space_mgr = SpaceManager()
    scanner = FingerprintScanner(space_mgr)
    bundler = SemanticBundler(space_mgr, scanner=scanner)

    if subcmd == "status":
        spaces = space_mgr.load_spaces()
        thesaurus = space_mgr.load_thesaurus()
        print(f"[knowledge-db] 已註冊空間清單 (共 {len(spaces)} 個空間，{len(thesaurus)} 組同義詞):")
        print("-" * 75)
        for name, sp in spaces.items():
            fps = scanner.load_fingerprints(name)
            pat_str = f" [patterns: {', '.join(sp.file_patterns)}]" if sp.file_patterns else " [all files]"
            print(f"  - 空間: {name} (來源: {sp.origin}){pat_str}")
            if sp.description:
                print(f"    說明: {sp.description}")
            print(f"    Include ({len(sp.include)}): {', '.join(sp.include)}")
            print(f"    指紋快取檔案數: {len(fps)}")
        print("-" * 75)
        return 0

    elif subcmd == "scan":
        force = "--force" in sub_argv
        targets = [a for a in sub_argv if not a.startswith("-")]

        if "--all" in sub_argv or not targets:
            results = scanner.scan_all_spaces(force=force)
            print(f"[knowledge-db] 全空間聯集增量掃描完成 (共 {len(results)} 個空間):")
            for sp_name, diff in results.items():
                print(
                    f"  - {sp_name}: Added={len(diff.added)}, Modified={len(diff.modified)}, "
                    f"Deleted={len(diff.deleted)}, Unchanged={len(diff.unchanged)}"
                )
            return 0
        else:
            sp_name = targets[0]
            try:
                sp_config = space_mgr.get_space(sp_name)
                diff = scanner.scan_space(sp_config, force=force)
                print(f"[knowledge-db] 空間 '{sp_name}' 增量掃描完成:")
                print(
                    f"  - Added: {len(diff.added)}, Modified: {len(diff.modified)}, "
                    f"Deleted: {len(diff.deleted)}, Unchanged: {len(diff.unchanged)}"
                )
                return 0
            except SpaceNotFoundError as e:
                print(f"[knowledge-db] 錯誤: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"[knowledge-db] 掃描失敗: {e}", file=sys.stderr)
                return 1

    elif subcmd == "bundle":
        targets = [a for a in sub_argv if not a.startswith("-")]
        out_arg = None
        for a in sub_argv:
            if a.startswith("--output="):
                out_arg = a.split("=", 1)[1]

        if "--all" in sub_argv or not targets:
            spaces = space_mgr.get_union_spaces()
            print(f"[knowledge-db] 開始為全空間聯集 ({len(spaces)} 個空間) 進行語意打包...")
            for sp in spaces:
                b = bundler.bundle_space(sp)
                out_path = bundler.export_bundle(b, target_path=out_arg)
                print(f"  - 空間 '{sp.name}': 打包 {len(b.symbols)} 個符號 ➔ {out_path}")
            return 0
        else:
            sp_name = targets[0]
            try:
                sp_config = space_mgr.get_space(sp_name)
                print(f"[knowledge-db] 開始為空間 '{sp_name}' 進行語意打包...")
                b = bundler.bundle_space(sp_config)
                out_path = bundler.export_bundle(b, target_path=out_arg)
                print(f"[knowledge-db] 成功打包 {len(b.symbols)} 個符號 ➔ {out_path}")
                return 0
            except SpaceNotFoundError as e:
                print(f"[knowledge-db] 錯誤: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"[knowledge-db] 打包失敗: {e}", file=sys.stderr)
                return 1

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
                space_filter = [a.split("=", 1)[1]]
            elif a.startswith("--kind="):
                kind_filter = [a.split("=", 1)[1]]
            elif a.startswith("--lang="):
                lang_filter = [a.split("=", 1)[1]]
            elif a.startswith("--limit="):
                try:
                    limit = int(a.split("=", 1)[1])
                except ValueError:
                    pass

        # 聚合空間符號並構建檢索倒排索引
        spaces = space_mgr.get_union_spaces()
        all_symbols = []
        for sp in spaces:
            if space_filter and sp.name not in space_filter:
                continue
            b = bundler.bundle_space(sp)
            all_symbols.extend(b.symbols)

        if not all_symbols:
            print(f"[knowledge-db] 空間內無有效符號或未找到符合條件之符號。")
            return 0

        thesaurus_groups = space_mgr.load_thesaurus()
        tokenizer = CodeTokenizer()
        thesaurus = ThesaurusEngine(thesaurus_groups)
        index = InvertedIndex(space_name="union")
        index.build(all_symbols, tokenizer=tokenizer)

        engine = BM25Engine(tokenizer=tokenizer, thesaurus=thesaurus)
        flt = QueryFilter(
            spaces=space_filter,
            languages=lang_filter,
            kinds=kind_filter,
            limit=limit,
        )

        results = engine.search(query_str, index=index, filter_cfg=flt)

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

    else:
        print(f"[knowledge-db] 未知指令: '{subcmd}'。輸入 -h 或 --help 查看用法。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
