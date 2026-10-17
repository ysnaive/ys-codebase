# API 與介面規格書 (API & Interface Specification)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanStatusResolver` | `agents_workflow/plans/status.py` | Public | 專案計畫與 Markdown 文件之標頭狀態提取、正規化及完成度判定 (SSOT) |
| `PlanScanner.get_plan_info` | `agents_workflow/plans/scanner.py` | Public | 判定計畫之 Track 與當前狀態，支援 Research Track 與標頭驅動 Phase |
| `PlanArchiver.archive_plan` | `agents_workflow/plans/archiver.py` | Public | 安全歸檔，以標頭狀態確認 Completed/Concluded，防禦 handoff 誤刪 |
| `PlanVerifier._map_file_to_template` | `agents_workflow/plans/verifier.py` | Internal | 將計畫檔案映射至標準模板，支援 `^R\d{2}_.+\.md$` 調研檔案 |
| `PlanVerifier.get_dynamic_placeholders` | `agents_workflow/plans/verifier.py` | Internal | 動態自模板目錄提取標頭佔位符 pattern 清單 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# agents_workflow/plans/status.py

class PlanStatusResolver:
    """計畫文件標頭狀態提取與完成度解析服務 (SSOT)"""

    @staticmethod
    def parse_header_metadata(lines: List[str], max_lines: int = 35) -> Dict[str, str]:
        """
        自 Markdown 前 max_lines 行的 Blockquote (> 鍵：值) 解析元數據字典。
        鍵名統一轉為 lower()，去除全形空白與多餘引號。
        """
        ...

    @staticmethod
    def get_doc_header_status(doc_path: Path) -> str:
        """
        讀取單一 Markdown 文件標頭狀態。
        優先序: '狀態' -> 'status' -> '計畫狀態' -> '調研狀態' -> 'research_status' -> 'plan_status'。
        若無有效狀態欄位則回傳 'unknown'。
        回傳值一律正規化為小寫字串 (例如 'in progress', 'completed', 'concluded', 'confirmed', 'passed')。
        """
        ...

    @staticmethod
    def is_doc_completed(doc_path: Path) -> bool:
        """
        檢驗單一文件是否已完成結案。
        判斷其標頭狀態值是否屬於 {'completed', 'concluded', 'passed'}。
        嚴禁以全文或正文字串搜尋判定。
        """
        ...

    @staticmethod
    def is_research_completed(plan_dir: Path) -> bool:
        """
        檢驗 Research 計畫是否完成結案。
        搜尋所有符合 R\d{2}_*.md 的檔案，若至少有一份且全部 R 檔標頭狀態皆為 'concluded' (或 'completed') 則回傳 True。
        """
        ...
```

```python
# agents_workflow/plans/scanner.py

class PlanScanner:
    def get_plan_info(self, plan_dir: Path) -> Tuple[str, str]:
        """
        Track 模式優先序判定:
        1. Umbrella: umbrella_overview.md 存在 -> 狀態取其標頭 (若 unknown 則依 sub_* 狀態推導)
        2. Fast Track: fast_track_plan.md / FT_plan.md 存在 -> 狀態取其標頭
        3. Full Track: P01_requirements_spec.md 存在
           - P07_walkthrough.md 標頭為 completed -> "Completed"
           - P07_walkthrough.md 存在 -> "Reviewing/Phase 7"
           - P06_test_plan.md 存在 且 其標頭 in ("in progress", "passed", "completed") -> "Testing/Phase 6"
           - P05_task.md 存在 -> "Implementing/Phase 5"
           - P04_implementation_plan.md 存在 -> "Reviewing/Phase 4"
           - P03_api_spec.md 存在 -> "Designing/Phase 3"
           - P02_architecture_plan.md 存在 -> "Designing/Phase 2"
           - 其他 -> "Planning/Phase 1"
        4. Revision: revision_log.md 存在 (且無 P01/FT/Umbrella) -> 狀態取其標頭
        5. Research: 存在任一符合 R\d{2}_*.md 檔案 -> 若全部 R 檔為 concluded 則 "Concluded" 否則 "Draft"
        6. Phase 0: P00_discuss.md 存在 -> "P00 Confirmed" 或 "P00 Discussing"
        7. 檢查 handoff.md 且狀態非 Completed/Concluded -> 附加 " (Paused)"
        """
        ...
```

```python
# agents_workflow/plans/archiver.py

class PlanArchiver:
    def archive_plan(self, plan_name: str, force: bool = False) -> Dict:
        """
        歸檔流程守門:
        1. verifier.verify_plan() 合規檢核 (has_fails 阻斷)
        2. PlanStatusResolver 檢核主計畫狀態是否 Completed / Concluded
        3. 檢核所有附掛之 revision_log.md (根目錄與 sub_*) 是否 Completed
        4. 檢核 CHANGELOG.md 是否記載
        5. 目的地衝突防護: if dest_dir.exists(): raise PlanDestinationExistsError
        6. (目的地無衝突後) 清理 handoff.md: temp_handoff.unlink()
        7. 原子搬移: shutil.move(src_dir, dest_dir)
        """
        ...
```

```python
# agents_workflow/plans/verifier.py

class PlanVerifier:
    def _map_file_to_template(self, file_name: str) -> Optional[str]:
        # 新增正則判斷: if re.match(r"^R\d{2}_.+\.md$", base): return "RXX_research_report.md"
        ...

    def get_dynamic_placeholders(self) -> List[str]:
        # 讀取 self.templates_dir 下各 .md 檔案標頭 blockquote
        # 提取 \[([^\]\r\n]+)\] 匹配項，若包含 "|" 或中文字符則轉為正規化正則
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
拓撲順序 (DAG):
[1. status.py (PlanStatusResolver)] 
       ├──> [2. scanner.py 重構]
       ├──> [3. archiver.py 重構 & handoff 時序修正]
       └──> [4. verifier.py 正則收緊、動態佔位符、RXX 放寬、死代碼清理]
              └──> [5. 撰寫單元測試 tests/test_plans_status.py (FT-01 ~ FT-09)]
                     └──> [6. 資產庫文檔與模板全面同步 (FT-10 ~ FT-27)]
                            └──> [7. 靜態檢查 dev check 與全量測試 dev test (RT-01)]
```

---

## 4. 決策定稿 (Confirmed Decision Records)

- **[P03:DR-01] 標頭解析容錯鍵集**：狀態鍵優先比對 `狀態` 與 `status`，其次支援 `計畫狀態` 與 `調研狀態`。對於非狀態標籤之 blockquote 內容（如 `> 依據 P00：...`）嚴格忽略。
- **[P03:DR-02] Verifier 佔位符動態推導快取**：動態推導結果存於 `self._dynamic_placeholders_cache`，避免高頻重複磁碟 I/O。
- **[P03:DR-03] 測試 ID 嚴格正則邊界**：使用 `re.search(r"\b(FT|ET|RT)-\d{2}\b", l)` 判定測試編號，徹底排除 `FP-01`、`FP-02`、`FP-03` 等流程步驟關鍵字誤判。

