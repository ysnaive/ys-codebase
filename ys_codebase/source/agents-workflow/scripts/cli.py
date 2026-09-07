"""
CLI Entry point for agents-workflow.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""
import sys
import os
import json
import builtins
from typing import Any, List, Dict, Optional

from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
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
from agents_workflow.roadmap import RoadmapManager


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """容錯正規化：若傳入 List[str] 則包裝為 CmdBags，支援內部測試直呼。"""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (builtins.list, tuple)):
        args = builtins.list(cmd_bags)
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


def roadmap(cmd_bags: Any) -> int:
    """處理 `agents-workflow roadmap` CLI 指令。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "roadmap")
    mgr = RoadmapManager()
    topic = bags.args[0] if bags.args else None
    list_all = bags.has_option("list") or bags.has_option("l")

    if topic and not list_all:
        item = mgr.get_roadmap(topic)
        if not item:
            print(f"[agents-workflow:roadmap] Roadmap topic '{topic}' not found in {mgr.roadmap_dir}.")
            return 1
        print(f"\n[agents-workflow:roadmap] Topic: {item.topic} ({item.status})")
        print(f"  * Path:    {item.path}")
        print(f"  * Date:    {item.date if item.date else 'N/A'}")
        print(f"  * Title:   {item.title}")
        print(f"  * Summary: {item.problem_summary}")
        return 0
    else:
        table_str = mgr.format_summary_table()
        print(table_str)
        return 0


def release(cmd_bags: Any) -> int:
    """執行原子 4 步發布交易（支援 --force 與雙階 Diff 檢測）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "release")
    force = bags.has_option("force") or bags.has_option("f")

    publisher = ReleasePublisher()
    print("[agents-workflow] Starting release transaction...")
    res = publisher.release_all(force=force)
    
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


def release_target(cmd_bags: Any) -> int:
    """管理 release-target 清單與狀態（支援 --proj 旗標）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "release-target")

    action = bags.args[0] if bags.args else None
    if not action or action in ("--list", "list", "-l") or bags.has_option("list") or bags.has_option("l"):
        targets = ReleaseTargetManager.list_targets()
        if not targets:
            print("[agents-workflow] No release targets found.")
            return 0
        print(f"\n[agents-workflow] Available Release Targets ({len(targets)}):")
        print("-" * 88)
        print(f"{'TARGET NAME':<20} {'STATUS':<26} {'DESCRIPTION'}")
        print("-" * 88)
        for t in targets:
            status_str = t['status']
            print(f"{t['name']:<20} {status_str:<26} {t['description']}")
        print("-" * 88)
        return 0

    is_proj = bags.has_option("proj") or bags.has_option("project")
    tier_label = "PROJECT" if is_proj else "LOCAL"
    target_name = bags.args[1] if len(bags.args) > 1 else (str(bags.get_option("add")) if bags.get_option("add") else (str(bags.get_option("remove")) if bags.get_option("remove") else None))

    if action in ("--add", "add") or bags.has_option("add"):
        t_name = target_name or (bags.args[0] if len(bags.args) > 0 and action != "add" else None)
        if not t_name:
            print("[agents-workflow] Error: Missing target name for --add. Usage: release-target --add <target> [--proj]")
            return 1
        print(f"[agents-workflow] Adding release target '{t_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.add_target(t_name, is_project=is_proj)
        if ok:
            print(f"[agents-workflow] Target '{t_name}' enabled ({tier_label}) and released successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed enabling target '{t_name}' ({tier_label}).")
            return 1

    elif action in ("--remove", "remove", "--rm") or bags.has_option("remove"):
        t_name = target_name or (bags.args[0] if len(bags.args) > 0 and action != "remove" else None)
        if not t_name:
            print("[agents-workflow] Error: Missing target name for --remove. Usage: release-target --remove <target> [--proj]")
            return 1
        print(f"[agents-workflow] Removing release target '{t_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.remove_target(t_name, is_project=is_proj)
        if ok:
            print(f"[agents-workflow] Target '{t_name}' removed ({tier_label}) and cleaned successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed removing target '{t_name}' ({tier_label}).")
            return 1
    else:
        print(f"[agents-workflow] Unknown release-target option '{action}'. Use list, add <t> [--proj], or remove <t> [--proj].")
        return 1


def compile(cmd_bags: Any) -> int:
    """執行 Stage 1 中繼工廠編譯管線。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "compile")
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


def tokens(cmd_bags: Any) -> int:
    """檢視全系統已註冊之 Token 錨點清單與語意 URI 說明。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "tokens")
    compiler = ArtifactCompiler()
    tokens_list = compiler.get_registered_tokens()
    
    if not tokens_list:
        print("[agents-workflow] No registered tokens found.")
        return 0
        
    print(f"\n[agents-workflow] Registered Token Anchors ({len(tokens_list)}):")
    print("-" * 75)
    print(f"{'TOKEN NAME':<32} {'DESCRIPTION'}")
    print("-" * 75)
    for tok in tokens_list:
        val = tok.get("value", "")
        desc = tok.get("description", "")
        print(f"{val:<32} {desc}")
    print("-" * 75)
    return 0


def list(cmd_bags: Any) -> int:
    """檢視當前已安裝模組清冊與 agents-workflow 導出規範清單。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "list")
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


def init(cmd_bags: Any) -> int:
    """一鍵初始化工作流目錄結構與 URI 協議。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "init")
    auto_confirm = bags.has_option("yes") or bags.has_option("y")
    paths_override: Dict[str, str] = {}
    
    if bags.get_option_value("path-plans"):
        paths_override["plans"] = str(bags.get_option_value("path-plans"))
    if bags.get_option_value("path-archived"):
        paths_override["archived"] = str(bags.get_option_value("path-archived"))
    if bags.get_option_value("path-docs"):
        paths_override["docs"] = str(bags.get_option_value("path-docs"))

    initializer = WorkflowInitializer()
    is_interactive = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    res = initializer.run_init_default(
        paths_override=paths_override,
        auto_confirm=auto_confirm,
        interactive=is_interactive
    )
    return 0 if res.get("success", False) else 1


def plan_archive(cmd_bags: Any) -> int:
    """將已完成之 Dev Plan 安全歸檔至 workflow.archived://。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_archive")
    if not bags.args:
        print("[agents-workflow:plan] Error: Missing plan name to archive. Usage: plan archive <plan_name> [--force]")
        return 1
    plan_name = bags.args[0]
    force = bags.has_option("force") or bags.has_option("f")

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


def plan_status(cmd_bags: Any) -> int:
    """掃描並輸出進行中之 Dev Plans 狀態矩陣 (ASCII 表格)。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_status")
    scanner = PlanScanner()
    matrix_str = scanner.render_matrix_ascii()
    print(matrix_str)
    return 0


def plan_search(cmd_bags: Any) -> int:
    """搜尋 Dev Plans 內部之決策紀錄 (DR) 或全文關鍵字。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_search")
    is_dr = bags.has_option("dr")
    limit = 20 if not is_dr else 25
    year = str(bags.get_option("year")) if bags.get_option("year") else None
    month = str(bags.get_option("month")) if bags.get_option("month") else None
    
    l_opt = bags.get_option("limit")
    if l_opt:
        try:
            limit = int(str(l_opt).strip())
        except ValueError:
            pass

    query = " ".join(bags.args)
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


def plan_check(cmd_bags: Any) -> int:
    """合規性診斷 Dev Plans 文件結構、標題與 Header 元數據。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_check")
    include_all = bags.has_option("all") or bags.has_option("a")
    is_json = bags.has_option("json")
    target_name = bags.args[0] if bags.args else None

    verifier = PlanVerifier()
    if target_name:
        rep = verifier.verify_plan(target_name)
        reports = {rep.plan_name: rep}
    else:
        reports = verifier.verify_all_plans(include_archived=include_all)

    if is_json:
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


def plan_verify(cmd_bags: Any) -> int:
    """plan check 之同義指令。"""
    return plan_check(cmd_bags)


def plan(cmd_bags: Any) -> int:
    """Dev Plans 專案開發計畫管理工具鏈複合入口。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan")
    if not bags.args:
        # 當無子命令時，轉呼叫 plan_status
        return plan_status(bags)
    action = bags.args[0].lower()
    sub_bags = CmdBags(
        raw_cmd=bags.raw_cmd,
        command=f"plan_{action}",
        args=bags.args[1:],
        options=bags.options
    )
    if action == "archive":
        return plan_archive(sub_bags)
    elif action == "status":
        return plan_status(sub_bags)
    elif action == "search":
        return plan_search(sub_bags)
    elif action in ("check", "verify"):
        return plan_check(sub_bags)
    else:
        print(f"[agents-workflow:plan] Unknown plan action '{action}'. Use archive, status, search, or check.")
        return 1


# Internal test / caller compatibility aliases
def cmd_roadmap(cmd_bags: Any) -> int:
    return roadmap(cmd_bags)


def cmd_release(cmd_bags: Any) -> int:
    return release(cmd_bags)


def cmd_release_target(cmd_bags: Any) -> int:
    return release_target(cmd_bags)


def cmd_compile(cmd_bags: Any) -> int:
    return compile(cmd_bags)


def cmd_tokens(cmd_bags: Any) -> int:
    return tokens(cmd_bags)


def cmd_list(cmd_bags: Any) -> int:
    return list(cmd_bags)


def cmd_init(cmd_bags: Any) -> int:
    return init(cmd_bags)


def cmd_init_default(cmd_bags: Any) -> int:
    return init(cmd_bags)


def cmd_plan(cmd_bags: Any) -> int:
    return plan(cmd_bags)

