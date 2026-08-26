"""
Release Target Manager for agents-workflow.
Manages release_targets configuration and lifecycle operations.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import json
from typing import List, Dict, Any, Tuple

try:
    from core import uri
except ImportError:
    uri = None

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher


class ReleaseTargetManager:
    """釋出目標組態管理器：負責 config.project.json 之 targets 讀寫。"""

    @classmethod
    def _get_config_path_and_data(cls) -> Tuple[str, Dict[str, Any]]:
        """獲取設定檔路徑與內容。"""
        cfg_uri = "config://agents-workflow/config.project.json"
        cfg_data = {
            "paths": {},
            "release_targets": ["antigravity"],
            "enable_agents_md": True,
            "enable_project_changelog": True
        }
        
        cfg_real_path = ""
        if uri:
            try:
                cfg_real_path = uri.resolve(cfg_uri, interactive=False)
            except Exception:
                pass

        if not cfg_real_path:
            cfg_real_path = os.path.join(os.getcwd(), "config", "agents-workflow", "config.project.json")

        if os.path.isfile(cfg_real_path):
            try:
                with open(cfg_real_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
            except Exception:
                pass

        return cfg_real_path, cfg_data

    @classmethod
    def _save_config_data(cls, cfg_real_path: str, cfg_data: Dict[str, Any]) -> None:
        """寫入設定檔。"""
        os.makedirs(os.path.dirname(cfg_real_path), exist_ok=True)
        with open(cfg_real_path, "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, indent=2, ensure_ascii=False)

    @classmethod
    def list_targets(cls) -> List[Dict[str, Any]]:
        """
        列出全系統可用 Targets，標註 [ENABLED], [DISABLED] 或 [ORPHAN / NOT FOUND]。
        """
        compiler = ArtifactCompiler()
        registered_targets = {t["name"]: t for t in compiler.get_release_targets() if "name" in t}
        
        _, cfg_data = cls._get_config_path_and_data()
        active_targets = set(cfg_data.get("release_targets", []))

        result: List[Dict[str, Any]] = []

        # 1. 遍歷已註冊 targets
        for name, t_obj in registered_targets.items():
            is_enabled = name in active_targets
            result.append({
                "name": name,
                "description": t_obj.get("description", ""),
                "enabled": is_enabled,
                "status": "[ENABLED]" if is_enabled else "[DISABLED]"
            })

        # 2. 檢查配置中但未註冊的 Orphan targets
        for name in active_targets:
            if name not in registered_targets:
                result.append({
                    "name": name,
                    "description": "(Unknown Target - definition not found in any module)",
                    "enabled": True,
                    "status": "[ORPHAN / NOT FOUND]"
                })

        return result

    @classmethod
    def add_target(cls, target_name: str) -> bool:
        """
        啟用 Target，更新 config.project.json 並自動觸發 release_all()。
        """
        cfg_path, cfg_data = cls._get_config_path_and_data()
        active_targets = list(cfg_data.get("release_targets", []))

        if target_name not in active_targets:
            active_targets.append(target_name)
            cfg_data["release_targets"] = active_targets
            cls._save_config_data(cfg_path, cfg_data)

        # 自動觸發發布流水線
        publisher = ReleasePublisher()
        res = publisher.release_all()
        return res.get("success", False)

    @classmethod
    def remove_target(cls, target_name: str) -> bool:
        """
        停用 Target，更新 config.project.json 並自動觸發 release_all()（清理舊檔案）。
        """
        cfg_path, cfg_data = cls._get_config_path_and_data()
        active_targets = list(cfg_data.get("release_targets", []))

        if target_name in active_targets:
            active_targets.remove(target_name)
            cfg_data["release_targets"] = active_targets
            cls._save_config_data(cfg_path, cfg_data)

        # 自動觸發發布流水線 (自動清理該 Target 舊檔案)
        publisher = ReleasePublisher()
        res = publisher.release_all()
        return res.get("success", False)
