#!/usr/bin/env python3
"""
sync_workflow.py — Agent Workflow 中央標準庫雙向同步工具

功能：
  - pull   : 從中央標準庫拉取最新通用 SOP、模板與腳本，覆蓋本地（保護區除外）。
  - push   : 將本地對通用 SOP、模板與腳本的改動，提交並推回中央標準庫。
  - diff   : 比對本地通用檔案與中央庫的具體差異。
  - status : 檢查本地與中央標準庫的同步狀態。
  - init   : 為全新專案初始化 .agents/ 規範目錄並完成首次同步。
"""

import sys
import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import os
import shutil
import subprocess
import json
import fnmatch
from pathlib import Path

DEFAULT_CORE_REPO = "https://github.com/YsNaive/agent.workflow.git"
DEFAULT_BRANCH = "main"

DEFAULT_INCLUDE_PATTERNS = [
    "workflows/DevelopmentSOP.md",
    "workflows/DevelopmentSOP_Continue.md",
    "workflows/DevelopmentSOP_Review.md",
    "workflows/DocumentationStandards.md",
    "workflows/templates/**",
    "workflows/extensions/ext_template.md",
    "scripts/**",
]

DEFAULT_EXCLUDE_PATTERNS = [
    "workflows/extensions/**",
    "workflows/ContextInit.md",
    "dev_plans/**",
    "ideas/**",
    "scratch/**",
    "AGENTS.md",
    ".workflow_config.json",
    ".cache_workflow_core/**",
    "__pycache__/**",
    "*.pyc",
]

def get_workspace_root() -> Path:
    cur = Path(__file__).resolve().parent
    while cur.parent != cur:
        if (cur / ".agents").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()

def get_agents_dir() -> Path:
    root = get_workspace_root()
    agents_dir = root / ".agents"
    if not agents_dir.exists():
        if (root / "workflows").is_dir() and (root / "scripts").is_dir():
            return root
        agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir

def load_config(agents_dir: Path) -> dict:
    cfg_file = agents_dir / ".workflow_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 讀取 .workflow_config.json 失敗: {e}，採用預設設定。")
    return {
        "core_repo": DEFAULT_CORE_REPO,
        "branch": DEFAULT_BRANCH,
        "sync_include": DEFAULT_INCLUDE_PATTERNS,
        "sync_exclude": DEFAULT_EXCLUDE_PATTERNS,
    }

def save_config(agents_dir: Path, config: dict):
    cfg_file = agents_dir / ".workflow_config.json"
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"[INFO] 已更新配置檔：{cfg_file}")

def is_matched(rel_path: str, patterns: list) -> bool:
    rel_normalized = rel_path.replace("\\", "/")
    for pattern in patterns:
        pat_normalized = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel_normalized, pat_normalized):
            return True
        if pat_normalized.endswith("/**"):
            prefix = pat_normalized[:-3]
            if rel_normalized.startswith(prefix):
                return True
        elif pat_normalized.endswith("/*"):
            prefix = pat_normalized[:-2]
            if rel_normalized.startswith(prefix) and "/" not in rel_normalized[len(prefix)+1:]:
                return True
    return False

def should_sync_file(rel_path: str, includes: list, excludes: list) -> bool:
    rel_normalized = rel_path.replace("\\", "/")
    if rel_normalized == "workflows/extensions/ext_template.md":
        return True
    if is_matched(rel_normalized, excludes):
        return False
    return is_matched(rel_normalized, includes)

def ensure_cache_repo(agents_dir: Path, repo_url: str, branch: str) -> Path:
    cache_dir = agents_dir / ".cache_workflow_core"
    if not cache_dir.exists() or not (cache_dir / ".git").is_dir():
        print(f"[INFO] 正在複製中央標準庫快取 ({repo_url})...")
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        res = subprocess.run(["git", "clone", "--branch", branch, repo_url, str(cache_dir)], capture_output=True, text=True)
        if res.returncode != 0:
            res2 = subprocess.run(["git", "clone", repo_url, str(cache_dir)], capture_output=True, text=True)
            if res2.returncode != 0:
                print(f"[ERROR] Clone 中央庫失敗：\n{res2.stderr}")
                sys.exit(1)
    else:
        subprocess.run(["git", "-C", str(cache_dir), "fetch", "origin"], capture_output=True)
        subprocess.run(["git", "-C", str(cache_dir), "checkout", branch], capture_output=True)
        subprocess.run(["git", "-C", str(cache_dir), "pull", "origin", branch], capture_output=True)
    return cache_dir

def cmd_status(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    print("=" * 70)
    print("  Agent Workflow 同步狀態")
    print("=" * 70)
    print(f"  工作目錄       : {agents_dir}")
    print(f"  中央庫 URL     : {cfg.get('core_repo', DEFAULT_CORE_REPO)}")
    print(f"  目標 Branch    : {cfg.get('branch', DEFAULT_BRANCH)}")
    cache_dir = ensure_cache_repo(agents_dir, cfg["core_repo"], cfg["branch"])
    res = subprocess.run(["git", "-C", str(cache_dir), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    head_sha = res.stdout.strip() if res.returncode == 0 else "Unknown"
    print(f"  中央庫最新 Commit: {head_sha}")
    print("=" * 70)

def cmd_diff(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    cache_dir = ensure_cache_repo(agents_dir, cfg["core_repo"], cfg["branch"])
    includes = cfg.get("sync_include", DEFAULT_INCLUDE_PATTERNS)
    excludes = cfg.get("sync_exclude", DEFAULT_EXCLUDE_PATTERNS)

    print(f"\n比對本地通用檔案與中央庫 ({cfg['core_repo']})...\n")
    diff_found = False

    for root, _, files in os.walk(cache_dir):
        if ".git" in root:
            continue
        for file in files:
            full_path = Path(root) / file
            rel_path = full_path.relative_to(cache_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue
            local_file = agents_dir / rel_path
            if not local_file.exists():
                print(f"[新增 (Remote Only)] {rel_path}")
                diff_found = True
            else:
                remote_content = full_path.read_text(encoding="utf-8", errors="ignore")
                local_content = local_file.read_text(encoding="utf-8", errors="ignore")
                if remote_content != local_content:
                    print(f"[差異 (Modified)]   {rel_path}")
                    diff_found = True

    for root, _, files in os.walk(agents_dir):
        if ".git" in root or ".cache_workflow_core" in root:
            continue
        for file in files:
            full_path = Path(root) / file
            rel_path = full_path.relative_to(agents_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue
            remote_file = cache_dir / rel_path
            if not remote_file.exists():
                print(f"[本地專屬 (Local Only)] {rel_path}")
                diff_found = True

    if not diff_found:
        print("[SUCCESS] 本地通用規範與中央標準庫完全一致，無任何差異。")
    print("")

def cmd_pull(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    cache_dir = ensure_cache_repo(agents_dir, cfg["core_repo"], cfg["branch"])
    includes = cfg.get("sync_include", DEFAULT_INCLUDE_PATTERNS)
    excludes = cfg.get("sync_exclude", DEFAULT_EXCLUDE_PATTERNS)

    print(f"\n開始從中央標準庫同步最新規範至本地：{agents_dir}\n")
    synced_count = 0
    created_count = 0
    protected_count = 0

    for root, _, files in os.walk(cache_dir):
        if ".git" in root:
            continue
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(cache_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                protected_count += 1
                continue

            dest_file = agents_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            is_new = not dest_file.exists()
            content_src = src_file.read_text(encoding="utf-8", errors="ignore")
            content_dest = dest_file.read_text(encoding="utf-8", errors="ignore") if not is_new else ""

            if is_new or content_src != content_dest:
                shutil.copy2(str(src_file), str(dest_file))
                if is_new:
                    print(f"  + [NEW]     {rel_path}")
                    created_count += 1
                else:
                    print(f"  * [UPDATED] {rel_path}")
                    synced_count += 1

    print("\n" + "=" * 60)
    print(f"  同步完成！新增: {created_count} 檔 | 更新: {synced_count} 檔")
    print(f"  [PROTECTED] 保護區 (dev_plans/extensions/AGENTS.md) 完好無損，未受任何更動。")
    
    agents_file = agents_dir / "AGENTS.md"
    template_file = agents_dir / "workflows" / "templates" / "AGENTS.template.md"
    if agents_file.exists() and template_file.exists():
        print("  💡 [提示] 本地 AGENTS.md 受到特化保護未被覆蓋。")
        print("     若中央庫有更新運行鐵則，建議參閱 .agents/workflows/templates/AGENTS.template.md")
        print("     並手動將最新鐵則同步至本地 AGENTS.md。")
    print("=" * 60 + "\n")

def cmd_push(args):
    commit_msg = args.message
    if not commit_msg:
        print("[ERROR] 請提供 commit 訊息，例如：python sync_workflow.py push -m '優化 Phase 4 Review 流程'")
        sys.exit(1)

    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    cache_dir = ensure_cache_repo(agents_dir, cfg["core_repo"], cfg["branch"])
    includes = cfg.get("sync_include", DEFAULT_INCLUDE_PATTERNS)
    excludes = cfg.get("sync_exclude", DEFAULT_EXCLUDE_PATTERNS)

    print(f"\n正在將本地通用修改同步至中央標準庫 ({cfg['core_repo']})...\n")
    modified_count = 0

    for root, _, files in os.walk(agents_dir):
        if ".git" in root or ".cache_workflow_core" in root:
            continue
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(agents_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue

            dest_file = cache_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            is_new = not dest_file.exists()
            content_src = src_file.read_text(encoding="utf-8", errors="ignore")
            content_dest = dest_file.read_text(encoding="utf-8", errors="ignore") if not is_new else ""

            if is_new or content_src != content_dest:
                shutil.copy2(str(src_file), str(dest_file))
                print(f"  -> [SYNC TO CORE] {rel_path}")
                modified_count += 1

    if modified_count == 0:
        print("[INFO] 本地通用檔案無任何變更，無需推送。")
        return

    subprocess.run(["git", "-C", str(cache_dir), "add", "-A"], check=True)
    res_commit = subprocess.run(["git", "-C", str(cache_dir), "commit", "-m", commit_msg], capture_output=True, text=True)
    print(res_commit.stdout)
    res_push = subprocess.run(["git", "-C", str(cache_dir), "push", "origin", cfg["branch"]], capture_output=True, text=True)
    if res_push.returncode != 0:
        print(f"[ERROR] 推送至遠端中央庫失敗：\n{res_push.stderr}")
        sys.exit(1)
    print(f"[SUCCESS] 成功將 {modified_count} 個通用檔案推回中央庫 ({cfg['core_repo']} - {cfg['branch']})！\n")

def cmd_init(args):
    repo_url = args.repo or DEFAULT_CORE_REPO
    agents_dir = get_agents_dir()
    cfg = {
        "core_repo": repo_url,
        "branch": DEFAULT_BRANCH,
        "sync_include": DEFAULT_INCLUDE_PATTERNS,
        "sync_exclude": DEFAULT_EXCLUDE_PATTERNS,
    }
    save_config(agents_dir, cfg)
    cmd_pull(args)
    
    agents_file = agents_dir / "AGENTS.md"
    template_file = agents_dir / "workflows" / "templates" / "AGENTS.template.md"
    if not agents_file.exists() and template_file.exists():
        shutil.copy2(str(template_file), str(agents_file))
        print(f"  + [INIT] 已從模板初始化專案專屬規範檔：{agents_file}\n")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent Workflow 中央標準庫雙向同步工具")
    subparsers = parser.add_subparsers(dest="command", help="子指令")

    subparsers.add_parser("status", help="檢查同步狀態")
    subparsers.add_parser("diff", help="比對本地通用檔案與中央庫的差異")
    subparsers.add_parser("pull", help="從中央庫拉取最新規範")
    
    p_push = subparsers.add_parser("push", help="將本地通用修改推回中央庫")
    p_push.add_argument("-m", "--message", type=str, required=True, help="Git Commit 說明訊息")

    p_init = subparsers.add_parser("init", help="初始化專案的 .agents/ 規範並拉取最新核心庫")
    p_init.add_argument("repo", nargs="?", default=DEFAULT_CORE_REPO, help="中央庫 Git URL")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        cmd_status(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "pull":
        cmd_pull(args)
    elif args.command == "push":
        cmd_push(args)
    elif args.command == "init":
        cmd_init(args)

if __name__ == "__main__":
    main()
