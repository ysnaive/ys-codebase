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

from knowledge_db.exceptions import KnowledgeDBError, SpaceNotFoundError
from knowledge_db.scanner import FingerprintScanner
from knowledge_db.space import SpaceManager


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("[knowledge-db] YS-Codebase Knowledge Database & Semantic Retrieval")
        print("Usage:")
        print("  python yscb.py knowledge-db status               列出所有註冊空間與狀態")
        print("  python yscb.py knowledge-db scan [space | --all] 執行增量指紋掃描")
        return 0

    subcmd = argv[0]
    sub_argv = argv[1:]

    space_mgr = SpaceManager()
    scanner = FingerprintScanner(space_mgr)

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

    else:
        print(f"[knowledge-db] 未知指令: '{subcmd}'。輸入 -h 或 --help 查看用法。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
