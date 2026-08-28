"""
CLI Entry point for agents-workflow.
Commands:
  release                     - Execute 4-step atomic release transaction for all active targets
  release-target              - Manage release targets (--list, --add <target>, --remove <target>)
  compile (alias: build)      - Execute Stage 1 artifact factory resolution pipeline
  tokens                      - Inspect registered token anchors
  list                        - Inspect exported standards, workflows, and templates
  --init-default              - One-click workflow URI protocols and directories initialization
  plan                        - Manage Dev Plans (archive, status, search, verify)
"""
import sys
import os
import argparse
from typing import List, Dict, Optional

# Windows 控制台 UTF-8 安全輸出保護
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Ensure package directory and sibling modules (e.g. core) are importable
_script_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_script_dir)
_modules_root = os.path.dirname(_pkg_root)

if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)
if _modules_root not in sys.path and os.path.isdir(_modules_root):
    sys.path.insert(0, _modules_root)

# 自動探測並掛載 core 模組路徑
for cand_core in [
    os.path.join(_modules_root, "core"),
    os.path.join(os.path.dirname(_modules_root), "source", "core"),
    os.path.join(os.path.dirname(_modules_root), "modules", "core")
]:
    if os.path.isdir(cand_core) and cand_core not in sys.path:
        sys.path.insert(0, cand_core)

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.initializer import WorkflowInitializer
from agents_workflow.publisher import ReleasePublisher
from agents_workflow.targets import ReleaseTargetManager
from agents_workflow.plans import (
    PlanArchiver,
    PlanScanner,
    PlanSearcher,
    PlanVerifier,
    PlanSeverity,
    PlanIssue,
    PlanReport,
    PlansToolchainError,
)



def cmd_release(args: List[str]) -> int:
    """執行原子 4 步發布交易（支援 --force 與雙階 Diff 檢測）。"""
    parser = argparse.ArgumentParser(prog="agents-workflow release", description="Execute release transaction for all active targets")
    parser.add_argument("--force", "-f", action="store_true", help="Force release all files without diff skipping")
    parsed_args = parser.parse_args(args)

    publisher = ReleasePublisher()
    print("[agents-workflow] Starting release transaction...")
    res = publisher.release_all(force=parsed_args.force)
    
    if res.get("success", False):
        if res.get("short_circuited", False):
            print(f"[agents-workflow] Release up to date (no changes detected, skipped {res.get('skipped_count', 0)} files).")
        else:
            print(f"[agents-workflow] Release completed successfully!")
            print(f"  * Written files:   {res.get('written_count', 0)}")
            print(f"  * Unchanged files: {res.get('skipped_count', 0)}")
            print(f"  * Total published: {res.get('published_count', 0)}")
        print(f"  * Active targets:  {', '.join(res.get('active_targets', []))}")
        if res.get("removed_count", 0) > 0:
            print(f"  * Pruned files:    {res.get('removed_count', 0)}")
        if res.get("orphan_targets"):
            print(f"  * Warning orphans: {', '.join(res.get('orphan_targets', []))}")
        return 0
    else:
        print(f"[agents-workflow] Release failed:")
        print(f"  - {res.get('error', 'Unknown error')}")
        for d in res.get("details", []):
            print(f"    * {d}")
        return 1


def cmd_release_target(args: List[str]) -> int:
    """管理 release-target 清單與狀態。"""
    if not args or args[0] in ("--list", "list", "-l"):
        targets = ReleaseTargetManager.list_targets()
        if not targets:
            print("[agents-workflow] No release targets found.")
            return 0
        print(f"\n[agents-workflow] Available Release Targets ({len(targets)}):")
        print("-" * 80)
        print(f"{'TARGET NAME':<20} {'STATUS':<20} {'DESCRIPTION'}")
        print("-" * 80)
        for t in targets:
            print(f"{t['name']:<20} {t['status']:<20} {t['description']}")
        print("-" * 80)
        return 0

    sub = args[0]
    if sub in ("--add", "add"):
        if len(args) < 2:
            print("[agents-workflow] Error: Missing target name for --add. Usage: release-target --add <target>")
            return 1
        t_name = args[1]
        print(f"[agents-workflow] Adding release target '{t_name}' and triggering atomic release...")
        ok = ReleaseTargetManager.add_target(t_name)
        if ok:
            print(f"[agents-workflow] Target '{t_name}' enabled and released successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed enabling target '{t_name}'.")
            return 1

    elif sub in ("--remove", "remove", "--rm"):
        if len(args) < 2:
            print("[agents-workflow] Error: Missing target name for --remove. Usage: release-target --remove <target>")
            return 1
        t_name = args[1]
        print(f"[agents-workflow] Removing release target '{t_name}' and triggering atomic release...")
        ok = ReleaseTargetManager.remove_target(t_name)
        if ok:
            print(f"[agents-workflow] Target '{t_name}' removed and cleaned successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed removing target '{t_name}'.")
            return 1
    else:
        print(f"[agents-workflow] Unknown release-target option '{sub}'. Use --list, --add <t>, or --remove <t>.")
        return 1


def cmd_compile(args: List[str]) -> int:
    compiler = ArtifactCompiler()
    print("[agents-workflow] Starting Stage 1 artifact compilation pipeline...")
    result = compiler.compile_stage1()
    
    if result["success"]:
        print(f"[agents-workflow] Stage 1 compilation completed successfully!")
        print(f"  * Cached files:    {len(result.get('resolved_items', []))}")
        print(f"  * Active inserts:  {result.get('inserted_count', 0)}")
        print(f"  * Known tokens:    {result.get('tokens_count', 0)}")
        return 0
    else:
        print(f"[agents-workflow] Stage 1 compilation failed with errors:")
        for err in result.get("errors", []):
            print(f"  - {err}")
        return 1


def cmd_tokens(args: List[str]) -> int:
    compiler = ArtifactCompiler()
    tokens = compiler.get_registered_tokens()
    
    if not tokens:
        print("[agents-workflow] No registered tokens found.")
        return 0
        
    print(f"\n[agents-workflow] Registered Token Anchors ({len(tokens)}):")
    print("-" * 75)
    print(f"{'TOKEN NAME':<32} {'DESCRIPTION'}")
    print("-" * 75)
    for tok in tokens:
        val = tok.get("value", "")
        desc = tok.get("description", "")
        print(f"{val:<32} {desc}")
    print("-" * 75)
    return 0


def cmd_list(args: List[str]) -> int:
    compiler = ArtifactCompiler()
    exports = compiler.get_exported_artifacts()
    
    if not exports:
        print("[agents-workflow] No exported artifacts found.")
        return 0
        
    print(f"\n[agents-workflow] Exported Artifacts Catalog ({len(exports)}):")
    print("-" * 80)
    print(f"{'TYPE':<12} {'SOURCE URI / PATH':<45} {'DESCRIPTION'}")
    print("-" * 80)
    for exp in exports:
        t = exp.get("type", "template")
        src = exp.get("source", "")
        desc = exp.get("description", "")
        print(f"{t:<12} {src:<45} {desc}")
    print("-" * 80)
    return 0


def cmd_init_default(args: List[str]) -> int:
    """處理 --init-default 與 --path-* 覆蓋參數。"""
    auto_confirm = False
    paths_override: Dict[str, str] = {}

    for arg in args:
        if arg in ("-y", "--yes"):
            auto_confirm = True
        elif arg.startswith("--path-plans="):
            paths_override["plans"] = arg.split("=", 1)[1]
        elif arg.startswith("--path-archived="):
            paths_override["archived"] = arg.split("=", 1)[1]
        elif arg.startswith("--path-docs="):
            paths_override["docs"] = arg.split("=", 1)[1]

    initializer = WorkflowInitializer()
    is_interactive = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    res = initializer.run_init_default(
        paths_override=paths_override,
        auto_confirm=auto_confirm,
        interactive=is_interactive
    )
    return 0 if res.get("success", False) else 1


def cmd_plan(args: List[str]) -> int:
    """處理 Dev Plans 工具鏈 (archive, status, search, verify)。"""
    if not args or args[0] in ("-h", "--help", "help"):
        print("""Usage: yscb agents-workflow plan <action> [options]

Plan Actions:
  archive <plan_name> [--force]   Safely archive a completed Dev Plan to workflow.archived://
  status                          Scan and print the active Dev Plans status matrix
  search [query] [options]        Search Decision Records (DR) or full-text in Dev Plans
    Options:
      --dr                        Search specifically for Decision Records (DR)
      --year=<YYYY>               Filter by year (e.g. 2026)
      --month=<MM>                Filter by month (e.g. 08)
      --limit=<N>                 Limit returned count (default: 20/25)
  verify [plan_name] [--all]      Verify Markdown compliance and Blockquote headers in Dev Plans
""")
        return 0

    action = args[0].lower()
    sub_args = args[1:]

    # 1. plan archive
    if action == "archive":
        if not sub_args:
            print("[agents-workflow:plan] Error: Missing plan name to archive. Usage: plan archive <plan_name> [--force]")
            return 1
        plan_name = sub_args[0]
        force = "--force" in sub_args or "-f" in sub_args

        archiver = PlanArchiver()
        try:
            res = archiver.archive_plan(plan_name, force=force)
            if res.get("cleaned_handoff"):
                print(f"  * [CLEANUP] 已清理暫時性交接快照：handoff.md")
            for w in res.get("warnings", []):
                print(f"  [WARNING] {w}")
            print(f"[agents-workflow:plan] [SUCCESS] 已成功將計畫歸檔至：{res.get('dest_path')}")
            return 0
        except PlansToolchainError as pe:
            print(f"[agents-workflow:plan] [ERROR] {pe}")
            return 1
        except Exception as ex:
            print(f"[agents-workflow:plan] [ERROR] 歸檔過程發生非預期錯誤：{ex}")
            return 1

    # 2. plan status (明確不掃描歷史目錄)
    elif action == "status":
        scanner = PlanScanner()
        matrix_str = scanner.render_matrix_ascii()
        print(matrix_str)
        return 0

    # 3. plan search
    elif action == "search":
        is_dr = "--dr" in sub_args
        limit = 20 if not is_dr else 25
        year = None
        month = None
        pos_queries = []

        for sa in sub_args:
            if sa == "--dr":
                is_dr = True
            elif sa.startswith("--year="):
                year = sa.split("=", 1)[1]
            elif sa.startswith("--month="):
                month = sa.split("=", 1)[1]
            elif sa.startswith("--limit="):
                try:
                    limit = int(sa.split("=", 1)[1])
                except ValueError:
                    pass
            elif not sa.startswith("-"):
                pos_queries.append(sa)

        query = " ".join(pos_queries)
        searcher = PlanSearcher()

        if is_dr or not query:
            drs = searcher.search_drs(query=query, year=year, month=month, limit=limit)
            print("=" * 90)
            print(f"{'Plan 名稱 / 來源檔案':<40} | {'DR ID / 標題':<22} | {'結論 / 摘要'}")
            print("=" * 90)
            for d in drs:
                src = d["source_file"] if len(d["source_file"]) <= 38 else d["source_file"][:35] + "..."
                did = d["dr_id"] if len(d["dr_id"]) <= 20 else d["dr_id"][:17] + "..."
                summ = d["summary"] if len(d["summary"]) <= 40 else d["summary"][:37] + "..."
                print(f"{src:<40} | {did:<22} | {summ}")
            print("=" * 90)
            print(f"共找到 {len(drs)} 筆 Decision Records。")
            return 0
        else:
            matches = searcher.search_full_text(query=query, year=year, month=month, limit=limit)
            print(f"搜尋關鍵字: \"{query}\" ...")
            print("=" * 90)
            for m in matches:
                print(f"[{m['plan_name']}/{m['rel_path']}:L{m['line_no']}]")
                for l_no, l_text in m.get("context", []):
                    prefix = " > " if l_no == m["line_no"] else "   "
                    print(f"{prefix}{l_no:4d}: {l_text}")
                print("-" * 90)
            print(f"共找到 {len(matches)} 筆符合結果。")
            return 0

    # 4. plan verify / plan check
    elif action in ("verify", "check"):
        if sub_args and sub_args[0] in ("-h", "--help", "help"):
            print("Usage: yscb agents-workflow plan check [plan_name] [--all] [--json]")
            return 0
        include_all = "--all" in sub_args or "-a" in sub_args
        is_json = "--json" in sub_args
        target_name = None
        for sa in sub_args:
            if sa not in ("--all", "-a", "--json") and not sa.startswith("-"):
                target_name = sa
                break

        verifier = PlanVerifier()
        if target_name:
            rep = verifier.verify_plan(target_name)
            reports = {rep.plan_name: rep}
        else:
            reports = verifier.verify_all_plans(include_archived=include_all)

        if is_json:
            import json
            json_dict = {k: v.to_dict() for k, v in reports.items()}
            print(json.dumps(json_dict, indent=2, ensure_ascii=False))
            return 0 if all(r.passed for r in reports.values()) else 1

        print("=" * 70)
        print("YS-Codebase Dev Plan Compliance Diagnostic Report")
        print("=" * 70)

        total_plans = len(reports)
        passed_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.PASS)
        warn_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.WARN)
        fail_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.FAIL)

        for p_name, r in reports.items():
            status_tag = f"[{r.status.value}]"
            print(f"[*] Plan: {p_name:<50} {status_tag}")
            if r.status != PlanSeverity.PASS:
                for iss in r.issues:
                    loc = f"{iss.file_name}:{iss.line_number}" if iss.line_number else iss.file_name
                    print(f"    |-- [{iss.severity.value}] ({loc}) [{iss.category}] {iss.message}")

        print("-" * 70)
        summary_str = f"Summary : {total_plans} Total, {passed_plans} Passed, {warn_plans} Warnings, {fail_plans} Failed"
        print(summary_str)
        overall_status = "PASSED" if fail_plans == 0 else "FAILED"
        print(f"Status  : {overall_status}")
        print("=" * 70)

        return 0 if fail_plans == 0 else 1

    else:
        print(f"[agents-workflow:plan] Unknown plan action '{action}'. Use archive, status, search, or check.")
        return 1



def print_help():
    print("""Usage: yscb agents-workflow <command> [options]

Commands:
  release                     Execute 4-step atomic release transaction for all active targets
  release-target [options]    Manage release targets
    --list, list              List available targets, status, and orphan warnings
    --add <target>            Enable release target and trigger release
    --remove <target>         Disable release target and prune published files
  compile, build              Run Stage 1 artifact compilation into cache.root://
  tokens                      List all registered token anchors and descriptions
  list                        List all declared export standards, workflows, and templates
  --init-default, init        One-click workflow URI protocols and directories initialization
    Options for --init-default:
      -y, --yes               Automatic confirmation mode without prompting
      --path-plans=<path>     Override recommended path for workflow.plans
      --path-archived=<path>  Override recommended path for workflow.archived
      --path-docs=<path>      Override recommended path for workflow.docs
  plan <action> [options]     Dev Plans management toolchain
    archive <name> [--force]  Safely archive a completed Dev Plan
    status                    Scan active Dev Plans status matrix (active plans only)
    search <query> [--dr]     Search Decision Records or full text in Dev Plans
    verify [name] [--all]     Verify Markdown compliance and Blockquote headers
  --help, -h                  Show this help message
""")


def main(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    cmd = args[0].lower()
    sub_args = args[1:]

    if cmd in ("--init-default", "init-default", "init"):
        return cmd_init_default(sub_args)
    elif cmd in ("release", "publish"):
        return cmd_release(sub_args)
    elif cmd in ("release-target", "release-targets", "target", "targets"):
        return cmd_release_target(sub_args)
    elif cmd in ("compile", "build"):
        return cmd_compile(sub_args)
    elif cmd in ("tokens", "--list-token", "--list-tokens"):
        return cmd_tokens(sub_args)
    elif cmd in ("list", "--list"):
        return cmd_list(sub_args)
    elif cmd == "plan":
        return cmd_plan(sub_args)
    elif cmd == "plan-archive":
        return cmd_plan(["archive"] + sub_args)
    elif cmd in ("plan-status", "plans-status"):
        return cmd_plan(["status"] + sub_args)
    elif cmd == "plan-search":
        return cmd_plan(["search"] + sub_args)
    elif cmd == "plan-verify":
        return cmd_plan(["verify"] + sub_args)
    else:
        if "--init-default" in args:
            all_init_args = [a for a in args if a != "--init-default"]
            return cmd_init_default(all_init_args)
        print(f"[agents-workflow] Unknown command '{cmd}'. See --help.")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
