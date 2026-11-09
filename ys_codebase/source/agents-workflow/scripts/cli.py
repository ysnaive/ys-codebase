"""
CLI Entry point for agents-workflow.
Migrated to core.commands active execution contract with strong-typed CmdBags.
"""
import builtins
import json
import sys
from typing import Any, Dict, Optional

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.initializer import WorkflowInitializer
from agents_workflow.plans import (
    PlanArchiver,
    PlanScanner,
    PlanSearcher,
    PlanSeverity,
    PlansToolchainError,
    PlanVerifier,
    SessionTraceEngine,
)
from agents_workflow.publisher import ReleasePublisher
from agents_workflow.roadmap import RoadmapManager, TodoManager
from agents_workflow.targets import ReleaseTargetManager
from core.commands import CmdBags, CmdOption
from core.guard import guard_dispatch
from core.log import log


def _log_cli(*args: Any, **kwargs: Any) -> None:
    file_arg = kwargs.get("file")
    stream = "stderr" if file_arg is sys.stderr else "stdout"
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    text = sep.join(str(a) for a in args)
    log(text, stream=stream, end=end)


def _normalize_bags(cmd_bags: Any, default_cmd: str = "") -> CmdBags:
    """容錯正規化：若傳入 List[str] 則包裝為 CmdBags，支援內部測試直呼與空白分隔之 --key <val> 參數。"""
    if isinstance(cmd_bags, CmdBags):
        return cmd_bags
    if isinstance(cmd_bags, (builtins.list, tuple)):
        value_option_names = {
            "status",
            "plan",
            "model",
            "scope",
            "note",
            "slug",
            "add",
            "remove",
            "rm",
            "phase",
            "log",
            "type",
            "transcript",
            "since",
            "limit",
            "year",
            "month",
            "path-plans",
            "path-archived",
            "path-docs",
            "path-roadmap",
            "target",
        }
        args = builtins.list(cmd_bags)
        raw_cmd = " ".join(str(x) for x in args)
        opts = {}
        pos = []
        i = 0
        n = len(args)
        while i < n:
            a = str(args[i])
            if a.startswith("--"):
                k = a[2:]
                v: Any = True
                if "=" in k:
                    k, val = k.split("=", 1)
                    v = val
                elif k in value_option_names and (i + 1) < n and not str(args[i + 1]).startswith("-"):
                    v = str(args[i + 1])
                    i += 1
                opts[k] = CmdOption(name=k, params=v)
            elif a.startswith("-") and len(a) > 1:
                k = a[1:]
                opts[k] = CmdOption(name=k, params=True)
            else:
                pos.append(a)
            i += 1
        return CmdBags(raw_cmd=raw_cmd, command=default_cmd, args=pos, options=opts)
    return CmdBags(raw_cmd="", command=default_cmd, args=[], options={})


def _get_str_option(bags: CmdBags, name: str, default: str = "") -> str:
    """安全提取字串選項值並去除首尾空白；若為布林旗標、空白或未設定則回傳 default。"""
    val = bags.get_option_value(name)
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned:
            return cleaned
    elif val is not None and not isinstance(val, bool):
        cleaned = str(val).strip()
        if cleaned:
            return cleaned
    return default


def roadmap_list(cmd_bags: Any) -> int:
    """列出路線圖摘要表格（支援 --status 過濾，自動排除 TODO.md）。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "roadmap_list")
    mgr = RoadmapManager()
    status_filter = _get_str_option(bags, "status") or None
    table_str = mgr.format_summary_table(status_filter=status_filter)
    _log_cli(table_str)
    return 0


def roadmap_promote(cmd_bags: Any) -> int:
    """將儲備路線圖物理移轉至計畫目錄並重命名為 roadmap.md (Consume-on-Promote)。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "roadmap_promote")
    if not bags.args:
        _log_cli("[agents-workflow:roadmap] Error: Missing topic to promote. Usage: roadmap promote <topic> [--plan <dir>] [--model <ModelName>]")
        return 1
    topic = bags.args[0]
    plan_dir = _get_str_option(bags, "plan") or None
    model_str = _get_str_option(bags, "model", "Unknown")

    mgr = RoadmapManager()
    res = mgr.promote_roadmap(topic_or_file=topic, model=model_str, target_plan=plan_dir)
    if not res.get("success", False):
        _log_cli(f"[agents-workflow:roadmap] [ERROR] {res.get('error', 'Failed to promote roadmap')}")
        return 1

    _log_cli(res.get("message", ""))
    return 0


def roadmap(cmd_bags: Any) -> int:
    """處理 `agents-workflow roadmap` CLI 指令（支援 list、promote 與單一主題查詢）。"""
    guard_dispatch("agents-workflow")
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
            _log_cli(f"[agents-workflow:roadmap] Roadmap topic '{first_arg}' not found in {mgr.roadmap_dir}.")
            return 1
        _log_cli(f"\n[agents-workflow:roadmap] Topic: {item.topic} ({item.status})")
        _log_cli(f"  * Path:    {item.path}")
        _log_cli(f"  * Date:    {item.date if item.date else 'N/A'}")
        _log_cli(f"  * Scope:   {item.scope}")
        _log_cli(f"  * Trigger: {item.trigger}")
        _log_cli(f"  * Title:   {item.title}")
        _log_cli(f"  * Summary: {item.problem_summary}")
        return 0
    else:
        return roadmap_list(bags)


def todo_add(cmd_bags: Any) -> int:
    """免讀盲寫追加單筆 TODO 條目至 workflow.roadmap://TODO.md。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "todo_add")
    if not bags.args:
        _log_cli("[agents-workflow:todo] Error: Missing title. Usage: todo add \"<標題>\" [--scope <模組>] [--note \"<備註>\"] [--model <ModelName>]")
        return 1
    title = " ".join(bags.args).strip()
    scope = _get_str_option(bags, "scope", "general")
    note = _get_str_option(bags, "note", "無")
    model_str = _get_str_option(bags, "model", "Unknown")

    mgr = TodoManager()
    try:
        item = mgr.add_todo(title=title, scope=scope, note=note, model=model_str)
    except Exception as ex:
        _log_cli(f"[agents-workflow:todo] [ERROR] {ex}")
        return 1
    _log_cli(f"[agents-workflow:todo] [SUCCESS] 已追加待辦條目 [{item.todo_id}]:")
    _log_cli(f"  * ID:      {item.todo_id}")
    _log_cli(f"  * Date:    {item.date}")
    _log_cli(f"  * Scope:   {item.scope}")
    _log_cli(f"  * Title:   {item.title}")
    _log_cli(f"  * Note:    {item.note}")
    return 0


def todo_list(cmd_bags: Any) -> int:
    """列出 workflow.roadmap://TODO.md 中之待辦條目（支援 --scope 過濾）。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "todo_list")
    scope = _get_str_option(bags, "scope") or None

    mgr = TodoManager()
    _log_cli(mgr.format_todo_table(scope_keyword=scope))
    return 0


def todo_promote(cmd_bags: Any) -> int:
    """支援單筆或多筆打包提取 TODO 條目 (Pop) 並生成 todo.md 與 changelog.md。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "todo_promote")
    if not bags.args:
        _log_cli("[agents-workflow:todo] Error: Missing TODO ID(s) to promote. Usage: todo promote <TODO-ID> [TODO-ID...] --slug <plan_slug> [--plan <dir>] [--model <ModelName>]")
        return 1
    slug = _get_str_option(bags, "slug") or None
    plan_dir = _get_str_option(bags, "plan") or None
    model_str = _get_str_option(bags, "model", "Unknown")

    mgr = TodoManager()
    res = mgr.promote_todos(todo_ids=bags.args, slug=slug, model=model_str, target_plan=plan_dir)
    if not res.get("success", False):
        _log_cli(f"[agents-workflow:todo] [ERROR] {res.get('error', 'Failed to promote todo(s)')}")
        return 1

    _log_cli(res.get("message", ""))
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
        _log_cli(f"[agents-workflow:todo] Unknown todo action '{action}'. Use add, list, or promote.")
        return 1


def release(cmd_bags: Any) -> int:
    """執行原子 4 步發布交易（支援 --force 與雙階 Diff 檢測）。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "release")
    force = bags.has_option("force") or bags.has_option("f")

    publisher = ReleasePublisher()
    _log_cli("[agents-workflow] Starting release transaction...")
    res = publisher.release_all(force=force)

    if res.get("success", False):
        if res.get("short_circuited", False):
            _log_cli(f"[agents-workflow] Release up to date (no changes detected, skipped {res.get('skipped_count', 0)} files).")
        else:
            _log_cli("[agents-workflow] Release completed successfully!")
            _log_cli(f"  * Written files:   {res.get('written_count', 0)}")
            _log_cli(f"  * Unchanged files: {res.get('skipped_count', 0)}")
            _log_cli(f"  * Total published: {res.get('published_count', 0)}")
        _log_cli(f"  * Active targets:  {', '.join(res.get('active_targets', []))}")
        if res.get("removed_count", 0) > 0:
            _log_cli(f"  * Pruned files:    {res.get('removed_count', 0)}")
        if res.get("orphan_targets"):
            _log_cli(f"  * Warning orphans: {', '.join(res.get('orphan_targets', []))}")
        return 0
    else:
        _log_cli("[agents-workflow] Release failed:")
        _log_cli(f"  - {res.get('error', 'Unknown error')}")
        for d in res.get("details", []):
            _log_cli(f"    * {d}")
        return 1


def release_target(cmd_bags: Any) -> int:
    """管理 release-target 清單與狀態（相容 --add/add 與 --remove/remove/--rm/rm，支援 --proj 旗標）。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "release-target")

    is_proj = bags.has_option("proj") or bags.has_option("project")
    tier_label = "PROJECT" if is_proj else "LOCAL"

    # 1. 優先判斷 Add 語法（支援 --add <t> 或 add <t>）
    add_tokens = ("add", "--add")
    is_add = bags.has_option("add") or (bool(bags.args) and bags.args[0] in add_tokens)
    if is_add:
        opt_val = _get_str_option(bags, "add")
        target_name = (
            opt_val
            or (bags.args[1].strip() if bags.args and bags.args[0] in add_tokens and len(bags.args) > 1 else "")
            or (bags.args[0].strip() if bags.args and bags.args[0] not in add_tokens else "")
        )
        if not target_name:
            _log_cli("[agents-workflow] Error: Missing target name for --add. Usage: release-target --add <target> [--proj]")
            return 1
        _log_cli(f"[agents-workflow] Adding release target '{target_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.add_target(target_name, is_project=is_proj)
        if ok:
            _log_cli(f"[agents-workflow] Target '{target_name}' enabled ({tier_label}) and released successfully.")
            return 0
        else:
            _log_cli(f"[agents-workflow] Failed enabling target '{target_name}' ({tier_label}).")
            return 1

    # 2. 優先判斷 Remove 語法（支援 --remove <t>、remove <t>、--rm <t> 或 rm <t>）
    remove_tokens = ("remove", "--remove", "rm", "--rm")
    is_remove = (
        bags.has_option("remove")
        or bags.has_option("rm")
        or (bool(bags.args) and bags.args[0] in remove_tokens)
    )
    if is_remove:
        opt_val = _get_str_option(bags, "remove") or _get_str_option(bags, "rm")
        target_name = (
            opt_val
            or (bags.args[1].strip() if bags.args and bags.args[0] in remove_tokens and len(bags.args) > 1 else "")
            or (bags.args[0].strip() if bags.args and bags.args[0] not in remove_tokens else "")
        )
        if not target_name:
            _log_cli("[agents-workflow] Error: Missing target name for --remove. Usage: release-target --remove <target> [--proj]")
            return 1
        _log_cli(f"[agents-workflow] Removing release target '{target_name}' ({tier_label}) and triggering atomic release...")
        ok = ReleaseTargetManager.remove_target(target_name, is_project=is_proj)
        if ok:
            _log_cli(f"[agents-workflow] Target '{target_name}' removed ({tier_label}) and cleaned successfully.")
            return 0
        else:
            _log_cli(f"[agents-workflow] Failed removing target '{target_name}' ({tier_label}).")
            return 1

    # 3. 預設行為：若指定 list 旗標或無其他動作，執行目標清冊輸出
    action = bags.args[0] if bags.args else None
    if not action or action in ("--list", "list", "-l") or bags.has_option("list") or bags.has_option("l"):
        targets = ReleaseTargetManager.list_targets()
        if not targets:
            _log_cli("[agents-workflow] No release targets found.")
            return 0
        _log_cli(f"\n[agents-workflow] Available Release Targets ({len(targets)}):")
        _log_cli("-" * 88)
        _log_cli(f"{'TARGET NAME':<20} {'STATUS':<26} {'DESCRIPTION'}")
        _log_cli("-" * 88)
        for t in targets:
            status_str = t["status"]
            _log_cli(f"{t['name']:<20} {status_str:<26} {t['description']}")
        _log_cli("-" * 88)
        return 0

    _log_cli(f"[agents-workflow] Unknown release-target option '{action}'. Use list, add <t> [--proj], or remove <t> [--proj].")
    return 1


def compile(cmd_bags: Any) -> int:
    """執行 Stage 1 中繼工廠編譯管線。"""
    guard_dispatch("agents-workflow")
    _normalize_bags(cmd_bags, "compile")
    compiler = ArtifactCompiler()
    _log_cli("[agents-workflow] Starting Stage 1 artifact compilation pipeline...")
    result = compiler.compile_stage1()

    if result["success"]:
        _log_cli("[agents-workflow] Stage 1 compilation completed successfully!")
        _log_cli(f"  * Cached files:    {len(result.get('resolved_items', []))}")
        _log_cli(f"  * Active inserts:  {result.get('inserted_count', 0)}")
        _log_cli(f"  * Known tokens:    {result.get('tokens_count', 0)}")
        return 0
    else:
        _log_cli("[agents-workflow] Stage 1 compilation failed with errors:")
        for err in result.get("errors", []):
            _log_cli(f"  - {err}")
        return 1


def tokens(cmd_bags: Any) -> int:
    """檢視全系統已註冊之 Token 錨點清單與語意 URI 說明。"""
    guard_dispatch("agents-workflow")
    _normalize_bags(cmd_bags, "tokens")
    compiler = ArtifactCompiler()
    tokens_list = compiler.get_registered_tokens()

    if not tokens_list:
        _log_cli("[agents-workflow] No registered tokens found.")
        return 0

    _log_cli(f"\n[agents-workflow] Registered Token Anchors ({len(tokens_list)}):")
    _log_cli("-" * 75)
    _log_cli(f"{'TOKEN NAME':<32} {'DESCRIPTION'}")
    _log_cli("-" * 75)
    for tok in tokens_list:
        val = tok.get("value") or tok.get("name") or ""
        desc = tok.get("description", "")
        _log_cli(f"{val:<32} {desc}")
    _log_cli("-" * 75)
    return 0


def list(cmd_bags: Any) -> int:
    """檢視當前已安裝模組清冊與 agents-workflow 導出規範清單。"""
    guard_dispatch("agents-workflow")
    _normalize_bags(cmd_bags, "list")
    compiler = ArtifactCompiler()
    exports = compiler.get_exported_artifacts()

    if not exports:
        _log_cli("[agents-workflow] No exported artifacts found.")
        return 0

    _log_cli(f"\n[agents-workflow] Exported Artifacts Catalog ({len(exports)}):")
    _log_cli("-" * 80)
    _log_cli(f"{'TYPE':<12} {'SOURCE URI / PATH':<45} {'DESCRIPTION'}")
    _log_cli("-" * 80)
    for exp in exports:
        t = exp.get("type", "template")
        src = exp.get("source", "")
        desc = compiler.resolve_export_description(exp)
        if "__${" in desc or "__#{" in desc:
            desc = compiler.resolve_stage2_uri(desc, "list", {})
        _log_cli(f"{t:<12} {src:<45} {desc}")
    _log_cli("-" * 80)
    return 0


def init(cmd_bags: Any) -> int:
    """一鍵初始化工作流目錄結構與 URI 協議。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "init")
    auto_confirm = bags.has_option("yes") or bags.has_option("y")
    paths_override: Dict[str, str] = {}

    for opt_key, cfg_key in (
        ("path-plans", "plans"),
        ("path-archived", "archived"),
        ("path-docs", "docs"),
        ("path-roadmap", "roadmap"),
    ):
        opt_val = _get_str_option(bags, opt_key)
        if opt_val:
            paths_override[cfg_key] = opt_val

    initializer = WorkflowInitializer()
    res = initializer.run_init_default(
        paths_override=paths_override,
        auto_confirm=auto_confirm,
        interactive=False,
    )
    return 0 if res.get("success", False) else 1


def plan_archive(cmd_bags: Any) -> int:
    """將已完成之 Dev Plan 安全歸檔至 workflow.archived://。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan_archive")
    if not bags.args:
        _log_cli("[agents-workflow:plan] Error: Missing plan name to archive. Usage: plan archive <plan_name> [--force]")
        return 1
    plan_name = bags.args[0]
    force = bags.has_option("force") or bags.has_option("f")

    archiver = PlanArchiver()
    try:
        res = archiver.archive_plan(plan_name, force=force)
        if res.get("cleaned_handoff"):
            _log_cli("  * [CLEANUP] 已清理暫時性交接快照：handoff.md")
        for w in res.get("warnings", []):
            _log_cli(f"  [WARNING] {w}")
        _log_cli(f"[agents-workflow:plan] [SUCCESS] 已成功將計畫歸檔至：{res.get('dest_path')}")
        return 0
    except PlansToolchainError as pe:
        _log_cli(f"[agents-workflow:plan] [ERROR] {pe}")
        return 1
    except Exception as ex:
        _log_cli(f"[agents-workflow:plan] [ERROR] 歸檔過程發生非預期錯誤：{ex}")
        return 1


def plan_status(cmd_bags: Any) -> int:
    """掃描並輸出進行中之 Dev Plans 狀態矩陣，或執行斷點領航與 handoff.md 原子閱後即焚 (--resume)。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan_status")
    scanner = PlanScanner()

    is_resume = bags.has_option("resume")
    target_plan = _get_str_option(bags, "plan") or (bags.args[0].strip() if bags.args and str(bags.args[0]).strip() else None)

    if is_resume or target_plan:
        if not is_resume:
            _log_cli(scanner.render_matrix_ascii())
        res = scanner.execute_resume(
            plan_name_or_subpath=target_plan,
            consume_handoff=is_resume,
        )
        if not res.get("success", False):
            _log_cli(scanner.render_matrix_ascii())
            _log_cli(res.get("formatted_output", ""))
            return 1
        _log_cli(res.get("formatted_output", ""))
        return 0

    matrix_str = scanner.render_matrix_ascii()
    _log_cli(matrix_str)
    return 0


def plan_search(cmd_bags: Any) -> int:
    """搜尋 Dev Plans 內部之決策紀錄 (DR) 或全文關鍵字。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan_search")
    is_dr = bags.has_option("dr")
    is_full = bags.has_option("full")
    is_json = bags.has_option("json")
    limit = 20 if not is_dr else 25
    year = _get_str_option(bags, "year") or None
    month = _get_str_option(bags, "month") or None

    l_opt = _get_str_option(bags, "limit")
    if l_opt:
        try:
            limit = int(l_opt)
        except ValueError:
            pass

    query = " ".join(bags.args)
    searcher = PlanSearcher()

    if is_dr or not query:
        drs = searcher.search_drs(query=query, year=year, month=month, limit=limit)
        if is_json:
            _log_cli(json.dumps(drs, indent=2, ensure_ascii=False))
            return 0
        _log_cli("=" * 90)
        _log_cli(f"{'Plan 名稱 / 來源檔案':<40} | {'DR ID / 標題':<22} | {'結論 / 摘要'}")
        _log_cli("=" * 90)
        for d in drs:
            raw_src = d["source_file"]
            raw_did = d["dr_id"]
            raw_sum = d["summary"]
            if is_full:
                _log_cli(f"{raw_src} | {raw_did} | {raw_sum}")
            else:
                src = raw_src if len(raw_src) <= 38 else "..." + raw_src[-35:]
                did = raw_did if len(raw_did) <= 20 else raw_did[:17] + "..."
                summ = raw_sum if len(raw_sum) <= 40 else raw_sum[:37] + "..."
                _log_cli(f"{src:<40} | {did:<22} | {summ}")
        _log_cli("=" * 90)
        _log_cli(f"共找到 {len(drs)} 筆 Decision Records。")
        return 0
    else:
        matches = searcher.search_full_text(query=query, year=year, month=month, limit=limit)
        if is_json:
            serializable = [
                {
                    "plan_name": m["plan_name"],
                    "file_path": str(m["file_path"]),
                    "rel_path": m["rel_path"],
                    "line_no": m["line_no"],
                    "matched_line": m["matched_line"],
                    "context": m.get("context", []),
                }
                for m in matches
            ]
            _log_cli(json.dumps(serializable, indent=2, ensure_ascii=False))
            return 0
        _log_cli(f"搜尋關鍵字: \"{query}\" ...")
        _log_cli("=" * 90)
        for m in matches:
            _log_cli(f"[{m['plan_name']}/{m['rel_path']}:L{m['line_no']}]")
            for l_no, l_text in m.get("context", []):
                prefix = " > " if l_no == m["line_no"] else "   "
                _log_cli(f"{prefix}{l_no:4d}: {l_text}")
            _log_cli("-" * 90)
        _log_cli(f"共找到 {len(matches)} 筆符合結果。")
        return 0


def plan_verify(cmd_bags: Any) -> int:
    """合規性診斷 Dev Plans 文件結構、雙檔協同、追溯差集與免讀盲寫追加 changelog.md。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan_verify")
    is_json = bags.has_option("json")
    target_name = bags.args[0] if bags.args else None

    phase_str = _get_str_option(bags, "phase", "all")
    log_msg = _get_str_option(bags, "log") or None
    log_type = _get_str_option(bags, "type", "PHASE")
    model_str = _get_str_option(bags, "model") or None

    verifier = PlanVerifier()

    if not target_name and (log_msg or phase_str.upper() not in ("ALL", "")):
        scanner = PlanScanner()
        t_dir, err_msg = scanner.resolve_target_plan_dir(None)
        if err_msg or t_dir is None:
            _log_cli(f"[agents-workflow:plan] [ERROR] {err_msg or '無法自動定位單一目標計畫，請明確傳入 <plan_name>。'}")
            return 1
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
        reports = verifier.verify_all_plans()

    if is_json:
        json_dict = {k: v.to_dict() for k, v in reports.items()}
        _log_cli(json.dumps(json_dict, indent=2, ensure_ascii=False))
        return 0 if all(r.passed for r in reports.values()) else 1

    _log_cli("=" * 70)
    _log_cli("YS-Codebase Dev Plan Compliance Diagnostic Report")
    _log_cli("=" * 70)

    total_plans = len(reports)
    passed_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.PASS)
    warn_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.WARN)
    fail_plans = sum(1 for r in reports.values() if r.status == PlanSeverity.FAIL)

    for p_name, r in reports.items():
        status_tag = f"[{r.status.value}]"
        _log_cli(f"[*] Plan: {p_name:<50} {status_tag}")
        if r.companion_created:
            _log_cli(f"    |-- [SELF-HEAL] 已自動初始化伴隨檔: {', '.join(r.companion_created)}")
        if r.header_healed:
            _log_cli(f"    |-- [SELF-HEAL] 已自動補齊確定性標頭: {', '.join(r.header_healed)}")
        if r.log_status == "appended":
            _log_cli(f"    |-- [CHANGELOG] 已免讀自動追加變更日誌列 (Type: {log_type.upper()})")
        elif r.log_status == "idempotent_skipped":
            _log_cli("    |-- [IDEMPOTENT] 變更日誌首列已存在相同 (類型, 摘要)，略過重複寫入")
        elif r.log_status == "skipped_on_fail":
            _log_cli("    |-- [BLOCKED] 因檢核存在 FAIL，已阻斷寫入 changelog.md")
        if r.status != PlanSeverity.PASS:
            for iss in r.issues:
                loc = f"{iss.file_name}:{iss.line_number}" if iss.line_number else iss.file_name
                _log_cli(f"    |-- [{iss.severity.value}] ({loc}) [{iss.category}] {iss.message}")
        if target_name and r.passed and r.next_phase_hint:
            _log_cli(f"    |-- [NEXT PHASE GATE] {r.next_phase_hint}")

    _log_cli("-" * 70)
    summary_str = f"Summary : {total_plans} Total, {passed_plans} Passed, {warn_plans} Warnings, {fail_plans} Failed"
    _log_cli(summary_str)
    overall_status = "PASSED" if fail_plans == 0 else "FAILED"
    _log_cli(f"Status  : {overall_status}")
    _log_cli("=" * 70)

    return 0 if fail_plans == 0 else 1


def plan(cmd_bags: Any) -> int:
    """Dev Plans 專案開發計畫管理工具鏈複合入口。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "plan")
    if not bags.args:
        return plan_status(bags)
    action = bags.args[0].lower()
    sub_bags = CmdBags(
        raw_cmd=bags.raw_cmd,
        command=f"plan_{action}",
        args=bags.args[1:],
        options=bags.options,
    )
    if action == "archive":
        return plan_archive(sub_bags)
    elif action == "status":
        return plan_status(sub_bags)
    elif action == "search":
        return plan_search(sub_bags)
    elif action == "verify":
        return plan_verify(sub_bags)
    else:
        _log_cli(f"[agents-workflow:plan] Unknown plan action '{action}'. Use archive, status, search, or verify.")
        return 1


def session_trace(cmd_bags: Any) -> int:
    """執行三級漸進式對話軌跡與五大硬性摩擦訊號提取 (供 /session-audit 調用)。"""
    guard_dispatch("agents-workflow")
    bags = _normalize_bags(cmd_bags, "session_trace")

    plan_arg = _get_str_option(bags, "plan") or (
        str(bags.args[0]).strip() if bags.args and str(bags.args[0]).strip() else None
    )
    transcript_arg = _get_str_option(bags, "transcript") or None

    opt_since = bags.get_option_value("since")
    since_min: Optional[float] = None
    if opt_since is not None and opt_since is not True:
        try:
            since_min = float(str(opt_since).strip())
        except ValueError:
            _log_cli(f"[agents-workflow:session-trace] Error: Invalid --since value '{opt_since}' (expected minutes).")
            return 1

    opt_limit = bags.get_option_value("limit")
    limit_val = 50
    if opt_limit is not None and opt_limit is not True:
        try:
            limit_val = max(1, int(str(opt_limit).strip()))
        except ValueError:
            _log_cli(f"[agents-workflow:session-trace] Error: Invalid --limit value '{opt_limit}' (expected integer).")
            return 1

    is_json = bags.has_option("json")
    is_list = bags.has_option("list") or bags.has_option("l")
    is_all = bags.has_option("all") or bags.has_option("a")

    engine = SessionTraceEngine()
    if is_list:
        from agents_workflow.plans._trace_renderer import render_session_list_text

        sessions = engine.list_sessions(
            include_all_workspaces=is_all,
            include_subagents=is_all,
            limit=limit_val if opt_limit is not None else 20,
        )
        if is_json:
            _log_cli(json.dumps(sessions, indent=2, ensure_ascii=False))
        else:
            _log_cli(render_session_list_text(sessions))
        return 0

    report = engine.analyze(
        plan_name_or_subpath=plan_arg,
        transcript_path=transcript_arg,
        since_minutes=since_min,
        limit=limit_val,
    )

    if plan_arg and report.target_plan is None and "找不到指定的計畫目錄" in report.plan_resolution_note:
        if is_json:
            _log_cli(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            _log_cli(f"[agents-workflow:session-trace] Error: {report.plan_resolution_note}")
        return 1

    if is_json:
        _log_cli(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _log_cli(report.render_text())
    return 0
