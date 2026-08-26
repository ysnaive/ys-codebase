"""
CLI Entry point for agents-workflow.
Commands:
  release                     - Execute 4-step atomic release transaction for all active targets
  release-target              - Manage release targets (--list, --add <target>, --remove <target>)
  compile (alias: build)      - Execute Stage 1 artifact factory resolution pipeline
  tokens                      - Inspect registered token anchors
  list                        - Inspect exported standards, workflows, and templates
  --init-default              - One-click workflow URI protocols and directories initialization
"""
import sys
import os
from typing import List, Dict

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


def cmd_release(args: List[str]) -> int:
    """執行原子 4 步發布交易。"""
    publisher = ReleasePublisher()
    print("[agents-workflow] Starting 4-step atomic release transaction...")
    res = publisher.release_all()
    
    if res.get("success", False):
        print(f"[agents-workflow] Release completed successfully!")
        print(f"  • Published files: {res.get('published_count', 0)}")
        print(f"  • Active targets:  {', '.join(res.get('active_targets', []))}")
        if res.get("removed_count", 0) > 0:
            print(f"  • Pruned files:    {res.get('removed_count', 0)}")
        if res.get("orphan_targets"):
            print(f"  • Warning orphans: {', '.join(res.get('orphan_targets', []))}")
        return 0
    else:
        print(f"[agents-workflow] Release failed:")
        print(f"  - {res.get('error', 'Unknown error')}")
        for d in res.get("details", []):
            print(f"    • {d}")
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
        print(f"  • Cached files:    {len(result.get('resolved_items', []))}")
        print(f"  • Active inserts:  {result.get('inserted_count', 0)}")
        print(f"  • Known tokens:    {result.get('tokens_count', 0)}")
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
    else:
        if "--init-default" in args:
            all_init_args = [a for a in args if a != "--init-default"]
            return cmd_init_default(all_init_args)
        print(f"[agents-workflow] Unknown command '{cmd}'. See --help.")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
