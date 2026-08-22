#!/usr/bin/env python3
"""
search_dev_plans.py — 歷史開發計畫與決策記錄 (DR) 檢索工具

用途：結構化檢索 plans_dir (進行中) 與 archive_dir (歸檔) 下的關鍵字與 Decision Records (DR)。
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import re
import argparse
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import get_plans_dir, get_archive_dir, get_module_dir, get_workspace_root

def find_all_plans(plans_dir: Path, archive_dir: Path, year: str = None, month: str = None):
    plans = []
    # 1. 搜尋進行中計畫
    if plans_dir.is_dir():
        for item in plans_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                plans.append(item)

    # 2. 搜尋歷史歸檔計畫 archive_plans/YYYY/MM/
    if archive_dir.is_dir():
        for y in archive_dir.iterdir():
            if y.is_dir() and (year is None or y.name == year):
                for m in y.iterdir():
                    if m.is_dir() and (month is None or m.name == month):
                        for p in m.iterdir():
                            if p.is_dir():
                                plans.append(p)
    return plans

def extract_drs_from_content(content: str) -> list[tuple[str, str]]:
    results = []
    
    # 模式 1: ### DR-01: [標題] 或 ### [REQ:DR-01] 標題
    sections = re.split(r"(?=^###\s+.*DR-)", content, flags=re.MULTILINE)
    for sec in sections:
        header_match = re.match(r"^###\s+([^\n]+)", sec)
        if header_match:
            dr_header = header_match.group(1).strip()
            # 嘗試提取「結論」或「議題」
            summary_match = re.search(r"-\s*\*\*結論\*\*\s*[:：]\s*(.*)", sec)
            if not summary_match:
                summary_match = re.search(r"-\s*\*\*議題\*\*\s*[:：]\s*(.*)", sec)
            
            summary = summary_match.group(1).strip() if summary_match else dr_header
            results.append((dr_header, summary))

    # 模式 2: - **DR-XX (標題)**：內容
    list_matches = re.findall(r"-\s*\*\*([A-Za-z0-9\-_:\[\]]+(?:\s*\([^)]+\))?)\*\*\s*[:：]\s*(.*)", content)
    for dr_id, summary in list_matches:
        if "DR" in dr_id:
            results.append((dr_id, summary.strip()))

    return results

def search_decision_records(plans: list, query: str = None, limit: int = 25):
    print("=" * 90)
    print(f"{'Plan 名稱 / 來源檔案':<40} | {'DR ID / 標題':<22} | {'結論 / 摘要'}")
    print("=" * 90)

    found_count = 0
    seen_keys = set()

    for plan in plans:
        # 遍歷主目錄及子目錄的所有 markdown
        for md_file in sorted(plan.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            drs = extract_drs_from_content(content)
            for dr_id, summary in drs:
                dedup_key = (plan.name, dr_id)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                if query:
                    q_lower = query.lower()
                    if q_lower not in dr_id.lower() and q_lower not in summary.lower() and q_lower not in md_file.name.lower():
                        continue

                rel_src = md_file.relative_to(plan)
                disp_source = f"{plan.name}/{rel_src}" if str(rel_src) != "." else plan.name
                disp_source = disp_source if len(disp_source) <= 38 else disp_source[:35] + "..."
                disp_id = dr_id if len(dr_id) <= 20 else dr_id[:17] + "..."
                disp_summary = summary if len(summary) <= 40 else summary[:37] + "..."

                print(f"{disp_source:<40} | {disp_id:<22} | {disp_summary}")
                found_count += 1
                if found_count >= limit:
                    break
            if found_count >= limit:
                break
        if found_count >= limit:
            break

    print("=" * 90)
    print(f"共找到 {found_count} 筆 Decision Records。")

def search_full_text(plans: list, query: str, limit: int = 20, root: Path = None):
    if root is None:
        root = get_workspace_root(get_module_dir())
    print(f"搜尋關鍵字: \"{query}\" ...")
    print("=" * 90)

    found_count = 0
    for plan in plans:
        for md_file in sorted(plan.rglob("*.md")):
            try:
                lines = md_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                if query.lower() in line.lower():
                    try:
                        rel_path = md_file.relative_to(root)
                    except ValueError:
                        rel_path = md_file
                    print(f"📄 [{rel_path}:L{idx+1}]")
                    start_i = max(0, idx - 1)
                    end_i = min(len(lines), idx + 2)
                    for l_num in range(start_i, end_i):
                        prefix = " > " if l_num == idx else "   "
                        print(f"{prefix}{l_num+1:4d}: {lines[l_num]}")
                    print("-" * 90)
                    found_count += 1
                    if found_count >= limit:
                        break
            if found_count >= limit:
                break
        if found_count >= limit:
            break

    print(f"共找到 {found_count} 筆符合結果。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="檢索 Dev Plans 歷史與決策")
    parser.add_argument("query_pos", nargs="?", default="", help="搜尋關鍵字 (positional)")
    parser.add_argument("-q", "--query", type=str, help="搜尋關鍵字 (與 positional 等效)")
    parser.add_argument("--dr", action="store_true", help="專門檢索 Decision Records (DR)")
    parser.add_argument("--year", type=str, help="限定搜尋年份 (如 2026)")
    parser.add_argument("--month", type=str, help="限定搜尋月份 (如 08)")
    parser.add_argument("--limit", type=int, default=20, help="限制回傳筆數 (預設 20)")

    args = parser.parse_args()
    q = args.query or args.query_pos or ""

    module_dir = get_module_dir()
    plans_dir = get_plans_dir(module_dir)
    archive_dir = get_archive_dir(module_dir)
    workspace_root = get_workspace_root(module_dir)

    if not plans_dir.exists() and not archive_dir.exists():
        print(f"[INFO] 找不到計畫目錄 ({plans_dir})。")
        sys.exit(0)

    all_plans = find_all_plans(plans_dir, archive_dir, year=args.year, month=args.month)

    if args.dr or not q:
        search_decision_records(all_plans, query=q, limit=args.limit)
    else:
        search_full_text(all_plans, query=q, limit=args.limit, root=workspace_root)
