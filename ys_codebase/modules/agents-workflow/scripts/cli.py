"""
CLI Entry point for agents-workflow.
Commands:
  compile (alias: build)  - Execute artifact factory resolution pipeline
  tokens                  - Inspect registered token anchors
  list                    - Inspect exported standards, workflows, and templates
  --init-default          - One-click workflow URI protocols and directories initialization
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

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.initializer import WorkflowInitializer


def cmd_compile(args: List[str]) -> int:
    compiler = ArtifactCompiler()
    print("[agents-workflow] Starting artifact compilation pipeline...")
    result = compiler.compile_all()
    
    if result["success"]:
        print(f"[agents-workflow] Compilation completed successfully!")
        print(f"  • Exported files: {result['exported_count']}")
        print(f"  • Active inserts: {result['inserted_count']}")
        print(f"  • Known tokens:   {result['tokens_count']}")
        return 0
    else:
        print(f"[agents-workflow] Compilation failed with errors:")
        for err in result["errors"]:
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
        elif arg.startswith("--path-ext="):
            paths_override["ext"] = arg.split("=", 1)[1]
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
  compile, build              Run the artifact factory resolution and emit to exports/
  tokens                      List all registered token anchors and descriptions
  list                        List all declared export standards, workflows, and templates
  --init-default, init        One-click workflow URI protocols and directories initialization
    Options for --init-default:
      -y, --yes               Automatic confirmation mode without prompting
      --path-plans=<path>     Override recommended path for workflow.plans
      --path-archived=<path>  Override recommended path for workflow.archived
      --path-ext=<path>       Override recommended path for workflow.ext
      --path-docs=<path>      Override recommended path for workflow.docs
  --help, -h                  Show this help message
""")


def main(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    cmd = args[0].lower()
    sub_args = args[1:]

    # 若第一個參數即為 --init-default
    if cmd in ("--init-default", "init-default", "init"):
        return cmd_init_default(sub_args)
    elif cmd in ("compile", "build"):
        return cmd_compile(sub_args)
    elif cmd in ("tokens", "--list-token", "--list-tokens"):
        return cmd_tokens(sub_args)
    elif cmd in ("list", "--list"):
        return cmd_list(sub_args)
    else:
        # 檢查是否含有 --init-default 標誌
        if "--init-default" in args:
            all_init_args = [a for a in args if a != "--init-default"]
            return cmd_init_default(all_init_args)
        print(f"[agents-workflow] Unknown command '{cmd}'. See --help.")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
