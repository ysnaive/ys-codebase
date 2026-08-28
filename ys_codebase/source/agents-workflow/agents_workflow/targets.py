"""
Release Target Manager for agents-workflow.
Manages release_targets configuration across Local and Project tiers,
with Local as default and support for --proj flag.
100% Python Standard Library, Zero Third-Party Dependency.
"""

import os
import json
from typing import List, Dict, Any, Tuple, Optional

try:
    from core import uri
except ImportError:
    uri = None

try:
    from core import config
except ImportError:
    config = None

from agents_workflow.compiler import ArtifactCompiler
from agents_workflow.publisher import ReleasePublisher


class ReleaseTargetManager:
    """釋出目標組態管理器：負責 Local (Tier 1) 與 Project (Tier 2) targets 讀寫。"""

    DEFAULT_PROJECT_TARGETS = ["antigravity"]

    @classmethod
    def get_tier_targets(cls, is_project: bool = False) -> List[str]:
        """讀取特定層級 (Local 或 Project) 的 release_targets 清單。"""
        if config is None:
            return cls.DEFAULT_PROJECT_TARGETS if is_project else []
        try:
            default_val = cls.DEFAULT_PROJECT_TARGETS if is_project else []
            raw = config.get_raw("agents-workflow", "release_targets", local=not is_project, default=None)
            if raw is None:
                return list(default_val)
            if isinstance(raw, list):
                return list(raw)
            return list(default_val)
        except Exception:
            return cls.DEFAULT_PROJECT_TARGETS if is_project else []

    @classmethod
    def save_tier_targets(cls, targets: List[str], is_project: bool = False) -> None:
        """寫入特定層級的 release_targets 清單。"""
        if config is None:
            return
        try:
            config.set("agents-workflow", "release_targets", targets, local=not is_project)
        except Exception:
            pass

    @classmethod
    def list_targets(cls) -> List[Dict[str, Any]]:
        """
        列出全系統可用 Targets，標註來源狀態:
        [ENABLED (LOCAL)], [ENABLED (PROJECT)], [ENABLED (BOTH)], [DISABLED] 或 [ORPHAN / NOT FOUND]。
        """
        compiler = ArtifactCompiler()
        registered_targets = {t["name"]: t for t in compiler.get_release_targets() if "name" in t}

        proj_targets = set(cls.get_tier_targets(is_project=True))
        local_targets = set(cls.get_tier_targets(is_project=False))
        all_active = proj_targets | local_targets

        result: List[Dict[str, Any]] = []

        # 1. 遍歷已註冊 targets
        for name, t_obj in registered_targets.items():
            in_local = name in local_targets
            in_proj = name in proj_targets

            if in_local and in_proj:
                status = "[ENABLED (BOTH)]"
                source = "both"
                enabled = True
            elif in_local:
                status = "[ENABLED (LOCAL)]"
                source = "local"
                enabled = True
            elif in_proj:
                status = "[ENABLED (PROJECT)]"
                source = "project"
                enabled = True
            else:
                status = "[DISABLED]"
                source = "none"
                enabled = False

            result.append({
                "name": name,
                "description": t_obj.get("description", ""),
                "enabled": enabled,
                "source": source,
                "status": status,
            })

        # 2. 檢查配置中但未註冊的 Orphan targets
        for name in sorted(all_active):
            if name not in registered_targets:
                in_local = name in local_targets
                in_proj = name in proj_targets
                src_label = "BOTH" if (in_local and in_proj) else ("LOCAL" if in_local else "PROJECT")
                result.append({
                    "name": name,
                    "description": "(Unknown Target - definition not found in any module)",
                    "enabled": True,
                    "source": "orphan",
                    "status": f"[ORPHAN / NOT FOUND ({src_label})]",
                })

        return result

    @classmethod
    def add_target(cls, target_name: str, is_project: bool = False) -> bool:
        """
        啟用 Target，預設寫入 config.local.json (is_project=False)，加 --proj 寫入 config.project.json。
        自動觸發 ReleasePublisher.release_all()。
        """
        active_targets = cls.get_tier_targets(is_project=is_project)

        if target_name not in active_targets:
            active_targets.append(target_name)
            cls.save_tier_targets(active_targets, is_project=is_project)

        # 自動觸發發布流水線
        publisher = ReleasePublisher()
        res = publisher.release_all()
        return res.get("success", False)

    @classmethod
    def remove_target(cls, target_name: str, is_project: bool = False) -> bool:
        """
        停用 Target，預設從 config.local.json 移除，加 --proj 從 config.project.json 移除。
        自動觸發 ReleasePublisher.release_all()（清理檔案）。
        """
        active_targets = cls.get_tier_targets(is_project=is_project)

        if target_name in active_targets:
            active_targets.remove(target_name)
            cls.save_tier_targets(active_targets, is_project=is_project)

        # 自動觸發發布流水線 (自動清理該 Target 舊檔案)
        publisher = ReleasePublisher()
        res = publisher.release_all()
        return res.get("success", False)
