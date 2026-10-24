"""
PlanStatusResolver — 開發計畫標頭狀態解析與完成度檢測服務 (SSOT)。
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Union, Any


class PlanStatusResolver:
    """計畫文件標頭狀態提取與完成度解析服務 (SSOT)。"""

    STATUS_KEYS = [
        "狀態",
        "status",
        "計畫狀態",
        "plan_status",
        "調研狀態",
        "research_status",
        "進度",
        "當前所在階段",
    ]

    MODEL_KEYS = [
        "模型",
        "model",
        "ai_model",
        "ai-model",
        "模型名稱",
        "model_name",
    ]

    COMPLETED_STATUS_SET = {"completed", "concluded", "passed"}
    ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}

    @classmethod
    def parse_header_metadata(cls, lines: List[str], max_lines: int = 35) -> Dict[str, str]:
        """
        結構化解析 Markdown 開頭 Blockquote (> 欄位：值) 中的 Header 元數據。
        
        Args:
            lines: Markdown 行清單
            max_lines: 最大讀取行數 (預設 35)
            
        Returns:
            Dict[str, str]: 小寫欄位名與修剪後的字串字典
        """
        headers: Dict[str, str] = {}
        for line in lines[:max_lines]:
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

    @classmethod
    def get_doc_header_status(cls, doc_target: Union[Path, str]) -> str:
        """
        讀取單一 Markdown 文件標頭狀態。
        
        Args:
            doc_target: 文件檔案路徑 (Path/str) 或 Markdown 文字內容 (str)
            
        Returns:
            str: 正規化後之小寫狀態字串 (如 'in progress', 'completed', 'concluded' 等)，若無法解析則回傳 'unknown'。
        """
        content = ""
        if isinstance(doc_target, Path) or (isinstance(doc_target, str) and "\n" not in doc_target and Path(doc_target).exists()):
            p = Path(doc_target)
            if not p.is_file():
                return "unknown"
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return "unknown"
        elif isinstance(doc_target, str):
            content = doc_target
        else:
            return "unknown"

        try:
            lines = content.splitlines()[:35]
            headers = cls.parse_header_metadata(lines)

            for key in cls.STATUS_KEYS:
                if key in headers:
                    val = headers[key].strip()
                    # 排除未替換之模板佔位符如 [Draft | Confirmed ...]
                    if val.startswith("[") and val.endswith("]") and "|" in val:
                        return "unknown"
                    # 正規化常見同義詞
                    norm_val = val.lower()
                    if norm_val in ("in_progress", "implementing", "executing", "active"):
                        return "in progress"
                    return norm_val

            return "unknown"
        except Exception:
            return "unknown"

    @classmethod
    def is_doc_completed(cls, doc_target: Union[Path, str]) -> bool:
        """
        檢驗單一文件是否已完成結案 (依據標頭狀態)。
        
        Args:
            doc_target: 文件檔案路徑或文字內容
            
        Returns:
            bool: 若標頭狀態為 completed, concluded 或 passed 則為 True
        """
        status = cls.get_doc_header_status(doc_target)
        return status in cls.COMPLETED_STATUS_SET

    @classmethod
    def is_research_completed(cls, plan_dir_or_target: Union[Path, str]) -> bool:
        """
        檢驗 Research 計畫是否完成結案 (所有 R{NN}_*.md 檔案標頭皆為 concluded 或 completed)。
        
        Args:
            plan_dir_or_target: 計畫目錄路徑、單一檔案路徑或 Markdown 內容
            
        Returns:
            bool: 若為目錄且所有 R 檔完成，或為單一調研文件且已完成則為 True
        """
        if isinstance(plan_dir_or_target, Path) or (isinstance(plan_dir_or_target, str) and "\n" not in plan_dir_or_target and Path(plan_dir_or_target).exists()):
            p = Path(plan_dir_or_target)
            if p.is_dir():
                r_files = [
                    f for f in p.iterdir()
                    if f.is_file() and re.match(r"^R\d{2}_.+\.md$", f.name, re.IGNORECASE)
                ]
                if not r_files:
                    return False
                return all(cls.is_doc_completed(rf) for rf in r_files)
            elif p.is_file():
                return cls.is_doc_completed(p)

        return cls.is_doc_completed(plan_dir_or_target)

    @classmethod
    def get_doc_header_model(cls, doc_target: Union[Path, str]) -> str:
        """
        提取單一 Markdown 文件前 35 行 Blockquote 之 `> 模型：` 標頭值。
        排除未替換之 `[...]` 模板佔位符，若無法解析或為佔位符則回傳 'Unknown'。

        Args:
            doc_target: 文件檔案路徑 (Path/str) 或 Markdown 文字內容 (str)

        Returns:
            str: 模型名稱字串或 'Unknown'
        """
        content = ""
        if isinstance(doc_target, Path) or (
            isinstance(doc_target, str) and "\n" not in doc_target and Path(doc_target).exists()
        ):
            p = Path(doc_target)
            if not p.is_file():
                return "Unknown"
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return "Unknown"
        elif isinstance(doc_target, str):
            content = doc_target
        else:
            return "Unknown"

        try:
            lines = content.splitlines()[:35]
            headers = cls.parse_header_metadata(lines)
            for key in cls.MODEL_KEYS:
                if key in headers:
                    val = headers[key].strip()
                    if not val:
                        return "Unknown"
                    if val.startswith("[") and val.endswith("]"):
                        return "Unknown"
                    return val
            return "Unknown"
        except Exception:
            return "Unknown"

    @classmethod
    def resolve_next_action(cls, plan_dir: Union[Path, str]) -> Dict[str, Any]:
        """
        根據目標計畫目錄現有產物與標頭狀態，確定性推導當前階段、下一步行動與應讀 SOP 參考檔路徑。
        支援自動深入 Umbrella 活躍之 `sub_{編號}_{名稱}` 子目錄。

        Args:
            plan_dir: 目標計畫或子計畫目錄路徑

        Returns:
            Dict[str, Any]: 包含 target_plan_name, target_plan_dir, mode, current_phase,
                            current_status, next_phase, required_reference_path, next_action_hint, has_handoff
        """
        p = Path(plan_dir).resolve()
        ref_base = ".agents/skills/development-sop/references"
        sop_skill_path = ".agents/skills/development-sop/SKILL.md"

        if not p.exists() or not p.is_dir():
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Unknown",
                "current_phase": "Unknown",
                "current_status": "unknown",
                "next_phase": "Unknown",
                "required_reference_path": sop_skill_path,
                "next_action_hint": f"找不到計畫目錄：{p}",
                "has_handoff": False,
            }

        # 1. 若為 Umbrella 主計畫且尚未指定到 sub_XX，自動探測第一個未完成之活躍 sub_XX
        umbrella_file = p / "umbrella_overview.md"
        master_roadmaps = list(p.glob("master_plan_*.md"))
        if umbrella_file.exists() or len(master_roadmaps) > 0:
            sub_dirs = sorted(
                [d for d in p.iterdir() if d.is_dir() and d.name.startswith("sub_")],
                key=lambda x: x.name,
            )
            for sd in sub_dirs:
                sub_nav = cls.resolve_next_action(sd)
                if sub_nav["current_status"] not in ("completed", "concluded"):
                    sub_nav["target_plan_name"] = f"{p.name}/{sd.name}"
                    sub_nav["parent_umbrella_dir"] = p
                    sub_nav["has_handoff"] = (sd / "handoff.md").exists() or (p / "handoff.md").exists()
                    return sub_nav

            # 若無活躍子計畫（尚無 sub_XX 或全部 sub_XX 皆已完成）
            target_u = umbrella_file if umbrella_file.exists() else master_roadmaps[0]
            u_status = cls.get_doc_header_status(target_u)
            is_done = u_status in ("completed", "concluded")
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Umbrella",
                "current_phase": "Umbrella Root",
                "current_status": u_status,
                "next_phase": "Archived / Completed" if is_done else "Sub-Plan Creation or Umbrella Closure",
                "required_reference_path": f"{ref_base}/plan_modes.md",
                "next_action_hint": (
                    "主計畫已全數完成，可依指示執行 plan archive 歸檔。"
                    if is_done
                    else "檢視 umbrella_overview.md 子計畫矩陣，啟動下一個 sub_XX 子計畫或將主計畫標記為 Completed。"
                ),
                "has_handoff": (p / "handoff.md").exists(),
            }

        has_handoff = (p / "handoff.md").exists()

        # 2. Fast Track 判定
        ft_plan = p / "fast_track_plan.md"
        legacy_ft = p / "FT_plan.md"
        if ft_plan.exists() or legacy_ft.exists():
            target_ft = ft_plan if ft_plan.exists() else legacy_ft
            ft_status = cls.get_doc_header_status(target_ft)
            if ft_status in ("completed", "concluded"):
                cur_phase, nxt_phase = "FP-03", "Completed"
                hint = "Fast Track 計畫已結案 (Completed)，可依指示歸檔或建立 revision_log.md 修訂。"
            elif ft_status == "passed":
                cur_phase, nxt_phase = "FP-02", "FP-03"
                hint = "FP-02 實作與測試已通過，請推進至 FP-03 執行三層文檔核驗與 plan verify 結案。"
            elif ft_status == "in progress":
                cur_phase, nxt_phase = "FP-02", "FP-03"
                hint = "接續完成 fast_track_plan.md 中未勾選之實作任務與單元測試，通過後推進至 FP-03。"
            else:
                cur_phase, nxt_phase = "FP-01", "FP-02"
                hint = "確認 fast_track_plan.md 4 大守門條件後，進入 FP-02 編碼實作與測試。"
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Fast Track",
                "current_phase": cur_phase,
                "current_status": ft_status,
                "next_phase": nxt_phase,
                "required_reference_path": f"{ref_base}/plan_modes.md",
                "next_action_hint": hint,
                "has_handoff": has_handoff,
            }

        # 3. Full Track (P01 ~ P07) 判定
        p01_file = p / "P01_requirements_spec.md"
        if p01_file.exists():
            phase_specs = [
                ("P07", p / "P07_walkthrough.md", f"{ref_base}/phase_07_walkthrough.md"),
                ("P06", p / "P06_test_plan.md", f"{ref_base}/phase_06_test.md"),
                ("P05", p / "P05_task.md", f"{ref_base}/phase_05_task.md"),
                ("P04", p / "P04_implementation_plan.md", f"{ref_base}/phase_04_plan.md"),
                ("P03", p / "P03_api_spec.md", f"{ref_base}/phase_03_api_spec.md"),
                ("P02", p / "P02_architecture_plan.md", f"{ref_base}/phase_02_architecture.md"),
                ("P01", p01_file, f"{ref_base}/phase_01_requirements.md"),
            ]

            p07_f = p / "P07_walkthrough.md"
            p06_f = p / "P06_test_plan.md"
            p05_f = p / "P05_task.md"
            p04_f = p / "P04_implementation_plan.md"
            p03_f = p / "P03_api_spec.md"
            p02_f = p / "P02_architecture_plan.md"

            if p07_f.exists():
                st = cls.get_doc_header_status(p07_f)
                if st in ("completed", "concluded"):
                    return {
                        "target_plan_name": p.name,
                        "target_plan_dir": p,
                        "mode": "Full Track",
                        "current_phase": "P07",
                        "current_status": st,
                        "next_phase": "Completed",
                        "required_reference_path": f"{ref_base}/phase_07_walkthrough.md",
                        "next_action_hint": "Phase 7 已結案 (Completed)，可歸檔或建立 revision_log.md 進行後續修訂。",
                        "has_handoff": has_handoff,
                    }
                return {
                    "target_plan_name": p.name,
                    "target_plan_dir": p,
                    "mode": "Full Track",
                    "current_phase": "P07",
                    "current_status": st,
                    "next_phase": "P07",
                    "required_reference_path": f"{ref_base}/phase_07_walkthrough.md",
                    "next_action_hint": "讀取 phase_07_walkthrough.md，完成三層文檔對齊、勾選全部 Checkbox 並執行 plan verify 結案。",
                    "has_handoff": has_handoff,
                }

            # 注意：P06 在 P02 會建立 Draft、P04 定稿為 Confirmed，因此僅當 P05 已存在時才進入 P05/P06 階段判定
            if p05_f.exists():
                p05_st = cls.get_doc_header_status(p05_f)
                p06_st = cls.get_doc_header_status(p06_f) if p06_f.exists() else "unknown"
                if p06_f.exists() and p06_st in ("in progress", "passed", "completed"):
                    if p06_st == "completed":
                        return {
                            "target_plan_name": p.name,
                            "target_plan_dir": p,
                            "mode": "Full Track",
                            "current_phase": "P06",
                            "current_status": p06_st,
                            "next_phase": "P07",
                            "required_reference_path": f"{ref_base}/phase_07_walkthrough.md",
                            "next_action_hint": "Phase 6 已完成驗收，請先精讀 phase_07_walkthrough.md 進入 Phase 7 結案審查。",
                            "has_handoff": has_handoff,
                        }
                    return {
                        "target_plan_name": p.name,
                        "target_plan_dir": p,
                        "mode": "Full Track",
                        "current_phase": "P06",
                        "current_status": p06_st,
                        "next_phase": "P07" if p06_st == "passed" else "P06",
                        "required_reference_path": (
                            f"{ref_base}/phase_07_walkthrough.md"
                            if p06_st == "passed"
                            else f"{ref_base}/phase_06_test.md"
                        ),
                        "next_action_hint": (
                            "P06 自動化測試已 Passed，請等待開發者確認 UX 驗收後讀取 phase_07_walkthrough.md 進入 Phase 7。"
                            if p06_st == "passed"
                            else "讀取 phase_06_test.md 執行測試套件並回填 P06_test_plan.md。"
                        ),
                        "has_handoff": has_handoff,
                    }
                if p05_st in ("completed", "passed", "confirmed"):
                    return {
                        "target_plan_name": p.name,
                        "target_plan_dir": p,
                        "mode": "Full Track",
                        "current_phase": "P05",
                        "current_status": p05_st,
                        "next_phase": "P06",
                        "required_reference_path": f"{ref_base}/phase_06_test.md",
                        "next_action_hint": "Phase 5 實作已完成，請先精讀 phase_06_test.md 進入 Phase 6 測試驗證。",
                        "has_handoff": has_handoff,
                    }
                return {
                    "target_plan_name": p.name,
                    "target_plan_dir": p,
                    "mode": "Full Track",
                    "current_phase": "P05",
                    "current_status": p05_st,
                    "next_phase": "P05",
                    "required_reference_path": f"{ref_base}/phase_05_task.md",
                    "next_action_hint": "讀取 phase_05_task.md 與 P05_task.md 未勾選之 TASK-XX 接續編碼實作與單元測試。",
                    "has_handoff": has_handoff,
                }

            if p04_f.exists():
                st = cls.get_doc_header_status(p04_f)
                is_done = st in ("confirmed", "passed", "completed")
                return {
                    "target_plan_name": p.name,
                    "target_plan_dir": p,
                    "mode": "Full Track",
                    "current_phase": "P04",
                    "current_status": st,
                    "next_phase": "P05" if is_done else "P04",
                    "required_reference_path": (
                        f"{ref_base}/phase_05_task.md" if is_done else f"{ref_base}/phase_04_plan.md"
                    ),
                    "next_action_hint": (
                        "Phase 4 已定稿，請先精讀 phase_05_task.md 進入 Phase 5 建立 P05_task.md 並展開實作。"
                        if is_done
                        else "讀取 phase_04_plan.md 接續完成 P04 實作計畫與 P06 Confirmed 定稿。"
                    ),
                    "has_handoff": has_handoff,
                }

            if p03_f.exists():
                st = cls.get_doc_header_status(p03_f)
                is_done = st in ("confirmed", "passed", "completed")
                return {
                    "target_plan_name": p.name,
                    "target_plan_dir": p,
                    "mode": "Full Track",
                    "current_phase": "P03",
                    "current_status": st,
                    "next_phase": "P04" if is_done else "P03",
                    "required_reference_path": (
                        f"{ref_base}/phase_04_plan.md" if is_done else f"{ref_base}/phase_03_api_spec.md"
                    ),
                    "next_action_hint": (
                        "Phase 3 已完成，請先精讀 phase_04_plan.md 進入 Phase 4 實作計畫與 P06 定稿。"
                        if is_done
                        else "讀取 phase_03_api_spec.md 接續完成 P03 API 規格與 DAG 依賴拓撲。"
                    ),
                    "has_handoff": has_handoff,
                }

            if p02_f.exists():
                st = cls.get_doc_header_status(p02_f)
                is_done = st in ("confirmed", "passed", "completed")
                return {
                    "target_plan_name": p.name,
                    "target_plan_dir": p,
                    "mode": "Full Track",
                    "current_phase": "P02",
                    "current_status": st,
                    "next_phase": "P03" if is_done else "P02",
                    "required_reference_path": (
                        f"{ref_base}/phase_03_api_spec.md" if is_done else f"{ref_base}/phase_02_architecture.md"
                    ),
                    "next_action_hint": (
                        "Phase 2 已完成（確認 P06 Draft 已建立），請先精讀 phase_03_api_spec.md 進入 Phase 3。"
                        if is_done
                        else "讀取 phase_02_architecture.md 接續完成 P02 架構設計與 P06 Draft 初始化。"
                    ),
                    "has_handoff": has_handoff,
                }

            st = cls.get_doc_header_status(p01_file)
            is_done = st in ("confirmed", "passed", "completed")
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Full Track",
                "current_phase": "P01",
                "current_status": st,
                "next_phase": "P02" if is_done else "P01",
                "required_reference_path": (
                    f"{ref_base}/phase_02_architecture.md" if is_done else f"{ref_base}/phase_01_requirements.md"
                ),
                "next_action_hint": (
                    "Phase 1 已完成，請先精讀 phase_02_architecture.md 進入 Phase 2 架構設計與 P06 Draft 初始化。"
                    if is_done
                    else "讀取 phase_01_requirements.md 接續完成 P01 需求規格轉譯。"
                ),
                "has_handoff": has_handoff,
            }

        # 4. 獨立修訂計畫 (Revision) 判定
        rev_log = p / "revision_log.md"
        if rev_log.exists():
            st = cls.get_doc_header_status(rev_log)
            is_done = st in ("completed", "concluded")
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Revision",
                "current_phase": "Revision",
                "current_status": st,
                "next_phase": "Completed" if is_done else "Revision",
                "required_reference_path": f"{ref_base}/plan_modes.md",
                "next_action_hint": (
                    "Revision 修訂計畫已結案 (Completed)。"
                    if is_done
                    else "讀取 revision_log.md 接續完成 [REV-XX] 修訂並執行 plan verify 檢核。"
                ),
                "has_handoff": has_handoff,
            }

        # 5. Research 調研計畫判定
        r_files = sorted(
            [f for f in p.iterdir() if f.is_file() and re.match(r"^R\d{2}_.+\.md$", f.name, re.IGNORECASE)],
            key=lambda x: x.name,
        )
        if r_files:
            latest_r = r_files[-1]
            r_done = cls.is_research_completed(p)
            st = "concluded" if r_done else cls.get_doc_header_status(latest_r)
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Research",
                "current_phase": latest_r.stem.split("_")[0].upper(),
                "current_status": st,
                "next_phase": "Transition (P01 / Roadmap / Archive)" if r_done else latest_r.name,
                "required_reference_path": f"{ref_base}/plan_modes.md",
                "next_action_hint": (
                    "調研報告已 Concluded，請向開發者確認三大流轉出口（① 升級 P01 實作 | ② 路線圖儲備 | ③ 結案存檔）。"
                    if r_done
                    else f"接續撰寫調研報告 {latest_r.name} 並將標頭狀態更新為 Concluded。"
                ),
                "has_handoff": has_handoff,
            }

        # 6. Phase 0 討論階段判定
        p00_file = p / "P00_discuss.md"
        legacy_p00 = p / "P00_semantic_requirements.md"
        if p00_file.exists() or legacy_p00.exists():
            target_p00 = p00_file if p00_file.exists() else legacy_p00
            st = cls.get_doc_header_status(target_p00)
            is_done = st in ("confirmed", "passed", "completed")
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Phase 0",
                "current_phase": "P00",
                "current_status": st,
                "next_phase": "P01 (or Track Routing)" if is_done else "P00",
                "required_reference_path": (
                    f"{ref_base}/phase_01_requirements.md" if is_done else f"{ref_base}/phase_00_discuss.md"
                ),
                "next_action_hint": (
                    "P00 已確認 (Confirmed)，請先精讀 phase_01_requirements.md 進入 Phase 1 建立 P01_requirements_spec.md（或依分流建立對應軌道檔案）。"
                    if is_done
                    else "讀取 phase_00_discuss.md 接續與開發者釐清需求邊界並更新 P00_discuss.md。"
                ),
                "has_handoff": has_handoff,
            }

        # 7. 前置源頭背景資產 (Origin Seed Assets: roadmap.md / todo.md) 判定
        seed_files = [fn for fn in ("roadmap.md", "todo.md") if (p / fn).is_file()]
        if seed_files:
            return {
                "target_plan_name": p.name,
                "target_plan_dir": p,
                "mode": "Seeded",
                "current_phase": "Seeded",
                "current_status": "seeded",
                "next_phase": "P00 (or Fast Track / Revision)",
                "required_reference_path": f"{ref_base}/phase_00_discuss.md",
                "next_action_hint": (
                    f"目錄已含前置源頭資產 ({', '.join(seed_files)})，請讀取 phase_00_discuss.md（或 plan_modes.md）"
                    f"直接於本目錄原地建立 P00_discuss.md、fast_track_plan.md 或 revision_log.md，嚴禁重複新建第二個資料夾。"
                ),
                "has_handoff": has_handoff,
            }

        return {
            "target_plan_name": p.name,
            "target_plan_dir": p,
            "mode": "Unknown",
            "current_phase": "Pending",
            "current_status": "unknown",
            "next_phase": "P00",
            "required_reference_path": f"{ref_base}/phase_00_discuss.md",
            "next_action_hint": "目錄尚未建立標準階段檔案，請讀取 phase_00_discuss.md 初始化 P00_discuss.md。",
            "has_handoff": has_handoff,
        }


