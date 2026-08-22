#!/usr/bin/env python3
"""
config_utils.py — agents-workflow 模組設定檔與路徑解析工具

職責：
  - 讀取全域設定 (config_global.json / config_global.template.json)
  - 讀寫本地設定 (config.json / config.template.json)
  - 動態解析計畫儲存路徑 (plans_dir，預設由 config_global 定義為 ../../plans)
  - 動態解析歷史歸檔路徑 (archive_dir，預設由 config_global 定義為 ../../archive_plans)
  - 支援本地 config.json 以顯式自訂值覆寫全域設定，預設未設定或為 "__inherit__" 時繼承全域
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Any

DEFAULT_PLANS_DIR = "../../plans"
DEFAULT_ARCHIVE_DIR = "../../archive_plans"
INHERIT_TOKEN = "__inherit__"


def get_module_dir(current_path: Optional[Path] = None) -> Path:
    """自動推導 agents-workflow 模組根目錄（modules/agents-workflow 或 source/agents-workflow）"""
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
    """自動推導 YSCB 工具庫根目錄 (依 yscb_config.json 所在位置或環境變數 YSCB_ROOT)"""
    yscb_root_str = os.environ.get("YSCB_ROOT")
    if yscb_root_str:
        return Path(yscb_root_str).resolve()

    m_dir = get_module_dir(module_dir)
    cur = m_dir
    while cur != cur.parent:
        if (cur / "yscb_config.json").is_file():
            return cur.resolve()
        cur = cur.parent
    return m_dir.parent.parent.resolve()


def get_workspace_root(module_dir: Optional[Path] = None) -> Path:
    """自動推導專案根目錄 (優先使用 YSCB_PROJECT_ROOT，其次依 yscb_config.json 的 paths.project_root，最後降級至 {module_dir}/../..)"""
    proj_root_str = os.environ.get("YSCB_PROJECT_ROOT")
    if proj_root_str:
        return Path(proj_root_str).resolve()

    m_dir = get_module_dir(module_dir)
    cur = m_dir
    while cur != cur.parent:
        cfg_file = cur / "yscb_config.json"
        if cfg_file.is_file():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                rel_proj = cfg_data.get("paths", {}).get("project_root")
                if rel_proj:
                    return (cfg_file.parent / rel_proj).resolve()
            except Exception:
                pass
            return cur.resolve()
        cur = cur.parent

    return m_dir.parent.parent.resolve()


def load_global_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入模組全域設定 (config_global.json)，若不存在則降級讀取 config_global.template.json"""
    m_dir = get_module_dir(module_dir)
    global_cfg_path = m_dir / "config_global.json"
    global_tpl_path = m_dir / "config_global.template.json"

    if global_cfg_path.is_file():
        try:
            with open(global_cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if global_tpl_path.is_file():
        try:
            with open(global_tpl_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "plans_dir": DEFAULT_PLANS_DIR,
        "archive_dir": DEFAULT_ARCHIVE_DIR
    }


def load_local_config(module_dir: Optional[Path] = None) -> Dict[str, Any]:
    """載入本地運行期設定 (config.json)，若不存在則降級讀取 config.template.json"""
    m_dir = get_module_dir(module_dir)
    local_cfg_path = m_dir / "config.json"
    local_tpl_path = m_dir / "config.template.json"

    if local_cfg_path.is_file():
        try:
            with open(local_cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if local_tpl_path.is_file():
        try:
            with open(local_tpl_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "ide_integrations": {},
        "custom_module_settings": {}
    }


def save_local_config(config: Dict[str, Any], module_dir: Optional[Path] = None):
    """持久化儲存本地模組設定檔至 config.json"""
    m_dir = get_module_dir(module_dir)
    local_cfg_path = m_dir / "config.json"
    with open(local_cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_plans_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 儲存路徑（本地 config.json 若未設定或為 __inherit__ 則繼承全域 config_global，否則使用本地覆寫值）"""
    m_dir = get_module_dir(module_dir)
    local_cfg = load_local_config(m_dir)
    global_cfg = load_global_config(m_dir)

    local_val = local_cfg.get("plans_dir")
    if local_val is not None and local_val != INHERIT_TOKEN:
        raw_path = local_val
    else:
        raw_path = global_cfg.get("plans_dir") or DEFAULT_PLANS_DIR

    p = Path(raw_path)
    if not p.is_absolute():
        p = (m_dir / p).resolve()
    return p


def get_archive_dir(module_dir: Optional[Path] = None) -> Path:
    """取得 Plan 歸檔路徑（本地 config.json 若未設定或為 __inherit__ 則繼承全域 config_global，否則使用本地覆寫值）"""
    m_dir = get_module_dir(module_dir)
    local_cfg = load_local_config(m_dir)
    global_cfg = load_global_config(m_dir)

    local_val = local_cfg.get("archive_dir")
    if local_val is not None and local_val != INHERIT_TOKEN:
        raw_path = local_val
    else:
        raw_path = global_cfg.get("archive_dir") or DEFAULT_ARCHIVE_DIR

    p = Path(raw_path)
    if not p.is_absolute():
        p = (m_dir / p).resolve()
    return p
