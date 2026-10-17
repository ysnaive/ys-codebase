# API 與介面規格書 (API & Interface Specification)

> 功能名稱：修訂計畫 (Revision Plan) 正交化定位重構、留檔強制化與 SOP 邊界純化  
> 建立日期：2026-10-17  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanScanner.get_plan_info` | `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Public Method | 解析計畫目錄之 Track 與狀態；支援獨立 `revision_log.md` 識別為 `("Revision", status)`，且附掛於其他 Track 時維持原 Track 與狀態不變 |
| `PlanVerifier._map_file_to_template` | `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Internal Method | 將 `revision_log.md` 對齊至 `"revision_log.md"` 標準模板 |
| `PlanVerifier.get_resolved_template_headers` | `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Public Method | 提取標準模板之章節標題；略過 `[REV-XX]` 動態範例三級標題以允許實例化自由命名 |
| `PlanVerifier._verify_markdown_file` | `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Internal Method | 針對 `revision_log.md` 檢核標準標頭、佔位符、章節標題與至少一筆 `[REV-XX]` 條目 |
| `PlanArchiver.archive_plan` | `ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` | Public Method | 支援獨立 `revision_log.md` 完成判定，並強制檢核主計畫及 `sub_*` 下所有附掛 `revision_log.md` 皆為 `Completed` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. agents_workflow/plans/scanner.py
class PlanScanner:
    def get_plan_info(self, plan_dir: Path) -> Tuple[str, str]:
        """
        解析單一計畫目錄的 Track 與當前狀態。
        - Pre-conditions: plan_dir 為存在之計畫目錄 Path。
        - Post-conditions:
          1. 若存在 umbrella / fast_track / P01，優先依既有規則回傳對應 Track 與狀態（忽略同目錄下附掛之 revision_log.md）。
          2. 若不存在上述主體檔案，但存在 revision_log.md（無論是否同時存在 P00_discuss.md 或 RXX），回傳 ("Revision", status)。
          3. 若僅存在 P00_discuss.md，回傳 ("Phase 0", status)。
        """

# 2. agents_workflow/plans/verifier.py
class PlanVerifier:
    PLACEHOLDER_PATTERNS = [
        # ... 既有規則 + 新增:
        r"\[修訂主題簡述\]",
        r"\[UI/UX/DX\s*\|\s*Parameter\s*\|\s*Docs\]",
        r"\[檔案路徑\]",
    ]

    def _map_file_to_template(self, file_name: str) -> Optional[str]:
        """
        新增映射:
        elif base == "revision_log.md":
            return "revision_log.md"
        """

    def _verify_markdown_file(
        self, file_path: Path, rel_file_name: str, is_sub_plan: bool, report: PlanReport
    ) -> None:
        """
        新增針對 revision_log.md 之條目檢核:
        if rel_file_name.endswith("revision_log.md"):
            has_rev = any(re.search(r"\[REV-\d+\]", l) for l in lines)
            if not has_rev:
                report.issues.append(PlanIssue(
                    severity=PlanSeverity.FAIL,
                    file_name=rel_file_name,
                    category="ID_MATRIX",
                    message="'revision_log.md' 修訂紀錄清單缺少具備 '[REV-XX]' 前綴之修訂條目。"
                ))
        """

# 3. agents_workflow/plans/archiver.py
class PlanArchiver:
    def archive_plan(self, plan_name: str, force: bool = False) -> Dict:
        """
        安全歸檔守門擴充:
        - 完成依據擴充：將 src_dir / "revision_log.md" 納入主要完成狀態候選檔案。
        - 附掛修訂完畢守門：收集 [src_dir / "revision_log.md"] + list(src_dir.glob("sub_*/revision_log.md")) 中所有存在的檔案；
          若任一存在之 revision_log.md 未標記 Completed (且 not force)，拋出 PlanIncompleteError。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. 資產模板與導出宣告層
   ├── 新增 ys_codebase/source/agents-workflow/assets/templates/revision_log.md
   └── 註冊 ys_codebase/source/agents-workflow/contributes/agents-workflow.json (export)
2. Dev Plans 工具鏈核心邏輯層
   ├── scanner.py: 支援獨立 Revision 識別與附掛正交免疫
   ├── verifier.py: 支援 revision_log.md 模板映射、佔位符與 [REV-XX] 檢核
   └── archiver.py: 支援獨立與附掛 (含 sub_*) revision_log.md 完成狀態守門
3. SOP 與 Skills 規範重構與去特化層
   ├── development-sop/SKILL.md & references/{plan_modes,phase_00,phase_05,phase_06,phase_07}.md
   ├── skills/{new-plan,continue,auto}/SKILL.md
   └── 知識庫與 README 同步 (source/agents-workflow/README.md, docs/agents-workflow/*)
4. 單元測試、沙盒驗證與 Dogfooding 發布
   ├── tests/test_plans_toolchain.py (FT-11 ~ FT-13, ET-03)
   └── dev check -> dev test -> install agents-workflow@build --force -> agents-workflow release
```

