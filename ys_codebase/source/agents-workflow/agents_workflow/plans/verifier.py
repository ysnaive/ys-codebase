"""
PlanVerifier — 開發計畫規範與合規性稽核服務。
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict


def _resolve_uri_path(uri: str) -> Optional[Path]:
    """安全解析語意 URI，若無 core 上下文則回傳 None。"""
    try:
        from core.uri import resolve
        resolved = resolve(uri)
        return Path(resolved).resolve()
    except Exception:
        return None


class PlanVerifier:
    """開發計畫文件合規性稽核引擎。"""

    def __init__(
        self,
        plans_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
    ):
        """
        初始化 PlanVerifier。
        
        Args:
            plans_dir: 進行中計畫目錄。若為 None 則透過 workflow.plans:// 解析。
            archive_dir: 歷史歸檔目錄。若為 None 則透過 workflow.archived:// 解析。
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

    @staticmethod
    def parse_plan_header(lines: List[str]) -> Dict[str, str]:
        """結構化解析 Markdown 開頭 Blockquote (> 欄位：值) 中的 Header 元數據。"""
        headers = {}
        for line in lines[:35]:
            line_clean = line.strip().replace("\u3000", " ")
            if line_clean.startswith(">"):
                inner = line_clean.lstrip(">").strip()
                if "：" in inner:
                    k, v = inner.split("：", 1)
                    headers[k.strip().lower()] = v.strip()
                elif ":" in inner:
                    k, v = inner.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
        return headers

    def verify_single_file(self, file_path: Path) -> List[Dict[str, str]]:
        """
        稽核單一 Markdown 文件。
        
        Returns:
            List[Dict[str, str]]: [{"level": "ERROR" | "WARN", "msg": str}]
        """
        issues: List[Dict[str, str]] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return [{"level": "ERROR", "msg": f"無法讀取檔案：{e}"}]

        lines = content.splitlines()

        # 1. 檢查是否殘留 HTML AGENT_GUIDANCE 註解
        if "=== AGENT_GUIDANCE" in content or "AGENT_GUIDANCE" in content:
            issues.append({
                "level": "ERROR",
                "msg": "文件中殘留了 <!-- AGENT_GUIDANCE --> 模板指引註解，產出時未依規範過濾剝除。"
            })

        # 2. 檢查 Header 元數據
        headers = self.parse_plan_header(lines)
        has_name = any(k in headers for k in ["功能名稱", "計畫名稱", "name", "title"])
        has_date = any(k in headers for k in ["建立日期", "完成日期", "date", "created_at"])
        has_status = any(k in headers for k in ["狀態", "status"])

        if not has_name:
            issues.append({"level": "WARN", "msg": "Header 缺少 [功能名稱] 欄位"})
        if not has_date:
            issues.append({"level": "WARN", "msg": "Header 缺少 [建立日期] 欄位"})
        if not has_status:
            issues.append({"level": "ERROR", "msg": "Header 缺少 [狀態] 欄位"})

        return issues

    def verify_plan_directory(self, plan_dir: Path) -> Dict[str, List[Dict[str, str]]]:
        """
        遞迴稽核計畫目錄（包含主計畫與 sub_* 子計畫）。
        
        Returns:
            Dict[str, List[Dict]]: { "相對路徑/檔名.md": [issues...] }
        """
        results = {}
        if not plan_dir.exists() or not plan_dir.is_dir():
            return results

        # 稽核當前目錄下的 Markdown（排除 changelog.md 與 handoff.md）
        for md in sorted(plan_dir.glob("*.md")):
            if md.name in ["changelog.md", "handoff.md"]:
                continue
            file_issues = self.verify_single_file(md)
            results[md.name] = file_issues

        # 遞迴檢查子計畫
        for sub in sorted(plan_dir.iterdir(), key=lambda x: x.name):
            if sub.is_dir() and sub.name.startswith("sub_"):
                sub_res = self.verify_plan_directory(sub)
                for k, v in sub_res.items():
                    results[f"{sub.name}/{k}"] = v

        return results

    def verify(
        self,
        plan_name: Optional[str] = None,
        include_all: bool = False
    ) -> Dict:
        """
        執行整體合規性稽核任務。
        
        Args:
            plan_name: 指定稽核的計畫目錄名稱或相對路徑。若為 None 則掃描所有進行中計畫。
            include_all: 若為 True 且 plan_name 為 None，則一併掃描歷史歸檔。
            
        Returns:
            Dict: 稽核結果與統計
        """
        target_plans: List[Path] = []

        if plan_name:
            p = Path(plan_name)
            if not p.is_absolute():
                if (self.plans_dir / plan_name).is_dir():
                    p = self.plans_dir / plan_name
                elif (self.archive_dir / plan_name).is_dir():
                    p = self.archive_dir / plan_name
                else:
                    p = self.plans_dir / plan_name
            if p.exists() and p.is_dir():
                target_plans.append(p)
            else:
                return {
                    "success": False,
                    "error": f"找不到指定的計畫目錄：{plan_name}",
                    "plans_audited": 0,
                    "total_errors": 1,
                    "total_warns": 0,
                    "details": {},
                }
        else:
            if self.plans_dir.exists():
                for item in sorted(self.plans_dir.iterdir(), key=lambda x: x.name):
                    if item.is_dir() and not item.name.startswith("."):
                        target_plans.append(item)
            if include_all and self.archive_dir.exists():
                for y in sorted(self.archive_dir.iterdir(), key=lambda x: x.name):
                    if y.is_dir():
                        for m in sorted(y.iterdir(), key=lambda x: x.name):
                            if m.is_dir():
                                for p in sorted(m.iterdir(), key=lambda x: x.name):
                                    if p.is_dir() and not p.name.startswith("."):
                                        target_plans.append(p)

        total_errors = 0
        total_warns = 0
        plan_details = {}

        for plan in target_plans:
            plan_res = self.verify_plan_directory(plan)
            plan_details[plan.name] = plan_res
            for f_name, issues in plan_res.items():
                for iss in issues:
                    if iss["level"] == "ERROR":
                        total_errors += 1
                    else:
                        total_warns += 1

        return {
            "success": total_errors == 0,
            "error": None,
            "plans_audited": len(target_plans),
            "total_errors": total_errors,
            "total_warns": total_warns,
            "details": plan_details,
        }
