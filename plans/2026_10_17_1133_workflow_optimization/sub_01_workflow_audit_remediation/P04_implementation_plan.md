# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-27 在架構設計 (P02) 與 API 規格 (P03) 中皆具備清晰的類別、函式或文檔改動對齊
- [x] **邊界防護**：EC-01 ~ EC-13 均有具體防禦處置（包含標頭缺失回退、正文含 Completed 防干擾、目的地衝突保護等）
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-05 指標約束，無引入任何第三方新依賴，僅使用標準函式庫 `re`, `os`, `pathlib`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新 Fast Track 步驟名稱 (FP-01~03)、Research 一等公民與狀態解析規範 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-17]` 標頭狀態解析唯一真理與動態模板佔位符推導 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本修訂重大改動摘要 |
| **微觀註解** | `agents_workflow/plans/*.py` | Modify | Public API 標準 Docstring 與 Why-Driven 動機註解 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 Markdown 文件損毀、為二進位檔或無標頭 blockquote，`PlanStatusResolver` 是否會拋出例外中斷 CLI 執行？  
> [*] **防護解法**：`PlanStatusResolver.parse_header_metadata` 與 `get_doc_header_status` 在讀取與解析時嚴格包覆 `try...except Exception:`，並在遇到非文字或無法解析時安全回傳 `'unknown'`，scanner 與 archiver 依據 `'unknown'` 進行防禦，保證零崩潰。

> [?] **尖銳問題 2**：動態佔位符推導若從模板讀取到未轉義之特殊字符（如正則保留字元 `|`, `[`, `]`），是否會引發 `re.error` 導致驗證器中斷？  
> [*] **防護解法**：佔位符解析時，對非分支符號進行 `re.escape()` 轉義，並透過 `try...except re.error:` 進行語法校驗，若編譯失敗則安全忽略該條動態模式，回退至靜態正則清單保護。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：建立 `status.py` 實作 `PlanStatusResolver`（FR-01、EC-01、EC-02）
- [ ] **TASK-02**：重構 `scanner.py` 與 `archiver.py`，改以標頭狀態解析驅動，修正 handoff 刪除時序與 Research Track 判定（FR-02、FR-03、FR-04、FR-08、EC-04、EC-05、EC-07）
- [ ] **TASK-03**：重構 `verifier.py`，實作調研檔放寬映射、正則收緊、動態佔位符推導與死代碼清理（FR-05、FR-06、FR-07、FR-09、EC-06、EC-09、EC-10）
- [ ] **TASK-04**：編寫單元測試 `tests/test_plans_status.py` 覆蓋 FT-01 ~ FT-09
- [ ] **TASK-05**：更新規範資產 `AgentsStandards.md`（指針改向指向 development-sop 佔位符、FP-03 更名）（FR-10、FR-11）
- [ ] **TASK-06**：更新 7 大技能手冊 (`development-sop`, `new-plan`, `continue`, `auto`, `pause`, `research`, `context-init`)（FR-11 ~ FR-17、FR-19、FR-21 ~ FR-25）
- [ ] **TASK-07**：更新 5 大標準模板 (`fast_track_plan`, `P07_walkthrough`, `revision_log`, `umbrella_overview`, `RXX_research_report`)（FR-18、FR-20、FR-22、FR-26）
- [ ] **TASK-08**：更新貢獻宣告與導覽清冊 (`agents-workflow.json`, `_manifest.md`)（FR-27）
- [ ] **TASK-DOC**：更新知識庫文檔 (`docs/agents-workflow/README.md`, `DESIGN_NOTES.md`) 與全域 `CHANGELOG.md`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性測試雙定稿確認**：本實作計畫與 `P06_test_plan.md` 同步定稿 (`Confirmed`)，所有 27 項需求與 13 項邊界條件皆納入任務分解與測試映射，確認合規後正式進入 Phase 5 編碼實作。

