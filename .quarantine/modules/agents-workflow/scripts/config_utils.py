#!/usr/bin/env python3
"""
config_utils.py — agents-workflow 模組設定檔與路徑解析工具 (基於 yscb_core)

職責：
  - 透過 yscb_core.ProjectContext 解析專案根目錄與計畫路徑 (支援 !undefined 攔截)
  - 透過 yscb_core.ConfigManager 讀寫 2×2 設定 (config.project.json / config.local.json)
  - 支援 plans_dir, archive_dir, docs_dir 解析
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Optional, Any

# 嘗試匯入 yscb_core，若未載入則自動向上探測
try:
    from yscb_core import ProjectContext, ConfigManager, Console
except ImportError:
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        for candidate in [
            parent / "modules" / "core",
            parent / "source" / "core",
            parent / "ys_codebase" / "source" / "core",
            parent / "ys_codebase" / "build" / "core",
            parent / "ys_codebase" / "modules" / "core",
        ]:
            if (candidate / "scripts").is_dir() and str(candidate / "scripts") not in sys.path:
                sys.path.insert(0, str(candidate / "scripts"))
                break
            elif candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
                break
    try:
        from yscb_core import ProjectContext, ConfigManager, Console
    except ImportError:
        ProjectContext = None
        ConfigManager = None
        Console = None

DEFAULT_PLANS_DIR = "plans"
DEFAULT_ARCHIVE_DIR = "archive_plans"
DEFAULT_DOCS_DIR = "docs"
DEFAULT_EXTENSIONS_DIR = "extensions"
DEFAULT_AGENTS_MD_PATH = "AGENTS.md"

AGENTS_BEGIN_MARKER = "<!-- YSCB_AGENTS_BEGIN -->"
AGENTS_END_MARKER = "<!-- YSCB_AGENTS_END -->"


def is_undefined_value(val: Any) -> bool:
    if ProjectContext:
        return ProjectContext.is_undefined(val)
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.startswith("!")


def get_module_dir(current_path: Optional[Path] = None) -> Path:
    """自動推導 agents-workflow 模組根目錄"""
    if current_path:
        p = current_path.resolve()
        if p.is_dir():
            if p.name == "scripts":
                return p.parent
            return p
        if p.is_file():
            return p.parent.parent if p.parent.name == "scripts" else p.parent
    return Path(__file__).resolve().parent.parent


def get_yscb_root(module_dir: Optional[Path] = None) -> Path:
    """自動推導 YSCB 工具庫根目錄"""
    if ProjectContext:
        return ProjectContext.get_yscb_root(module_dir)
    m_dir = get_module_dir(module_dir)
    return m_dir.parent.parent.resolve()


def get_workspace_root(module_dir: Optional[Path] = None) -> Path:
    """自動推導專案根目錄"""
    if ProjectContext:
        return ProjectContext.get_project_root(module_dir)
    m_dir = get_module_dir(module_dir)
    return m_dir.parent.parent.resolve()


def load_project_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入專案級規範設定 (config.project.json)"""
    if ConfigManager:
        return ConfigManager.get_project_config("agents-workflow", module_dir)
    m_dir = get_module_dir(module_dir)
    for name in ["config.project.json", "config.project.template.json"]:
        p = m_dir / name
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"version": "1.0", "paths": {"plans_dir": "!undefined", "archive_dir": "!undefined", "docs_dir": "!undefined"}}


# 相容別名
load_global_config = load_project_config


def save_project_config(config: Dict[str, Any], module_dir: Optional[Path] = None):
    """持久化儲存專案級規範設定至 config.project.json (進 Git)"""
    if ConfigManager:
        ConfigManager.save_project_config("agents-workflow", config, module_dir)
    else:
        m_dir = get_module_dir(module_dir)
        with open(m_dir / "config.project.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")


def load_local_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入本機個人偏好 (config.local.json)"""
    if ConfigManager:
        return ConfigManager.get_user_config("agents-workflow", module_dir)
    m_dir = get_module_dir(module_dir)
    for name in ["config.local.json", "config.local.template.json"]:
        p = m_dir / name
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"ide_integrations": {}, "custom_user_settings": {}}


def save_local_config(config: Dict[str, Any], module_dir: Optional[Path] = None):
    """持久化儲存本機模組個人設定至 config.local.json (被 .gitignore 忽略)"""
    if ConfigManager:
        ConfigManager.save_user_config("agents-workflow", config, module_dir)
    else:
        m_dir = get_module_dir(module_dir)
        with open(m_dir / "config.local.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")


def _extract_path_setting(full_cfg: Dict[str, Any], key: str, default: str) -> str:
    # 支援 paths.<key> 與頂層 <key>
    paths = full_cfg.get("paths", {})
    if isinstance(paths, dict) and key in paths:
        return paths[key]
    return full_cfg.get(key, default)


def get_plans_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 儲存路徑 (若為 !undefined 則報錯阻斷)"""
    m_dir = get_module_dir(module_dir)
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", m_dir)
        raw_path = _extract_path_setting(full_cfg, "plans_dir", "!undefined")
        if is_undefined_value(raw_path):
            raise RuntimeError(
                "[ERROR] 模組 'agents-workflow' 尚未初始化 paths.plans_dir (!undefined)！\n"
                "  • 請執行: python yscb_cli.py agents-workflow init --default\n"
                "  • 或指定: python yscb_cli.py agents-workflow init --plans-dir plans"
            )
        return ProjectContext.resolve(raw_path)

    proj_root = get_workspace_root(m_dir)
    p_cfg = load_project_config(m_dir)
    raw_path = _extract_path_setting(p_cfg, "plans_dir", "!undefined")
    if is_undefined_value(raw_path):
        raise RuntimeError("[ERROR] 模組 'agents-workflow' 尚未初始化 paths.plans_dir (!undefined)！")
    p = Path(raw_path)
    return p if p.is_absolute() else (proj_root / p).resolve()


def get_archive_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 歸檔路徑 (若為 !undefined 則報錯阻斷)"""
    m_dir = get_module_dir(module_dir)
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", m_dir)
        raw_path = _extract_path_setting(full_cfg, "archive_dir", "!undefined")
        if is_undefined_value(raw_path):
            raise RuntimeError(
                "[ERROR] 模組 'agents-workflow' 尚未初始化 paths.archive_dir (!undefined)！\n"
                "  • 請執行: python yscb_cli.py agents-workflow init --default\n"
                "  • 或指定: python yscb_cli.py agents-workflow init --archive-dir archive_plans"
            )
        return ProjectContext.resolve(raw_path)

    proj_root = get_workspace_root(m_dir)
    p_cfg = load_project_config(m_dir)
    raw_path = _extract_path_setting(p_cfg, "archive_dir", "!undefined")
    if is_undefined_value(raw_path):
        raise RuntimeError("[ERROR] 模組 'agents-workflow' 尚未初始化 paths.archive_dir (!undefined)！")
    p = Path(raw_path)
    return p if p.is_absolute() else (proj_root / p).resolve()


def get_docs_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Docs 文檔路徑 (若為 !undefined 則報錯阻斷)"""
    m_dir = get_module_dir(module_dir)
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", m_dir)
        raw_path = _extract_path_setting(full_cfg, "docs_dir", "!undefined")
        if is_undefined_value(raw_path):
            raise RuntimeError(
                "[ERROR] 模組 'agents-workflow' 尚未初始化 paths.docs_dir (!undefined)！\n"
                "  • 請執行: python yscb_cli.py agents-workflow init --default\n"
                "  • 或指定: python yscb_cli.py agents-workflow init --docs-dir docs"
            )
        return ProjectContext.resolve(raw_path)

    proj_root = get_workspace_root(m_dir)
    p_cfg = load_project_config(m_dir)
    raw_path = _extract_path_setting(p_cfg, "docs_dir", "!undefined")
    if is_undefined_value(raw_path):
        raise RuntimeError("[ERROR] 模組 'agents-workflow' 尚未初始化 paths.docs_dir (!undefined)！")
    p = Path(raw_path)
    return p if p.is_absolute() else (proj_root / p).resolve()


def get_extensions_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Extension 擴充清單路徑 (若為 !undefined 則報錯阻斷，但若有 workflows/extensions 則容錯回退)"""
    m_dir = get_module_dir(module_dir)
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", m_dir)
        raw_path = _extract_path_setting(full_cfg, "extensions_dir", "!undefined")
        if not is_undefined_value(raw_path):
            proj_root = ProjectContext.get_project_root(m_dir)
            return ProjectContext.resolve(raw_path, base_dir=proj_root)
        # 若未指定，嘗試回退至模組內建 workflows/extensions
        fallback = m_dir / "workflows" / "extensions"
        if fallback.is_dir():
            return fallback
        raise RuntimeError(
            "[ERROR] 模組 'agents-workflow' 尚未初始化 paths.extensions_dir (!undefined)！\n"
            "  • 請執行: python yscb_cli.py agents-workflow init --default\n"
            "  • 或指定: python yscb_cli.py agents-workflow init --extensions-dir extensions"
        )

    proj_root = get_workspace_root(m_dir)
    p_cfg = load_project_config(m_dir)
    raw_path = _extract_path_setting(p_cfg, "extensions_dir", "!undefined")
    if not is_undefined_value(raw_path):
        p = Path(raw_path)
        return p if p.is_absolute() else (proj_root / p).resolve()
    fallback = m_dir / "workflows" / "extensions"
    if fallback.is_dir():
        return fallback
    raise RuntimeError("[ERROR] 模組 'agents-workflow' 尚未初始化 paths.extensions_dir (!undefined)！")


def get_agents_md_path(module_dir: Optional[Path] = None) -> Optional[Path]:
    """取得 agents_md_path 路徑 (若為 !undefined 或未設定則回傳 None)"""
    m_dir = get_module_dir(module_dir)
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", m_dir)
        raw_path = _extract_path_setting(full_cfg, "agents_md_path", "!undefined")
        if not is_undefined_value(raw_path):
            proj_root = ProjectContext.get_project_root(m_dir)
            return ProjectContext.resolve(raw_path, base_dir=proj_root)
        return None

    proj_root = get_workspace_root(m_dir)
    p_cfg = load_project_config(m_dir)
    raw_path = _extract_path_setting(p_cfg, "agents_md_path", "!undefined")
    if not is_undefined_value(raw_path):
        p = Path(raw_path)
        return p if p.is_absolute() else (proj_root / p).resolve()
    return None


def sync_agents_md(module_dir: Optional[Path] = None, target_path_override: Optional[str] = None) -> bool:
    """
    執行 AGENTS.md 軟合併同步 (Soft-Merge)：
    - 若無檔案：使用 AGENTS.template.md 建立新檔案
    - 若檔案具備 <!-- YSCB_AGENTS_BEGIN --> ~ <!-- YSCB_AGENTS_END -->：僅更新該區塊，保留外部自訂內容
    - 若檔案存在但不具備標記：輸出提示/警告，不進行覆寫
    """
    m_dir = get_module_dir(module_dir)
    proj_root = get_workspace_root(m_dir)
    
    if target_path_override:
        if is_undefined_value(target_path_override):
            return False
        if ProjectContext:
            target_file = ProjectContext.resolve(target_path_override, base_dir=proj_root)
        else:
            s = str(target_path_override).strip()
            if s.startswith("project://"):
                s = s[len("project://"):].lstrip("/\\")
            p = Path(s)
            target_file = p if p.is_absolute() else (proj_root / p).resolve()
    else:
        target_file = get_agents_md_path(m_dir)
        if not target_file:
            return False

    template_file = m_dir / "workflows" / "templates" / "AGENTS.template.md"
    if not template_file.is_file():
        print(f"[WARN] 找不到行為準則範本檔: {template_file}", file=sys.stderr)
        return False

    tpl_content = template_file.read_text(encoding="utf-8")

    # 擷取模板核心區塊
    if AGENTS_BEGIN_MARKER in tpl_content and AGENTS_END_MARKER in tpl_content:
        begin_idx = tpl_content.find(AGENTS_BEGIN_MARKER)
        end_idx = tpl_content.find(AGENTS_END_MARKER) + len(AGENTS_END_MARKER)
        tpl_block = tpl_content[begin_idx:end_idx]
    else:
        tpl_block = f"{AGENTS_BEGIN_MARKER}\n{tpl_content}\n{AGENTS_END_MARKER}"

    # 狀態 1：目標檔案不存在 ➔ 直接建立新檔案
    if not target_file.exists():
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(tpl_content, encoding="utf-8")
        print(f"[SUCCESS] 已依範本建立 AGENTS 行為準則文件 ➔ {target_file}")
        return True

    # 讀取既有目標檔案
    existing_content = target_file.read_text(encoding="utf-8")

    # 狀態 2：具備軟合併標記 ➔ 進行區塊替換
    if AGENTS_BEGIN_MARKER in existing_content and AGENTS_END_MARKER in existing_content:
        b_idx = existing_content.find(AGENTS_BEGIN_MARKER)
        e_idx = existing_content.find(AGENTS_END_MARKER) + len(AGENTS_END_MARKER)
        new_content = existing_content[:b_idx] + tpl_block + existing_content[e_idx:]
        target_file.write_text(new_content, encoding="utf-8")
        print(f"[SUCCESS] 已完成 AGENTS 行為準則核心區塊軟合併更新 ➔ {target_file}")
        return True

    # 狀態 3：檔案已存在但不具備標記 ➔ 提示開發者，不覆寫
    print(f"[WARN] 目標檔案已存在 ({target_file}) 但未包含 '{AGENTS_BEGIN_MARKER}' 軟合併標記，跳過自動覆寫。請手動於檔案中加入標記以啟用自動同步。")
    return False


