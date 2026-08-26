"""
PlanArchiver — 開發計畫安全歸檔服務。
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, Dict

from . import (
    PlanNotFoundError,
    PlanFormatError,
    PlanIncompleteError,
    PlanDestinationExistsError,
)


def _resolve_uri_path(uri: str) -> Optional[Path]:
    """安全解析語意 URI，若無 core 上下文則回傳 None。"""
    try:
        from core.uri import resolve
        resolved = resolve(uri)
        return Path(resolved).resolve()
    except Exception:
        return None


class PlanArchiver:
    """開發計畫安全歸檔服務。"""

    def __init__(
        self,
        plans_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
        project_root: Optional[Path] = None
    ):
        """
        初始化 PlanArchiver。
        
        Args:
            plans_dir: 進行中計畫目錄。若為 None 則透過 workflow.plans:// 解析。
            archive_dir: 歷史歸檔目錄。若為 None 則透過 workflow.archived:// 解析。
            project_root: 專案根目錄。若為 None 則透過 project:// 解析。
        """
        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            res_plans = _resolve_uri_path("workflow.plans://")
            self.plans_dir = res_plans if res_plans else Path.cwd() / "plans"

        if archive_dir is not None:
            self.archive_dir = Path(archive_dir).resolve()
        else:
            res_arch = _resolve_uri_path("workflow.archived://")
            self.archive_dir = res_arch if res_arch else Path.cwd() / "archive_plans"

        if project_root is not None:
            self.project_root = Path(project_root).resolve()
        else:
            res_proj = _resolve_uri_path("project://")
            self.project_root = res_proj if res_proj else Path.cwd()

    def archive_plan(self, plan_name: str, force: bool = False) -> Dict:
        """
        執行計畫安全歸檔操作。
        
        Args:
            plan_name: 計畫目錄名稱 (例如 2026_08_23_1505_feature_name)
            force: 若為 True，跳過完成狀態與 CHANGELOG 記載檢查
            
        Returns:
            Dict: 執行結果彙總
        """
        src_dir = self.plans_dir / plan_name
        if not src_dir.exists() or not src_dir.is_dir():
            raise PlanNotFoundError(f"找不到指定的計畫目錄：{src_dir}")

        # 解析時間戳前綴 YYYY_MM_
        match = re.match(r"^(\d{4})_(\d{2})_", plan_name)
        if not match:
            raise PlanFormatError(f"計畫名稱格式不符合規範（需以 YYYY_MM 開頭）：{plan_name}")

        year, month = match.group(1), match.group(2)
        dest_dir = self.archive_dir / year / month / plan_name

        # 1. 檢查完成狀態
        ft_plan = src_dir / "fast_track_plan.md"
        legacy_ft_plan = src_dir / "FT_plan.md"
        p07_walkthrough = src_dir / "P07_walkthrough.md"
        umbrella_overview = src_dir / "umbrella_overview.md"

        is_completed = False
        for target_file in [ft_plan, legacy_ft_plan, p07_walkthrough, umbrella_overview]:
            if target_file.exists():
                content = target_file.read_text(encoding="utf-8", errors="ignore")
                if (
                    "Completed" in content
                    or "狀態：Completed" in content
                    or "狀態: Completed" in content
                    or "status: completed" in content.lower()
                ):
                    is_completed = True
                    break

        warnings = []
        if not is_completed and not force:
            raise PlanIncompleteError(
                f"計畫 '{plan_name}' 尚未完成（未找到 Completed 標記）。若確定要強制歸檔，請使用 --force 參數。"
            )

        # 2. 檢查全域 CHANGELOG.md 是否記載
        changelog_file = self.project_root / "CHANGELOG.md"
        if changelog_file.exists() and not force:
            cl_content = changelog_file.read_text(encoding="utf-8", errors="ignore")
            if plan_name not in cl_content:
                raise PlanIncompleteError(
                    f"專案根目錄 CHANGELOG.md 尚未包含此計畫 ({plan_name}) 的發布紀錄。若確定要略過檢查，請使用 --force 參數。"
                )

        # 3. 清理暫時性交接快照 (handoff.md)
        cleaned_handoff = False
        temp_handoff = src_dir / "handoff.md"
        if temp_handoff.exists():
            try:
                temp_handoff.unlink()
                cleaned_handoff = True
            except Exception as e:
                warnings.append(f"清理暫時交接快照失敗：{e}")

        # 4. 目的地衝突防護
        if dest_dir.exists():
            raise PlanDestinationExistsError(f"目標歷史歸檔目錄已存在相同名稱的計畫：{dest_dir}")

        # 5. 執行安全搬移
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_dir), str(dest_dir))

        return {
            "success": True,
            "plan_name": plan_name,
            "source_path": src_dir,
            "dest_path": dest_dir,
            "cleaned_handoff": cleaned_handoff,
            "warnings": warnings,
            "error": None,
        }
