#!/usr/bin/env python3
"""
sync_workflow.py — Agent Workflow 中央標準庫雙向同步工具 (v1.0)

功能：
  - pull   : 從中央標準庫拉取最新通用 SOP、模板與腳本，並自動執行版本遷移與 AGENTS.md 核心區塊同步。
  - push   : 將本地對通用 SOP、模板與腳本的改動，提交並推回中央標準庫。
  - diff   : 比對本地通用檔案與中央庫的具體差異。
  - status : 檢查本地與中央標準庫的同步狀態。
  - init   : 為全新專案初始化 .agents/ 規範目錄並完成首次同步。
"""

import sys
import os
import shutil
import subprocess
import json
import fnmatch
import re
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DEFAULT_CORE_REPO = "https://github.com/YsNaive/agent.workflow.git"
DEFAULT_BRANCH = "main"
CURRENT_VERSION = "1.0"

DEFAULT_INCLUDE_PATTERNS = [
    "workflows/**",
    "scripts/**",
]

DEFAULT_EXCLUDE_PATTERNS = [
    "workflows/extensions/**",
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
                cfg = json.load(f)
                if "version" not in cfg:
                    cfg["version"] = "0.0"
                return cfg
        except Exception as e:
            print(f"[WARN] 讀取 .workflow_config.json 失敗: {e}，採用預設設定。")
    return {
        "version": "0.0",
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

# ── 版本遷移管線 (Version Migration Pipeline) ───────────────────────────

def migrate_v0_to_v1(agents_dir: Path, config: dict):
    print("[MIGRATE] 檢測到舊版工作流配置 (v0.0)，正在升級至 v1.0...")
    config["version"] = "1.0"
    config["sync_include"] = ["workflows/**", "scripts/**"]

    # 針對 v0.0 舊版具體檔名進行單次安全清理
    v0_legacy_files = [
        "workflows/DevelopmentSOP.md",
        "workflows/DevelopmentSOP_Continue.md",
        "workflows/DevelopmentSOP_Research.md",
        "workflows/DevelopmentSOP_Review.md",
        "workflows/ContextInit.md",
    ]
    for old_rel in v0_legacy_files:
        old_f = agents_dir / old_rel
        if old_f.exists():
            try:
                old_f.unlink()
                print(f"  - [MIGRATE] 已清理舊版更名檔案: {old_rel}")
            except Exception as e:
                print(f"  ! [MIGRATE WARN] 清理 {old_rel} 失敗: {e}")

    save_config(agents_dir, config)
    print("[MIGRATE] v0.0 -> v1.0 升級完成！\n")

MIGRATIONS = [
    ("0.0", "1.0", migrate_v0_to_v1),
]

def run_migrations(agents_dir: Path, config: dict):
    current_ver = config.get("version", "0.0")
    for from_v, to_v, handler in MIGRATIONS:
        if current_ver == from_v:
            handler(agents_dir, config)
            current_ver = to_v

# ── 檔案過濾與路徑匹配 ───────────────────────────────────────────────

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

# ── AGENTS.md 核心規則區塊混合同步 ─────────────────────────────────────

def sync_agents_md_core_block(agents_dir: Path, cache_dir: Path):
    local_agents = agents_dir / "AGENTS.md"
    template_agents = cache_dir / "workflows" / "templates" / "AGENTS.template.md"
    if not local_agents.exists() or not template_agents.exists():
        return

    local_text = local_agents.read_text(encoding="utf-8", errors="ignore")
    template_text = template_agents.read_text(encoding="utf-8", errors="ignore")

    start_marker = "<!-- CORE_RULES_BEGIN -->"
    end_marker = "<!-- CORE_RULES_END -->"

    if start_marker not in template_text or end_marker not in template_text:
        return

    tmpl_core = template_text.split(start_marker)[1].split(end_marker)[0]

    if start_marker in local_text and end_marker in local_text:
        before = local_text.split(start_marker)[0]
        after = local_text.split(end_marker)[1]
        new_local_text = f"{before}{start_marker}{tmpl_core}{end_marker}{after}"
        if new_local_text != local_text:
            local_agents.write_text(new_local_text, encoding="utf-8")
            print(f"  * [SYNC BLOCK] AGENTS.md 核心通用規則區塊已自動對齊更新，專案特化規範完好保留。")
    else:
        print(f"  💡 [提示] 本地 AGENTS.md 尚未標註 <!-- CORE_RULES_BEGIN --> 錨點，保留原檔未自動替換。")

# ── 指令操作 ──────────────────────────────────────────────────────────

def cmd_status(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    print("=" * 70)
    print("  Agent Workflow 同步狀態 (v1.0)")
    print("=" * 70)
    print(f"  工作目錄       : {agents_dir}")
    print(f"  配置版本       : {cfg.get('version', '0.0')}")
    print(f"  中央標準庫 URL : {cfg['core_repo']}")
    print(f"  目標分支       : {cfg['branch']}")
    print(f"  包含同步路徑   : {cfg.get('sync_include', DEFAULT_INCLUDE_PATTERNS)}")
    print(f"  排除保護路徑   : {cfg.get('sync_exclude', DEFAULT_EXCLUDE_PATTERNS)}")
    print("=" * 70)

def cmd_diff(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)
    cache_dir = ensure_cache_repo(agents_dir, cfg["core_repo"], cfg["branch"])
    includes = cfg.get("sync_include", DEFAULT_INCLUDE_PATTERNS)
    excludes = cfg.get("sync_exclude", DEFAULT_EXCLUDE_PATTERNS)

    print("=" * 70)
    print(f"  比對本地與中央庫 ({cfg['core_repo']} - {cfg['branch']}) 的差異")
    print("=" * 70)

    has_diff = False
    checked_paths = set()

    # 1. 檢查本地檔案（本地新增 vs 內容差異）
    for root, _, files in os.walk(agents_dir):
        if ".git" in root or ".cache_workflow_core" in root:
            continue
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(agents_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue

            checked_paths.add(rel_path)
            dest_file = cache_dir / rel_path
            if not dest_file.exists():
                print(f"[本地新增]   {rel_path}")
                has_diff = True
            else:
                c1 = src_file.read_text(encoding="utf-8", errors="ignore")
                c2 = dest_file.read_text(encoding="utf-8", errors="ignore")
                if c1 != c2:
                    print(f"[內容差異]   {rel_path}")
                    has_diff = True

    # 2. 檢查中央庫中存在但本地已刪除/更名之檔案
    for root, _, files in os.walk(cache_dir):
        if ".git" in root:
            continue
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(cache_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue
            if rel_path not in checked_paths:
                local_file = agents_dir / rel_path
                if not local_file.exists():
                    print(f"[本地已移除] {rel_path} (推送時將自中央庫同步移除)")
                    has_diff = True

    if not has_diff:
        print("  🎉 本地通用檔案與中央庫完全一致，無任何差異。")
    print("=" * 70)

def cmd_pull(args):
    agents_dir = get_agents_dir()
    cfg = load_config(agents_dir)

    # 執行版本遷移管線
    run_migrations(agents_dir, cfg)
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

    # 執行 AGENTS.md 核心區塊混合同步
    sync_agents_md_core_block(agents_dir, cache_dir)

    print("\n" + "=" * 60)
    print(f"  同步完成！新增: {created_count} 檔 | 更新: {synced_count} 檔")
    print(f"  [PROTECTED] 保護區 (dev_plans/extensions) 完好無損，未受更動。")
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

    # 檢查中央庫中存在但本地通用目錄已刪除/更名的檔案
    for root, _, files in os.walk(cache_dir):
        if ".git" in root:
            continue
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(cache_dir).as_posix()
            if not should_sync_file(rel_path, includes, excludes):
                continue
            local_counterpart = agents_dir / rel_path
            if not local_counterpart.exists():
                src_file.unlink()
                print(f"  -> [REMOVE FROM CORE] {rel_path}")
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
        "version": "1.0",
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
    parser = argparse.ArgumentParser(description="Agent Workflow 中央標準庫雙向同步工具 (v1.0)")
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
