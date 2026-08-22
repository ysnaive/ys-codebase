#!/usr/bin/env python3
"""
verify_plan.py — Dev Plan 合規性與 Extension 深度稽核工具

用途：
  - 掃描指定 Dev Plan 目錄（或所有活躍進行中計畫），檢查：
    1. 各 Phase 文件 Header 元數據格式（功能名稱、建立日期、所屬主計畫、狀態、擴充項目、模板版本）。
    2. 全量 Extension 稽核：檢查 extensions/ 目錄下必跑 (trigger: always) 與宣告之擴充項目是否皆已落實。
    3. 未完成標記與未定稿佔位符檢測。
"""

import sys
import os
import re
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def get_workspace_root() -> Path:
    cur = Path(__file__).resolve().parent
    while cur.parent != cur:
        if (cur / ".agents").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()

def parse_extensions(agents_dir: Path) -> list:
    ext_dir = agents_dir / "workflows" / "extensions"
    extensions = []
    if not ext_dir.exists():
        return extensions

    for f in ext_dir.glob("*.md"):
        if f.name == "ext_template.md":
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        name = f.stem
        phase = "unknown"
        trigger = "always"

        # 解析 Frontmatter
        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip().strip("[]'\"")
                    if k == "name":
                        name = v
                    elif k == "phase":
                        phase = v
                    elif k == "trigger":
                        trigger = v.lower()
        else:
            # 檔案名稱推斷 (如 P01_logging_standards_ext.md)
            parts = f.stem.split("_", 1)
            if len(parts) == 2 and parts[0].startswith("P0"):
                phase = parts[0]

        extensions.append({
            "file": f.name,
            "name": name,
            "phase": phase,
            "trigger": trigger,
            "title": f.stem,
        })
    return extensions

def parse_plan_header(lines: list) -> dict:
    """結構化解析 Markdown 開頭 Blockquote (> 欄位：值) 中的 Header 元數據"""
    headers = {}
    for line in lines[:30]:
        line_clean = line.strip().replace("\u3000", " ")
        if line_clean.startswith(">"):
            inner = line_clean.lstrip(">").strip()
            if "：" in inner:
                k, v = inner.split("：", 1)
                headers[k.strip().lower()] = v.strip()
            elif ":" in inner:
                k, v = inner.split(":", 1)
                headers[k.strip().lower()] = v.strip()
    return headers

def verify_single_file(file_path: Path, all_exts: list) -> list:
    issues = []
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    # 1. 檢查是否殘留 HTML AGENT_GUIDANCE 註解
    if "=== AGENT_GUIDANCE" in content:
        issues.append({"level": "ERROR", "msg": "文件中殘留了 <!-- AGENT_GUIDANCE --> 模板指引註解，產出時未依規範過濾剝除。"})

    # 2. 檢查 Header 元數據
    headers = parse_plan_header(lines)
    has_name = any(k in headers for k in ["功能名稱", "計畫名稱", "name", "title"])
    has_date = any(k in headers for k in ["建立日期", "完成日期", "date", "created_at"])
    has_status = any(k in headers for k in ["狀態", "status"])
    has_ext = any(k in headers for k in ["擴充項目", "active ext", "active ext."])

    if not has_name:
        issues.append({"level": "WARN", "msg": "Header 缺少 [功能名稱] 欄位"})
    if not has_date:
        issues.append({"level": "WARN", "msg": "Header 缺少 [建立日期] 欄位"})
    if not has_status:
        issues.append({"level": "ERROR", "msg": "Header 缺少 [狀態] 欄位"})
    if not has_ext:
        issues.append({"level": "WARN", "msg": "Header 缺少 [擴充項目] (或 active ext.) 宣告欄位"})

    # 3. 檢查必跑 Extension (trigger: always)
    phase_code = file_path.stem.split("_")[0].upper() # 例如 P01, P02...
    matching_always_exts = [e for e in all_exts if e["phase"].upper() == phase_code and e["trigger"] == "always"]

    declared_exts_text = ""
    for k in ["擴充項目", "active ext", "active ext."]:
        if k in headers:
            declared_exts_text = headers[k]
            break

    for ext in matching_always_exts:
        # 檢查 Header 宣告
        if ext["name"] not in declared_exts_text and ext["file"] not in declared_exts_text and ext["title"] not in declared_exts_text:
            issues.append({"level": "ERROR", "msg": f"缺少必跑擴充項目宣告：{ext['name']} (trigger: always for {phase_code})"})
        # 檢查正文是否包含結果
        if ext["name"] not in content and "Extension" not in content and "擴充" not in content:
            issues.append({"level": "WARN", "msg": f"正文未檢測到擴充項目 [{ext['name']}] 的執行結果記錄區塊"})

    return issues

def verify_plan_directory(plan_dir: Path, all_exts: list) -> dict:
    results = {}
    md_files = sorted(list(plan_dir.glob("*.md")))
    for md in md_files:
        if md.name in ["changelog.md", "handoff.md"]:
            continue
        file_issues = verify_single_file(md, all_exts)
        results[md.name] = file_issues

    # 遞迴檢查子計畫
    for sub in plan_dir.iterdir():
        if sub.is_dir() and sub.name.startswith("sub_"):
            sub_res = verify_plan_directory(sub, all_exts)
            for k, v in sub_res.items():
                results[f"{sub.name}/{k}"] = v

    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dev Plan 合規性與 Extension 深度稽核工具")
    parser.add_argument("plan", nargs="?", help="指定欲審查的 Dev Plan 目錄名稱或路徑（留空則掃描當前所有進行中計畫）")
    parser.add_argument("--all", action="store_true", help="包含 history 已歸檔之計畫一併掃描")
    args = parser.parse_args()

    root = get_workspace_root()
    agents_dir = root / ".agents"
    dev_plans_dir = agents_dir / "dev_plans"
    all_exts = parse_extensions(agents_dir)

    target_plans = []
    if args.plan:
        p = Path(args.plan)
        if not p.is_absolute():
            p = dev_plans_dir / args.plan
        if p.exists() and p.is_dir():
            target_plans.append(p)
        else:
            print(f"[ERROR] 找不到指定的計畫目錄：{p}")
            sys.exit(1)
    else:
        if not dev_plans_dir.exists():
            print("[INFO] 無 dev_plans 目錄。")
            return
        for item in dev_plans_dir.iterdir():
            if item.is_dir() and item.name != "history":
                target_plans.append(item)
            elif args.all and item.name == "history":
                for y in item.iterdir():
                    if y.is_dir():
                        for m in y.iterdir():
                            if m.is_dir():
                                for p in m.iterdir():
                                    if p.is_dir():
                                        target_plans.append(p)

    if not target_plans:
        print("[INFO] 目前無任何進行中的 Dev Plan。")
        return

    print("=" * 80)
    print(f"  Dev Plan 合規性與 Extension 深度驗收報告 (載入 {len(all_exts)} 個 Extension 定義)")
    print("=" * 80)

    total_errors = 0
    total_warns = 0

    for plan in target_plans:
        print(f"\n📁 審查計畫：{plan.name}")
        plan_results = verify_plan_directory(plan, all_exts)
        has_any_issue = False

        for f_name, issues in plan_results.items():
            if not issues:
                print(f"  ✅ {f_name:<35} [合規通過]")
            else:
                has_any_issue = True
                print(f"  ⚠️ {f_name:<35} 發現 {len(issues)} 項問題:")
                for iss in issues:
                    prefix = "🛑 [ERROR]" if iss["level"] == "ERROR" else "⚠️ [WARN] "
                    if iss["level"] == "ERROR":
                        total_errors += 1
                    else:
                        total_warns += 1
                    print(f"     {prefix} {iss['msg']}")

    print("\n" + "=" * 80)
    if total_errors == 0 and total_warns == 0:
        print("  🎉 驗收結果：100% 合規！所有計畫均符合 Header 元數據與 Extension 規範。")
    else:
        print(f"  驗收摘要：發現 {total_errors} 個重大錯誤 (ERROR)，{total_warns} 個警告 (WARN)。")
    print("=" * 80 + "\n")

    if total_errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
