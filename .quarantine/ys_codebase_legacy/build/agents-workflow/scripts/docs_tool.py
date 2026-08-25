#!/usr/bin/env python3
"""
docs_tool.py — 專案知識庫 (docs/) 健康守護與按需輔助工具

職責：
1. init: 初始化 docs/ 根目錄與 _project/ 核心骨架
2. check-links / audit: 檢查 docs/ 內部 Markdown 相對路徑死鏈與 YAML Frontmatter 格式
3. new-topic: 按需快速套用範本生成專題手冊 (docs_topic.md)
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Any

SCRIPTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPTS_DIR.parent
TEMPLATES_DIR = MODULE_DIR / "workflows" / "templates" / "docs"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_utils import get_docs_dir, get_module_dir, get_workspace_root


def docs_init(target_docs_dir: Path = None) -> int:
    """初始化 docs/ 根目錄與全域知識地圖骨架"""
    module_dir = get_module_dir()
    docs_dir = target_docs_dir or get_docs_dir(module_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    project_dir = docs_dir / "_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    # 1. 建立 docs/README.md (Knowledge Map)
    readme_path = docs_dir / "README.md"
    if not readme_path.exists():
        template_map = TEMPLATES_DIR / "docs_global_index.md"
        if template_map.exists():
            readme_path.write_text(template_map.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            readme_path.write_text(
                "---\ntarget: \"Project/KnowledgeMap\"\ndoc_type: \"overview\"\nstatus: \"active\"\n---\n\n# 專案全域知識地圖\n",
                encoding="utf-8"
            )
        print(f"  [+] 已建立全域知識地圖: {readme_path}")
    else:
        print(f"  [INFO] 全域知識地圖已存在: {readme_path}")

    # 2. 建立 _project/ 基礎占位檔 (若不存在)
    for std_file in ["ARCHITECTURE.md", "STANDARDS.md", "CLI_SPECIFICATION.md"]:
        f_path = project_dir / std_file
        if not f_path.exists():
            f_path.write_text(f"---\ntarget: \"Project/{f_path.stem}\"\ndoc_type: \"readme\"\nstatus: \"draft\"\n---\n\n# {f_path.stem}\n", encoding="utf-8")
            print(f"  [+] 已建立核心公理檔案: {f_path}")

    print(f"[SUCCESS] 專案知識庫骨架初始化完成 ➔ {docs_dir}")
    return 0


def docs_new_topic(module_name: str, topic_name: str, target_docs_dir: Path = None) -> int:
    """按需快速生成專題技術手冊"""
    module_dir = get_module_dir()
    docs_dir = target_docs_dir or get_docs_dir(module_dir)
    mod_docs_dir = docs_dir / module_name
    mod_docs_dir.mkdir(parents=True, exist_ok=True)

    if not topic_name.endswith(".md"):
        topic_file_name = f"{topic_name}.md"
    else:
        topic_file_name = topic_name

    dest_file = mod_docs_dir / topic_file_name
    if dest_file.exists():
        print(f"[ERROR] 目標專題手冊已存在：{dest_file}")
        return 1

    template_topic = TEMPLATES_DIR / "docs_topic.md"
    if template_topic.exists():
        content = template_topic.read_text(encoding="utf-8")
        # 替換基礎識別
        content = content.replace("[Namespace/ModuleName/TopicName]", f"{module_name}/{Path(topic_file_name).stem}")
        content = content.replace("[ModuleName]", module_name)
    else:
        content = f"---\ntarget: \"{module_name}/{Path(topic_file_name).stem}\"\ndoc_type: \"topic\"\nstatus: \"draft\"\n---\n\n# {Path(topic_file_name).stem}\n"

    dest_file.write_text(content, encoding="utf-8")
    print(f"[SUCCESS] 已建立專題技術手冊 ➔ {dest_file}")
    return 0


def check_docs_health(target_docs_dir: Path = None) -> int:
    """檢查 docs/ 內部所有 Markdown 檔案的相對路徑死鏈與 Frontmatter 語法"""
    module_dir = get_module_dir()
    docs_dir = target_docs_dir or get_docs_dir(module_dir)

    if not docs_dir.exists():
        print(f"[INFO] 找不到知識庫目錄：{docs_dir}")
        return 0

    print("=" * 80)
    print(f"🔍 開始掃描知識庫健康度 (目標: {docs_dir}) ...")
    print("=" * 80)

    all_mds = list(docs_dir.rglob("*.md"))
    if not all_mds:
        print("[INFO] 目前知識庫內無任何 .md 檔案。")
        return 0

    broken_links_count = 0
    frontmatter_warnings = 0

    for md_path in sorted(all_mds):
        try:
            content = md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[ERROR] 無法讀取檔案 {md_path}: {e}")
            continue

        rel_doc_path = md_path.relative_to(docs_dir)

        # 1. Frontmatter 檢查
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = parts[1]
                if "target:" not in fm:
                    print(f"  ⚠️  [Frontmatter] {rel_doc_path} 缺少 'target:' 欄位")
                    frontmatter_warnings += 1
                if "status:" not in fm:
                    print(f"  ⚠️  [Frontmatter] {rel_doc_path} 缺少 'status:' 欄位")
                    frontmatter_warnings += 1
        else:
            print(f"  ⚠️  [Frontmatter] {rel_doc_path} 未包含 YAML Frontmatter 標頭")
            frontmatter_warnings += 1

        # 2. 相對路徑超連結死鏈檢查 [text](link)
        link_matches = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
        for link_text, link_target in link_matches:
            target_clean = link_target.strip()
            # 忽略外部連結、錨點、mail、自訂語意協議
            if (
                target_clean.startswith("http://")
                or target_clean.startswith("https://")
                or target_clean.startswith("mailto:")
                or target_clean.startswith("#")
                or "://" in target_clean
            ):
                continue

            # 去除錨點 #anchor
            pure_path_str = target_clean.split("#", 1)[0].strip()
            if not pure_path_str:
                continue

            target_resolved = (md_path.parent / pure_path_str).resolve()
            if not target_resolved.exists():
                print(f"  ❌ [Broken Link] {rel_doc_path}: 連結 [{link_text}]({target_clean}) 目標不存在 ➔ {target_resolved.name}")
                broken_links_count += 1

    print("=" * 80)
    print(f"📊 掃描完成：共檢查 {len(all_mds)} 份文檔。")
    print(f"   • 相對路徑死鏈 (Broken Links) : {broken_links_count} 處")
    print(f"   • Frontmatter 格式提示 (Warnings): {frontmatter_warnings} 處")
    print("=" * 80)

    if broken_links_count > 0:
        print("[FAIL] 偵測到無效超連結死鏈，請修復上述路徑。")
        return 1

    print("[SUCCESS] 知識庫超連結健康度 100% 正常！")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="專案知識庫健康守護與輔助工具")
    subparsers = parser.add_subparsers(dest="action", help="操作指令")

    # init
    init_p = subparsers.add_parser("init", help="初始化知識庫根目錄與全域地圖骨架")
    init_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    # check-links / audit
    audit_p = subparsers.add_parser("audit", help="檢查 docs/ 內部相對路徑死鏈與 Frontmatter")
    audit_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    check_p = subparsers.add_parser("check-links", help="[別名] 同 audit")
    check_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    # new-topic
    topic_p = subparsers.add_parser("new-topic", help="快速生成專題技術手冊範本")
    topic_p.add_argument("module", help="目標模組目錄名稱 (例: Core 或 Network)")
    topic_p.add_argument("topic", help="專題名稱 (例: lifecycle 或 protocol_spec)")
    topic_p.add_argument("--docs-dir", help="指定 docs 目錄路徑")

    args = parser.parse_args()

    custom_docs = Path(args.docs_dir).resolve() if getattr(args, "docs_dir", None) else None

    if args.action == "init":
        return docs_init(custom_docs)
    elif args.action in ["audit", "check-links"]:
        return check_docs_health(custom_docs)
    elif args.action == "new-topic":
        return docs_new_topic(args.module, args.topic, custom_docs)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
