"""
PlanArchiver — 開發計畫安全歸檔服務。
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import (
    PlanDestinationExistsError,
    PlanFormatError,
    PlanIncompleteError,
    PlanNotFoundError,
)
from ._common import evaluate_plan_completion, resolve_plan_uri


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
        self.plans_dir = (
            Path(plans_dir).resolve()
            if plans_dir is not None
            else resolve_plan_uri("workflow.plans://", "plans")
        )
        self.archive_dir = (
            Path(archive_dir).resolve()
            if archive_dir is not None
            else resolve_plan_uri("workflow.archived://", "plans/archived")
        )
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else resolve_plan_uri("project://", ".")
        )
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
        plan_name = (plan_name or "").strip().rstrip("/\\")
        if (
            not plan_name
            or "/" in plan_name
            or "\\" in plan_name
            or ".." in Path(plan_name).parts
        ):
            raise PlanNotFoundError(f"找不到指定的計畫目錄：{self.plans_dir / plan_name}")

        plans_root = self.plans_dir.resolve()
        src_dir = (plans_root / plan_name).resolve()
        if (
            src_dir.parent != plans_root
            or not src_dir.exists()
            or not src_dir.is_dir()
        ):
            raise PlanNotFoundError(f"找不到指定的計畫目錄：{src_dir}")

        match = re.match(r"^(\d{4})_(\d{2})_", plan_name)
        if not match:
            raise PlanFormatError(f"計畫名稱格式不符合規範（需以 YYYY_MM 開頭）：{plan_name}")

        year, month = match.group(1), match.group(2)
        dest_dir = self.archive_dir / year / month / plan_name

        # 1. 執行 PlanVerifier 剛性合規檢核
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

        # 2. 統一檢查主計畫、所有 sub_XX 子計畫及附掛之 revision_log.md 是否全數完成
        warnings: List[str] = []
        if not force:
            is_completed, block_reason = evaluate_plan_completion(src_dir)
            if not is_completed:
                raise PlanIncompleteError(
                    block_reason
                    or f"計畫 '{plan_name}' 尚未完成（未找到標頭 Completed/Concluded 標記）。若確定要強制歸檔，請使用 --force 參數。"
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

        # 5. 清理暫時性交接快照 (主目錄與所有 sub_* 子目錄之 handoff.md)
        cleaned_handoff = False
        handoff_targets: List[Path] = [src_dir / "handoff.md"]
        for sub_dir in sorted(src_dir.iterdir(), key=lambda x: x.name):
            if sub_dir.is_dir() and sub_dir.name.startswith("sub_"):
                handoff_targets.append(sub_dir / "handoff.md")

        from core import vfs

        for h_target in handoff_targets:
            if h_target.exists():
                try:
                    vfs.remove(str(h_target), missing_ok=True)
                    cleaned_handoff = True
                except Exception as e:
                    warnings.append(f"清理暫時交接快照失敗 ({h_target.name})：{e}")

        # 6. 執行安全搬移並對歸檔目錄施加唯讀鎖
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        vfs.move(str(src_dir), str(dest_dir))
        try:
            from core import file_lock as fl_mod

            fl_mod.lock_path(dest_dir, force=True, root_dir=self.project_root)
        except Exception:
            pass

        return {
            "success": True,
            "plan_name": plan_name,
            "source_path": src_dir,
            "dest_path": dest_dir,
            "cleaned_handoff": cleaned_handoff,
            "warnings": warnings,
            "error": None,
        }
