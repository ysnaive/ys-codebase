#!/usr/bin/env python3
"""
config_utils.py — agents-workflow 模組設定檔與路徑解析工具 (基於 yscb_core)

職責：
  - 透過 yscb_core.ProjectContext 解析專案根目錄與計畫路徑
  - 透過 yscb_core.ConfigManager 讀寫 2×2 設定 (config.project.json / config.local.json)
  - 支援 plans_dir 與 archive_dir 解析
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
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
                break
    try:
        from yscb_core import ProjectContext, ConfigManager, Console
    except ImportError:
        # 極端降級 (Standalone fallback)
        ProjectContext = None
        ConfigManager = None
        Console = None

DEFAULT_PLANS_DIR = "plans"
DEFAULT_ARCHIVE_DIR = "archive_plans"
INHERIT_TOKEN = "__inherit__"


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


def load_global_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入專案級規範設定 (config.project.json / 兼容 config_global.json)"""
    if ConfigManager:
        return ConfigManager.get_project_config("agents-workflow", module_dir)
    m_dir = get_module_dir(module_dir)
    for name in ["config.project.json", "config.project.template.json", "config_global.json", "config_global.template.json"]:
        p = m_dir / name
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"plans_dir": DEFAULT_PLANS_DIR, "archive_dir": DEFAULT_ARCHIVE_DIR}


def load_local_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入本機個人偏好 (config.local.json / 兼容 config.json)"""
    if ConfigManager:
        return ConfigManager.get_user_config("agents-workflow", module_dir)
    m_dir = get_module_dir(module_dir)
    for name in ["config.local.json", "config.local.template.json", "config.json", "config.template.json"]:
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


def get_plans_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 儲存路徑"""
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", module_dir)
        raw_path = full_cfg.get("plans_dir", DEFAULT_PLANS_DIR)
        return ProjectContext.resolve(raw_path)

    m_dir = get_module_dir(module_dir)
    proj_root = get_workspace_root(m_dir)
    local_cfg = load_local_config(m_dir)
    global_cfg = load_global_config(m_dir)
    raw_path = local_cfg.get("plans_dir") or global_cfg.get("plans_dir") or DEFAULT_PLANS_DIR
    p = Path(raw_path)
    if not p.is_absolute():
        p = (proj_root / p).resolve()
    return p


def get_archive_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 歸檔路徑"""
    if ConfigManager and ProjectContext:
        full_cfg = ConfigManager.load("agents-workflow", module_dir)
        raw_path = full_cfg.get("archive_dir", DEFAULT_ARCHIVE_DIR)
        return ProjectContext.resolve(raw_path)

    m_dir = get_module_dir(module_dir)
    proj_root = get_workspace_root(m_dir)
    local_cfg = load_local_config(m_dir)
    global_cfg = load_global_config(m_dir)
    raw_path = local_cfg.get("archive_dir") or global_cfg.get("archive_dir") or DEFAULT_ARCHIVE_DIR
    p = Path(raw_path)
    if not p.is_absolute():
        p = (proj_root / p).resolve()
    return p
