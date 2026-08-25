#!/usr/bin/env python3
"""
verify_plan.py — Dev Plan 合規性與 Extension 深度稽核工具

用途：
  - 掃描指定 Dev Plan 目錄（或所有活躍進行中計畫），檢查：
    1. 各 Phase 文件 Header 元數據格式（功能名稱、建立日期、所屬主計畫、狀態、擴充項目、模板版本）。
    2. 全量 Extension 稽核：檢查 sop_ext:// / extensions/ 目錄下必跑 (trigger: always) 與宣告之擴充項目是否皆已落實。
    3. P01 / FT_plan 之 Extension 適用性判定矩陣。
    4. 未完成標記與未定稿佔位符檢測。
"""

import sys
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import get_plans_dir, get_archive_dir, get_module_dir, get_extensions_dir, get_workspace_root
from ext_registry import ExtensionRegistry

try:
    from yscb_core import ProjectContext
except ImportError:
    core_scripts = MODULE_DIR.parent / "core" / "scripts"
    if core_scripts.is_dir() and str(core_scripts) not in sys.path:
        sys.path.insert(0, str(core_scripts))
    from context import ProjectContext


def parse_extensions(module_dir: Path, workspace_root: Optional[Path] = None) -> list:
    """透過 ExtensionRegistry 掃描所有可用 Extension（含各自宣告之 phase 適用範圍 Token 集合）"""
    registry = ExtensionRegistry.discover_all(ProjectContext)
    extensions = []
    for name, info in sorted(registry.items()):
        doc_p = info.get("doc_path")
        extensions.append({
            "file": doc_p.name if doc_p else f"{name}.md",
            "name": name,
            "phase": info.get("phase") or {"ALL"},
            "trigger": info.get("trigger", "on_demand"),
            "title": name,
            "script_path": info.get("script_path"),
            "source_type": info.get("source_type", "module"),
            "module_name": info.get("module_name"),
        })
    return extensions


def compute_phase_code(file_name: str) -> str:
    """
    依 Dev Plan 產出物檔名推導標準 Phase Token，供比對 Extension manifest/frontmatter 宣告之 phase 欄位。
    例：P01_requirements_spec.md -> "P01"；FT_plan.md -> "FT_PLAN"（不可用單純 stem.split("_")[0] 取得，
    否則會誤判為 "FT" 而永遠無法比對到 dogfooding_pipeline_ext.md 等宣告的 "FT_plan" Token）。
    """
    stem = Path(file_name).stem
    if stem == "FT_plan":
        return "FT_PLAN"
    return stem.split("_")[0].upper()


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

    # 2.1 檢查 Phase 1 / FT_plan 是否有 Extension 適用性判定矩陣
    if file_path.name in ["P01_requirements_spec.md", "FT_plan.md"]:
        has_matrix = any(term in content for term in [
            "專案擴充特化判定矩陣",
            "擴充特化判定矩陣",
            "Extension Specialization Matrix",
            "Extension Matrix"
        ])
        if not has_matrix:
            issues.append({"level": "WARN", "msg": f"{file_path.name} 建議包含 [專案擴充特化判定矩陣 (Extension Specialization Matrix)] 評估表格"})

    # 3. 檢查必跑 Extension (trigger: always)
    phase_code = compute_phase_code(file_path.name)  # 例如 P01, P02..., FT_PLAN
    matching_always_exts = [
        e for e in all_exts
        if e["trigger"] == "always" and ("ALL" in e["phase"] or phase_code in e["phase"])
    ]

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


def run_pluggable_extension_verifiers(plan_dir: Path, extensions_dir: Optional[Path]) -> dict:
    """抽象動態外掛 Hook：掃描 Plan Header 宣告之擴充項目，自動調用對應驗證腳本"""
    ext_results = {}
    registry = ExtensionRegistry.discover_all(ProjectContext)

    declared_ext_names = set()
    for md in plan_dir.glob("*.md"):
        try:
            content = md.read_text(encoding="utf-8", errors="ignore")
            headers = parse_header_metadata(content)
            for k in ["擴充項目", "active ext", "active ext."]:
                if k in headers and headers[k] and "none" not in headers[k].lower():
                    for item in re.split(r"[,、 ]+", headers[k]):
                        item_clean = item.strip()
                        if item_clean and item_clean.lower() != "none":
                            declared_ext_names.add(item_clean)
        except Exception:
            pass

    for ext_name in sorted(list(declared_ext_names)):
        script_to_run = None
        if ext_name in registry:
            script_to_run = registry[ext_name].get("script_path")
        elif extensions_dir and extensions_dir.is_dir():
            for c in [extensions_dir / f"{ext_name}_verify.py", extensions_dir / f"{ext_name}.py"]:
                if c.is_file():
                    script_to_run = c
                    break

        if not script_to_run or not Path(script_to_run).is_file():
            continue

        try:
            res = subprocess.run(
                [sys.executable, str(script_to_run), str(plan_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120
            )
            issues = []
            if res.returncode != 0:
                err_text = (res.stderr.strip() or res.stdout.strip() or f"exit code {res.returncode}")
                issues.append({"level": "ERROR", "msg": f"[{ext_name}] 外掛驗證失敗：{err_text}"})
            else:
                out_text = res.stdout.strip()
                if out_text:
                    for line in out_text.splitlines():
                        if "[WARN]" in line:
                            issues.append({"level": "WARN", "msg": f"[{ext_name}] {line}"})
                        elif "[ERROR]" in line:
                            issues.append({"level": "ERROR", "msg": f"[{ext_name}] {line}"})
            ext_results[f"Extension:{ext_name}"] = issues
        except Exception as e:
            ext_results[f"Extension:{ext_name}"] = [{"level": "ERROR", "msg": f"[{ext_name}] 執行外掛驗證腳本出錯: {e}"}]

    return ext_results



def verify_plan_directory(plan_dir: Path, all_exts: list, extensions_dir: Optional[Path] = None) -> dict:
    results = {}

    # 剛性檢查 changelog.md 存在性與基礎格式
    changelog_path = plan_dir / "changelog.md"
    if not changelog_path.is_file():
        results["changelog.md"] = [{"level": "ERROR", "msg": "缺少必備計畫內部變更日誌 (changelog.md)"}]
    else:
        try:
            cl_text = changelog_path.read_text(encoding="utf-8", errors="ignore")
            cl_issues = []
            if "變更" not in cl_text and "Changelog" not in cl_text:
                cl_issues.append({"level": "WARN", "msg": "changelog.md 缺少標準標題 '# 計畫變更紀錄 (Changelog)'"})
            if "| 日期時間" not in cl_text and "| 日期" not in cl_text:
                cl_issues.append({"level": "WARN", "msg": "changelog.md 缺少標準表格欄位 '| 日期時間 | 類型 | 摘要 |'"})
            results["changelog.md"] = cl_issues
        except Exception as e:
            results["changelog.md"] = [{"level": "ERROR", "msg": f"讀取 changelog.md 失敗: {e}"}]

    md_files = sorted(list(plan_dir.glob("*.md")))
    for md in md_files:
        if md.name in ["changelog.md", "handoff.md"]:
            continue
        file_issues = verify_single_file(md, all_exts)
        results[md.name] = file_issues

    # 執行抽象外掛式 Extension Verifier Hook
    if extensions_dir:
        ext_hook_results = run_pluggable_extension_verifiers(plan_dir, extensions_dir)
        results.update(ext_hook_results)

    # 遞迴檢查子計畫
    for sub in plan_dir.iterdir():
        if sub.is_dir() and sub.name.startswith("sub_"):
            sub_res = verify_plan_directory(sub, all_exts, extensions_dir)
            for k, v in sub_res.items():
                results[f"{sub.name}/{k}"] = v

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dev Plan 合規性與 Extension 深度稽核工具")
    parser.add_argument("plan", nargs="?", help="指定欲審查的 Dev Plan 目錄名稱或路徑（留空則掃描當前所有進行中計畫）")
    parser.add_argument("--all", action="store_true", help="包含 archive_plans 已歸檔之計畫一併掃描")
    args = parser.parse_args()

    module_dir = get_module_dir()
    plans_dir = get_plans_dir(module_dir)
    archive_dir = get_archive_dir(module_dir)

    root = get_workspace_root(module_dir)
    all_exts = parse_extensions(module_dir, root)

    target_plans = []
    if args.plan:
        p = Path(args.plan)
        if not p.is_absolute():
            if (plans_dir / args.plan).is_dir():
                p = plans_dir / args.plan
            elif (archive_dir / args.plan).is_dir():
                p = archive_dir / args.plan
            else:
                p = plans_dir / args.plan
        if p.exists() and p.is_dir():
            target_plans.append(p)
        else:
            print(f"[ERROR] 找不到指定的計畫目錄：{p}")
            sys.exit(1)
    else:
        if plans_dir.exists():
            for item in plans_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    target_plans.append(item)
        if args.all and archive_dir.exists():
            for y in archive_dir.iterdir():
                if y.is_dir():
                    for m in y.iterdir():
                        if m.is_dir():
                            for p in m.iterdir():
                                if p.is_dir():
                                    target_plans.append(p)

    if not target_plans:
        print(f"[INFO] 目前在 {plans_dir} 無任何進行中的 Plan。")
        return

    print("=" * 80)
    print(f"  Dev Plan 合規性與 Extension 深度驗收報告 (載入 {len(all_exts)} 個 Extension 定義)")
    print("=" * 80)

    total_errors = 0
    total_warns = 0

    ext_dir = None
    try:
        ext_dir = get_extensions_dir(module_dir)
    except Exception:
        pass

    for plan in target_plans:
        print(f"\n📁 審查計畫：{plan.name}")
        plan_results = verify_plan_directory(plan, all_exts, ext_dir)

        for f_name, issues in plan_results.items():
            if not issues:
                print(f"  ✅ {f_name:<35} [合規通過]")
            else:
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
