# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：修訂計畫 (Revision Plan) 正交化定位重構、留檔強制化與 SOP 邊界純化  
> 建立日期：2026-10-17  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：優化「修訂計畫 (Revision Plan)」在 codebase 中的定位問題，將修訂計畫重構為正交選項，廢除「無留檔 (0 計畫文件)」機制並強制留檔產出 `revision_log.md`，同時優化現有 `development-sop` 流程陳述、移除通用模板與規範中混入之專案自引用特化規則（如 `@build`、`dev test`），並在 `P06` 增設「業務功能驗證 vs. 表層修訂」之主動分流詢問機制。
- **核心目標**：
  1. **修訂計畫正交化與適用情境明確定義**：定位於不牽涉核心業務與控制流邏輯的 **UI/UX/DX 表層微調、靜態參數/常數調整、文檔與註解調整**。支援兩種存在型態：
     - **無衍生來源（獨立修訂計畫）**：可單獨存在於 `plans/{plan_name}/`（包含 `revision_log.md` + `changelog.md`，選配前置 `P00_discuss.md`、`RXX_research_report.md`）。
     - **衍生/附掛於既有計畫**：可直接建立於一般計畫（Full Track / Fast Track）、分類型主計畫（Umbrella）或其子計畫（`sub_XX`）目錄下，記錄主功能完成後之各項後續修訂。
  2. **全面廢除無留檔機制，新增標準模板 `revision_log.md`**：
     - 廢除過往「免開實體目錄、0 計畫文件」規範，所有修訂皆須實體留檔於 `revision_log.md`。
     - 採用 `[REV-01]`、`[REV-02]` 條目結構，同一修訂主題之多輪微調原地收斂為最終敘述，不重複疊加流水帳。
  3. **Dev Plans 工具鏈對齊 (`PlanScanner` / `PlanVerifier` / `PlanArchiver`)**：
     - `PlanScanner` (`plan status`)：獨立修訂計畫（無 `umbrella` / `fast_track` / `P01~P07`，但有 `revision_log.md`）識別 Track 模式為 `Revision`；附掛於其他計畫時，不干擾原計畫之主狀態判定。
     - `PlanVerifier` (`plan verify`)：註冊 `revision_log.md` 模板映射，納入標準標頭、模型欄位、未替換佔位符、HTML 註解與 `Completed` 狀態下 Checkbox 勾選合規檢核。
     - `PlanArchiver` (`plan archive`)：歸檔前確認 `revision_log.md`（無論獨立或附掛）已標記 `Completed` 且通過 `PlanVerifier` 檢核，確保結案無遺漏。
  4. **P06 業務功能測試專注與轉入 P07 -> Revision 主動引導**：
     - 於 `phase_06_test.md` 明確規範：P06 專注於業務邏輯與功能正確性驗證；當開發者不再反饋邏輯 Bug 或錯誤行為，轉而開始要求微調 UI/UX/DX、參數或文檔時，Agent 必須主動提問：「核心業務功能是否已確認無誤？是否先進入 P07 完成結案審查後，再開啟 `revision_log.md` 進行後續修訂？」。
  5. **通用工作流框架純化（移除本專案自引用特化規則）**：
     - 清理 `agents-workflow` 通用模板與 `development-sop` 規範（如 `plan_modes.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md`）中硬編碼之 `dev test`、`@build`、`dev bump` 等 YSCB 生態系模組自引用特化詞彙，回歸通用 codebase 表述（模組開發特化細節交由 `dev` 模組之 `yscb-module-dev` 技能或 Token 注入承載）。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更 `core`、`server`、`knowledge-db` 模組之業務邏輯。
  - 不影響歷史已封存於 `plans/archived/` 之舊計畫檔案。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 修訂計畫 (Revision Plan) 正交定位與雙軌存在型態**：
  - 修訂計畫專注於非業務邏輯變更（UI/UX/DX、靜態參數、文檔調整）。既可作為獨立計畫開立（支援搭配選配之 `P00` / `RXX`），亦可正交附掛於一般計畫、Umbrella 主計畫或 `sub_XX` 子計畫目錄內，直接建立 `revision_log.md`。
- **[P00:DR-02] 廢除無留檔模式與 `revision_log.md` 聚合紀錄規範**：
  - 徹底廢棄「0 計畫文件」設定。新增 `assets/templates/revision_log.md` 標準模板並於 `contributes/agents-workflow.json` 導出。內文以 `### [REV-XX] [修訂主題簡述]` 組織，針對同一條目的多輪來回調整（如反覆微調視覺排版）直接原地覆寫收斂為最終變更摘要，禁止記錄每次微調之流水帳。
- **[P00:DR-03] 工具鏈狀態掃描、合規稽核與歸檔守門規則**：
  - **狀態掃描 (`PlanScanner`)**：附掛於既有計畫之 `revision_log.md` 不改變原計畫的 Track 與主狀態；唯當計畫為獨立修訂計畫時，`plan status` 將其 Track 模式標示為 `Revision`，狀態依 `revision_log.md` 標頭顯示（如 `In Progress` / `Completed`）。
  - **合規稽核 (`PlanVerifier`)** 與 **安全歸檔 (`PlanArchiver`)**：`_map_file_to_template` 納入 `revision_log.md`；`PlanArchiver` 在檢查計畫是否可歸檔時，除支援獨立 `revision_log.md` 作為完成依據外，若一般計畫/子計畫內存在附掛之 `revision_log.md`，亦必須確認其標頭狀態為 `Completed`（並由 `PlanVerifier` 確保無未勾選 `- [ ]`），防止尚有未收尾修訂即誤歸檔。
- **[P00:DR-04] P06 業務測試與表層修訂分界引導機制**：
  - 於 `phase_06_test.md` 增設明確的階段職責防線：P06 聚焦於業務功能與邊界條件驗證。一旦開發者反饋收斂至非業務邏輯（UI/UX/DX 排版、文案、參數微調、文檔潤飾），Agent 應主動詢問業務核心是否已無問題、並建議先推進至 P07 完成結案與 SOP Review 後，再透過 `revision_log.md` 展開修訂循環。
- **[P00:DR-05] `agents-workflow` 通用性純化（剝離自引用特化規則）**：
  - `agents-workflow` 為通用專案工作流框架，全面檢視並移除 `revision_log.md`、`plan_modes.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md` 中直接硬編碼的 YSCB 模組開發專用詞彙（如 `@build` 直裝、`dev test <mod>`、`dev bump` 等），改為通用工程測試與建置表述，必要之模組開發特化守門由 `dev` 模組注入或 `yscb-module-dev` 技能負責。

---

## 3. 開放議題與確認紀錄

- [x] 確認修訂計畫適用範圍（UI/UX/DX、參數調整、文檔調整等非業務邏輯變更）。
- [x] 確認修訂計畫正交性（可無衍生來源獨立存在並搭配 P00/RXX，亦可衍生附掛於一般計畫、Umbrella 或子計畫）。
- [x] 確認廢除無留檔模式，統一產出 `revision_log.md` 並以 `REV-XX` 收斂紀錄。
- [x] 確認 `plan status`、`plan verify`、`plan archive` 行為與通用模板去特化要求。
- [x] 確認 P06 測試階段轉入 P07 與 Revision 之主動詢問機制。

