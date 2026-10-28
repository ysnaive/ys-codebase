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
    SessionTraceEngine,
)
from agents_workflow.roadmap import RoadmapManager, TodoManager


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


def roadmap_list(cmd_bags: Any) -> int:
    """列出路線圖摘要表格（支援 --status 過濾，自動排除 TODO.md）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "roadmap_list")
    mgr = RoadmapManager()
    opt_status = bags.get_option_value("status")
    status_filter = str(opt_status).strip() if isinstance(opt_status, str) and opt_status.strip() else None
    table_str = mgr.format_summary_table(status_filter=status_filter)
    print(table_str)
    return 0


def roadmap_promote(cmd_bags: Any) -> int:
    """將儲備路線圖物理移轉至計畫目錄並重命名為 roadmap.md (Consume-on-Promote)。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "roadmap_promote")
    if not bags.args:
        print("[agents-workflow:roadmap] Error: Missing topic to promote. Usage: roadmap promote <topic> [--plan <dir>] [--model <ModelName>]")
        return 1
    topic = bags.args[0]
    opt_plan = bags.get_option_value("plan")
    plan_dir = str(opt_plan).strip() if isinstance(opt_plan, str) and opt_plan.strip() else None
    opt_model = bags.get_option_value("model")
    model_str = str(opt_model).strip() if isinstance(opt_model, str) and opt_model.strip() else "Unknown"

    mgr = RoadmapManager()
    res = mgr.promote_roadmap(topic_or_file=topic, model=model_str, target_plan=plan_dir)
    if not res.get("success", False):
        print(f"[agents-workflow:roadmap] [ERROR] {res.get('error', 'Failed to promote roadmap')}")
        return 1

    print(res.get("message", ""))
    return 0


def roadmap(cmd_bags: Any) -> int:
    """處理 `agents-workflow roadmap` CLI 指令（支援 list、promote 與單一主題查詢）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "roadmap")
    mgr = RoadmapManager()

    first_arg = bags.args[0] if bags.args else None
    list_all = bags.has_option("list") or bags.has_option("l")

    if first_arg and first_arg.lower() == "promote" and not list_all:
        sub_bags = CmdBags(
            raw_cmd=bags.raw_cmd,
            command="roadmap_promote",
            args=bags.args[1:],
            options=bags.options,
        )
        return roadmap_promote(sub_bags)

    if first_arg and first_arg.lower() == "list":
        sub_bags = CmdBags(
            raw_cmd=bags.raw_cmd,
            command="roadmap_list",
            args=bags.args[1:],
            options=bags.options,
        )
        return roadmap_list(sub_bags)

    if first_arg and not list_all:
        item = mgr.get_roadmap(first_arg)
        if not item:
            print(f"[agents-workflow:roadmap] Roadmap topic '{first_arg}' not found in {mgr.roadmap_dir}.")
            return 1
        print(f"\n[agents-workflow:roadmap] Topic: {item.topic} ({item.status})")
        print(f"  * Path:    {item.path}")
        print(f"  * Date:    {item.date if item.date else 'N/A'}")
        print(f"  * Scope:   {item.scope}")
        print(f"  * Trigger: {item.trigger}")
        print(f"  * Title:   {item.title}")
        print(f"  * Summary: {item.problem_summary}")
        return 0
    else:
        return roadmap_list(bags)


def todo_add(cmd_bags: Any) -> int:
    """免讀盲寫追加單筆 TODO 條目至 workflow.roadmap://TODO.md。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "todo_add")
    if not bags.args:
        print("[agents-workflow:todo] Error: Missing title. Usage: todo add \"<標題>\" [--scope <模組>] [--note \"<備註>\"] [--model <ModelName>]")
        return 1
    title = " ".join(bags.args).strip()
    opt_scope = bags.get_option_value("scope")
    scope = str(opt_scope).strip() if isinstance(opt_scope, str) and opt_scope.strip() else "general"
    opt_note = bags.get_option_value("note")
    note = str(opt_note).strip() if isinstance(opt_note, str) and opt_note.strip() else "無"
    opt_model = bags.get_option_value("model")
    model_str = str(opt_model).strip() if isinstance(opt_model, str) and opt_model.strip() else "Unknown"

    mgr = TodoManager()
    try:
        item = mgr.add_todo(title=title, scope=scope, note=note, model=model_str)
    except Exception as ex:
        print(f"[agents-workflow:todo] [ERROR] {ex}")
        return 1
    print(f"[agents-workflow:todo] [SUCCESS] 已追加待辦條目 [{item.todo_id}]:")
    print(f"  * ID:      {item.todo_id}")
    print(f"  * Date:    {item.date}")
    print(f"  * Scope:   {item.scope}")
    print(f"  * Title:   {item.title}")
    print(f"  * Note:    {item.note}")
    return 0


def todo_list(cmd_bags: Any) -> int:
    """列出 workflow.roadmap://TODO.md 中之待辦條目（支援 --scope 過濾）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "todo_list")
    opt_scope = bags.get_option_value("scope")
    scope = str(opt_scope).strip() if isinstance(opt_scope, str) and opt_scope.strip() else None

    mgr = TodoManager()
    print(mgr.format_todo_table(scope_keyword=scope))
    return 0


def todo_promote(cmd_bags: Any) -> int:
    """支援單筆或多筆打包提取 TODO 條目 (Pop) 並生成 todo.md 與 changelog.md。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "todo_promote")
    if not bags.args:
        print("[agents-workflow:todo] Error: Missing TODO ID(s) to promote. Usage: todo promote <TODO-ID> [TODO-ID...] --slug <plan_slug> [--plan <dir>] [--model <ModelName>]")
        return 1
    opt_slug = bags.get_option_value("slug")
    slug = str(opt_slug).strip() if isinstance(opt_slug, str) and opt_slug.strip() else None
    opt_plan = bags.get_option_value("plan")
    plan_dir = str(opt_plan).strip() if isinstance(opt_plan, str) and opt_plan.strip() else None
    opt_model = bags.get_option_value("model")
    model_str = str(opt_model).strip() if isinstance(opt_model, str) and opt_model.strip() else "Unknown"

    mgr = TodoManager()
    res = mgr.promote_todos(todo_ids=bags.args, slug=slug, model=model_str, target_plan=plan_dir)
    if not res.get("success", False):
        print(f"[agents-workflow:todo] [ERROR] {res.get('error', 'Failed to promote todo(s)')}")
        return 1

    print(res.get("message", ""))
    return 0


def todo(cmd_bags: Any) -> int:
    """輕量級待辦與微觀技術債管理工具鏈複合入口 (TODO.md)。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "todo")
    if not bags.args:
        return todo_list(bags)
    action = bags.args[0].lower()
    sub_bags = CmdBags(
        raw_cmd=bags.raw_cmd,
        command=f"todo_{action}",
        args=bags.args[1:],
        options=bags.options,
    )
    if action == "add":
        return todo_add(sub_bags)
    elif action == "list":
        return todo_list(sub_bags)
    elif action == "promote":
        return todo_promote(sub_bags)
    else:
        print(f"[agents-workflow:todo] Unknown todo action '{action}'. Use add, list, or promote.")
        return 1


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
    """管理 release-target 清單與狀態（相容 --add/add 與 --remove/remove，支援 --proj 旗標）。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "release-target")

    is_proj = bags.has_option("proj") or bags.has_option("project")
    tier_label = "PROJECT" if is_proj else "LOCAL"

    # 1. 優先判斷 Add 語法（支援 --add <t> 或 add <t>）
    is_add = bags.has_option("add") or (bool(bags.args) and bags.args[0] in ("add", "--add"))
    if is_add:
        opt_val = bags.get_option_value("add")
        target_name = (
            opt_val if isinstance(opt_val, str) and opt_val.strip() else None
        ) or (
            bags.args[1] if bags.args and bags.args[0] in ("add", "--add") and len(bags.args) > 1 else None
        ) or (
            bags.args[0] if bags.args and bags.args[0] not in ("add", "--add") else None
        )
        if not target_name or not isinstance(target_name, str) or not target_name.strip():
            print("[agents-workflow] Error: Missing target name for --add. Usage: release-target --add <target> [--proj]")
            return 1
        print(f"[agents-workflow] Adding release target '{target_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.add_target(target_name, is_project=is_proj)
        if ok:
            print(f"[agents-workflow] Target '{target_name}' enabled ({tier_label}) and released successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed enabling target '{target_name}' ({tier_label}).")
            return 1

    # 2. 優先判斷 Remove 語法（支援 --remove <t> 或 remove <t>）
    is_remove = bags.has_option("remove") or (bool(bags.args) and bags.args[0] in ("remove", "--remove", "--rm"))
    if is_remove:
        opt_val = bags.get_option_value("remove")
        target_name = (
            opt_val if isinstance(opt_val, str) and opt_val.strip() else None
        ) or (
            bags.args[1] if bags.args and bags.args[0] in ("remove", "--remove", "--rm") and len(bags.args) > 1 else None
        ) or (
            bags.args[0] if bags.args and bags.args[0] not in ("remove", "--remove", "--rm") else None
        )
        if not target_name or not isinstance(target_name, str) or not target_name.strip():
            print("[agents-workflow] Error: Missing target name for --remove. Usage: release-target --remove <target> [--proj]")
            return 1
        print(f"[agents-workflow] Removing release target '{target_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.remove_target(target_name, is_project=is_proj)
        if ok:
            print(f"[agents-workflow] Target '{target_name}' removed ({tier_label}) and cleaned successfully.")
            return 0
        else:
            print(f"[agents-workflow] Failed removing target '{target_name}' ({tier_label}).")
            return 1

    # 3. 預設行為：若指定 list 旗標或無其他動作，執行目標清冊輸出
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
        val = tok.get("value") or tok.get("name") or ""
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
        if "__${" in desc or "__#{" in desc:
            desc = compiler.resolve_stage2_uri(desc, "list", {})
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
    """掃描並輸出進行中之 Dev Plans 狀態矩陣，或執行斷點領航與 handoff.md 原子閱後即焚 (--resume)。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_status")
    scanner = PlanScanner()

    is_resume = bags.has_option("resume")
    opt_plan = bags.get_option_value("plan")
    target_plan = (
        str(opt_plan).strip()
        if isinstance(opt_plan, str) and opt_plan.strip()
        else (bags.args[0] if bags.args else None)
    )

    if is_resume or target_plan:
        if not is_resume:
            # 未加 --resume 但指定了 --plan / plan_name：先印狀態矩陣，再印唯讀領航資訊
            print(scanner.render_matrix_ascii())
        res = scanner.execute_resume(
            plan_name_or_subpath=target_plan,
            consume_handoff=is_resume,
        )
        if not res.get("success", False):
            # 若存在多個活躍計畫且未指定 --plan，先印出狀態矩陣方便使用者/Agent 確認
            print(scanner.render_matrix_ascii())
            print(res.get("formatted_output", ""))
            return 1
        print(res.get("formatted_output", ""))
        return 0

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
    year = str(bags.get_option_value("year")) if bags.get_option_value("year") else None
    month = str(bags.get_option_value("month")) if bags.get_option_value("month") else None
    
    l_opt = bags.get_option_value("limit")
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
    """合規性診斷 Dev Plans 文件結構、雙檔協同、追溯差集與免讀盲寫追加 changelog.md。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "plan_check")
    include_all = bags.has_option("all") or bags.has_option("a")
    is_json = bags.has_option("json")
    target_name = bags.args[0] if bags.args else None

    opt_phase = bags.get_option_value("phase")
    phase_str = str(opt_phase).strip() if isinstance(opt_phase, str) and opt_phase.strip() else "all"

    opt_log = bags.get_option_value("log")
    log_msg = str(opt_log).strip() if isinstance(opt_log, str) and opt_log.strip() else None

    opt_type = bags.get_option_value("type")
    log_type = str(opt_type).strip() if isinstance(opt_type, str) and opt_type.strip() else "PHASE"

    opt_model = bags.get_option_value("model")
    model_str = str(opt_model).strip() if isinstance(opt_model, str) and opt_model.strip() else None

    verifier = PlanVerifier()

    # 若未指定 target_name 但傳入了 --log 或指定單一 --phase (非 all)，自動透過 PlanScanner 定位單一活躍計畫（含活躍 sub_XX）
    if not target_name and (log_msg or phase_str.upper() not in ("ALL", "")):
        scanner = PlanScanner()
        t_dir, err_msg = scanner.resolve_target_plan_dir(None)
        if err_msg or t_dir is None:
            print(f"[agents-workflow:plan] [ERROR] {err_msg or '無法自動定位單一目標計畫，請明確傳入 <plan_name>。'}")
            return 1
        # 若為 Umbrella 且未指定子計畫，自動深入活躍 sub_XX
        from agents_workflow.plans.status import PlanStatusResolver
        nav = PlanStatusResolver.resolve_next_action(t_dir)
        target_name = str(nav["target_plan_dir"])

    if target_name:
        rep = verifier.verify_plan(
            target_name,
            phase=phase_str,
            log_msg=log_msg,
            log_type=log_type,
            model=model_str,
        )
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
        if r.companion_created:
            print(f"    |-- [SELF-HEAL] 已自動初始化伴隨檔: {', '.join(r.companion_created)}")
        if r.header_healed:
            print(f"    |-- [SELF-HEAL] 已自動補齊確定性標頭: {', '.join(r.header_healed)}")
        if r.log_status == "appended":
            print(f"    |-- [CHANGELOG] 已免讀自動追加變更日誌列 (Type: {log_type.upper()})")
        elif r.log_status == "idempotent_skipped":
            print(f"    |-- [IDEMPOTENT] 變更日誌首列已存在相同 (類型, 摘要)，略過重複寫入")
        elif r.log_status == "skipped_on_fail":
            print(f"    |-- [BLOCKED] 因檢核存在 FAIL，已阻斷寫入 changelog.md")
        if r.status != PlanSeverity.PASS:
            for iss in r.issues:
                loc = f"{iss.file_name}:{iss.line_number}" if iss.line_number else iss.file_name
                print(f"    |-- [{iss.severity.value}] ({loc}) [{iss.category}] {iss.message}")
        if target_name and r.passed and r.next_phase_hint:
            print(f"    |-- [NEXT PHASE GATE] {r.next_phase_hint}")

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


def session_trace(cmd_bags: Any) -> int:
    """執行三級漸進式對話軌跡與五大硬性摩擦訊號提取 (供 /session-audit 調用)。"""
    guard_dispatch("agents-workflow")
    _setup_stream_encodings()
    bags = _normalize_bags(cmd_bags, "session_trace")

    opt_plan = bags.get_option_value("plan")
    plan_arg = str(opt_plan).strip() if isinstance(opt_plan, str) and opt_plan.strip() else (
        str(bags.args[0]).strip() if bags.args else None
    )

    opt_transcript = bags.get_option_value("transcript")
    transcript_arg = str(opt_transcript).strip() if isinstance(opt_transcript, str) and opt_transcript.strip() else None

    opt_since = bags.get_option_value("since")
    since_min: Optional[float] = None
    if opt_since is not None and opt_since is not True:
        try:
            since_min = float(str(opt_since).strip())
        except ValueError:
            print(f"[agents-workflow:session-trace] Error: Invalid --since value '{opt_since}' (expected minutes).")
            return 1

    opt_limit = bags.get_option_value("limit")
    limit_val = 50
    if opt_limit is not None and opt_limit is not True:
        try:
            limit_val = max(1, int(str(opt_limit).strip()))
        except ValueError:
            print(f"[agents-workflow:session-trace] Error: Invalid --limit value '{opt_limit}' (expected integer).")
            return 1

    is_json = bags.has_option("json")
    is_list = bags.has_option("list") or bags.has_option("l")
    is_all = bags.has_option("all") or bags.has_option("a")

    engine = SessionTraceEngine()
    if is_list:
        sessions = engine.list_sessions(
            include_all_workspaces=is_all,
            include_subagents=is_all,
            limit=limit_val if opt_limit is not None else 20,
        )
        if is_json:
            print(json.dumps(sessions, indent=2, ensure_ascii=False))
        else:
            print(engine.render_session_list_text(sessions))
        return 0

    report = engine.analyze(
        plan_name_or_subpath=plan_arg,
        transcript_path=transcript_arg,
        since_minutes=since_min,
        limit=limit_val,
    )

    # 若顯式指定了不存在之 --plan，回傳非 0 退出碼
    if plan_arg and report.target_plan is None and "找不到指定的計畫目錄" in report.plan_resolution_note:
        if is_json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"[agents-workflow:session-trace] Error: {report.plan_resolution_note}")
        return 1

    if is_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(report.render_text())
    return 0


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


def cmd_todo(cmd_bags: Any) -> int:
    return todo(cmd_bags)


def cmd_session_trace(cmd_bags: Any) -> int:
    return session_trace(cmd_bags)


