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
    _resolve_uri_path,
)


class PlanArchiver:
    """開發計畫安全歸檔服務。"""

    def __init__(
        self,
        plans_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
    ):
        """
        初始化 PlanArchiver。
        
        Args:
            plans_dir: 進行中計畫目錄。若為 None 則透過 workflow.plans:// 解析。
            archive_dir: 歷史歸檔目錄。若為 None 則透過 workflow.archived:// 解析。
            project_root: 專案根目錄。若為 None 則透過 project:// 解析。
            templates_dir: 標準模板目錄（可選，供 PlanVerifier 使用）。
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

        self.templates_dir = Path(templates_dir).resolve() if templates_dir is not None else None
        self.verifier = None

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

        # 1. 執行 PlanVerifier 剛性合規檢核 (FR-07)
        from .verifier import PlanVerifier
        verifier = self.verifier or PlanVerifier(
            self.plans_dir, self.archive_dir, self.templates_dir
        )
        report = verifier.verify_plan(src_dir)
        if report.has_fails and not force:
            fail_msgs = "\n  - ".join(report.errors[:5])
            raise PlanIncompleteError(
                f"計畫 '{plan_name}' 存在未通過之檢核項目 ({len(report.errors)} 個重大錯誤 FAIL)，無法歸檔：\n  - {fail_msgs}\n若確定要強制歸檔，請使用 --force 參數。"
            )

        # 2. 檢查完成狀態
        from .status import PlanStatusResolver

        ft_plan = src_dir / "fast_track_plan.md"
        legacy_ft_plan = src_dir / "FT_plan.md"
        p07_walkthrough = PlanStatusResolver.resolve_phase_file(src_dir, "P07")
        umbrella_overview = src_dir / "umbrella_overview.md"
        rev_log = src_dir / "revision_log.md"

        is_completed = False
        for target_file in [ft_plan, legacy_ft_plan, p07_walkthrough, umbrella_overview, rev_log]:
            if target_file.exists() and PlanStatusResolver.is_doc_completed(target_file):
                is_completed = True
                break

        # 檢查是否為 Research Track 且完成
        if not is_completed:
            if PlanStatusResolver.is_research_completed(src_dir):
                is_completed = True

        warnings = []
        if not is_completed and not force:
            raise PlanIncompleteError(
                f"計畫 '{plan_name}' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。"
            )

        # 2.1 檢查所有存在之 revision_log.md（主目錄與 sub_* 子計畫）是否皆已標記 Completed
        all_rev_logs = []
        if rev_log.exists():
            all_rev_logs.append(rev_log)
        for sub_dir in sorted(src_dir.iterdir(), key=lambda x: x.name):
            if sub_dir.is_dir() and sub_dir.name.startswith("sub_"):
                sub_rev = sub_dir / "revision_log.md"
                if sub_rev.exists():
                    all_rev_logs.append(sub_rev)

        if not force:
            for r_file in all_rev_logs:
                if not PlanStatusResolver.is_doc_completed(r_file):
                    rel_r = r_file.relative_to(src_dir)
                    raise PlanIncompleteError(
                        f"計畫 '{plan_name}' 內存在尚未完成之修訂紀錄 '{rel_r}'（標頭未標記 Completed），為確保結案無遺漏，無法歸檔。若確定要強制歸檔，請使用 --force 參數。"
                    )

        # 3. 檢查全域 CHANGELOG.md 是否記載
        changelog_file = self.project_root / "CHANGELOG.md"
        if changelog_file.exists() and not force:
            cl_content = changelog_file.read_text(encoding="utf-8", errors="ignore")
            if plan_name not in cl_content:
                raise PlanIncompleteError(
                    f"專案根目錄 CHANGELOG.md 尚未包含此計畫 ({plan_name}) 的發布紀錄。若確定要略過檢查，請使用 --force 參數。"
                )

        # 4. 目的地衝突防護 (須優先於暫存檔案清理，防禦衝突時誤刪手動交接上下文)
        if dest_dir.exists():
            raise PlanDestinationExistsError(f"目標歷史歸檔目錄已存在相同名稱的計畫：{dest_dir}")

        # 5. 清理暫時性交接快照 (handoff.md)
        cleaned_handoff = False
        temp_handoff = src_dir / "handoff.md"
        if temp_handoff.exists():
            try:
                temp_handoff.unlink()
                cleaned_handoff = True
            except Exception as e:
                warnings.append(f"清理暫時交接快照失敗：{e}")

        # 6. 執行安全搬移
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
