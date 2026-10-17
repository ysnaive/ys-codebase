# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：修訂計畫 (Revision Plan) 正交化定位重構、留檔強制化與 SOP 邊界純化  
> 建立日期：2026-10-17  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書與資產修改清單中有 1:1 對應介面與目標檔案
- [x] **邊界防護**：EC-01 ~ EC-04 有具體處理策略（`PlanScanner` 優先序、`PlanArchiver` 附掛守門、`PlanVerifier` 動態標題正規化與去特化防呆對齊）
- [x] **依賴純淨**：符合 NFR-01 與 NFR-02 指標約束，100% Python 標準庫實作

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新模板庫清單（納入 `revision_log`）與修訂計畫正交留檔說明 |
| **隨包手冊** | `ys_codebase/source/agents-workflow/README.md` | Modify | 同步更新 6 大計畫分支拓撲圖與修訂計畫說明（廢除 0 計畫檔案描述） |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 更新 `plan status`、`plan verify`、`plan archive` 對 `revision_log.md` 的支援規則 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-17]` 修訂計畫正交化、強制留檔與 P06/P07 職責分界決策 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本計畫變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 `revision_log.md` 模板中包含 `### [REV-01] [修訂主題簡述]`，而使用者在實際檔案中寫為 `### [REV-01] 優化 CLI 輸出排版`，`PlanVerifier.get_resolved_template_headers()` 是否會因預期標題包含 `rev01修訂主題簡述` 而誤判實際檔案缺少標題？  
> [*] **防護解法**：於 `PlanVerifier.get_resolved_template_headers()` 中，當提取模板的三級標題 `###` 時，若偵測到標題包含 `[REV-` 動態條目模式，則不將該範例三級標題加入靜態 `expected_headers` 清單（僅強制檢查 `## 1. 修訂紀錄清單` 與 `## 2. 結案與合規檢核` 二級章節標題），並於 `_verify_markdown_file` 獨立檢查 `revision_log.md` 必須至少有一筆匹配 `\[REV-\d+\]` 的修訂條目。

> [?] **尖銳問題 2**：當一個 Full Track 計畫已完成 (`P07_walkthrough.md` 為 `Completed`)，開發者後續在同目錄新增了 `revision_log.md`（狀態 `In Progress`），此時誤執行 `plan archive` 會發生什麼事？  
> [*] **防護解法**：在 `PlanArchiver.archive_plan` 中，除了檢查主計畫是否 `Completed` 外，額外強制檢查主目錄及所有 `sub_*` 子目錄下已存在的 `revision_log.md` 是否皆為 `Completed`。只要有任何一份 `revision_log.md` 尚未標記 `Completed`，立即拋出 `PlanIncompleteError` 阻斷歸檔。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01**：新增 `ys_codebase/source/agents-workflow/assets/templates/revision_log.md` 並於 `contributes/agents-workflow.json` 註冊導出（FR-01）
- [x] **TASK-02**：更新 `agents_workflow/plans/{scanner,verifier,archiver}.py` 支援 `revision_log.md` 正交掃描、合規稽核與歸檔守門（FR-03, FR-04, FR-05, EC-01 ~ EC-03）
- [x] **TASK-03**：重構 `development-sop`、`new-plan`、`continue`、`auto` 技能手冊與參考文件（修訂計畫正交定位、P06 主動詢問分流、通用框架去特化純化）（FR-02, FR-06, FR-07, EC-04）
- [x] **TASK-04**：更新 `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` 新增單元與邊界測試（FT-01 ~ FT-03, ET-01）
- [x] **TASK-DOC**：同步更新 `source/agents-workflow/README.md`、`docs/agents-workflow/{README,user_guide,DESIGN_NOTES}.md` 並執行 `@build` 與 `release` 物化驗證

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確認 `P04_implementation_plan.md` 與 `P06_test_plan.md` 雙定稿 (`Confirmed`)，依序進入 Phase 5 編碼實作。

