# 需求規格說明書 (Requirements Specification)

> 功能名稱：修訂計畫 (Revision Plan) 正交化定位重構、留檔強制化與 SOP 邊界純化  
> 建立日期：2026-10-17  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 新增 `revision_log.md` 標準模板與資產導出 | 於 `ys_codebase/source/agents-workflow/assets/templates/revision_log.md` 建立標準修訂紀錄書模板，嵌入 `__@{PHASEXX_HEADER}__` 共用標頭，提供 `## 1. 修訂紀錄清單 (Revision Entries)`（`### [REV-01] [修訂主題簡述]` 結構，含修訂類別 `UI/UX/DX \| Parameter \| Docs`、涉及檔案、修訂摘要、驗證結果）與 `## 2. 結案與合規檢核 (Completion & Compliance Checklist)`（含修訂與驗證完畢、日誌與文檔同步、`plan verify` 結構合規檢核 3 項 Checkbox），並註冊至 `contributes/agents-workflow.json` 之 `export` 清單。 | P0 | [P00:DR-02] |
| **FR-02** | 修訂計畫正交定位與 SOP / Skill 規範重構 | 更新 `development-sop/SKILL.md`、`development-sop/references/plan_modes.md`、`development-sop/references/phase_00_discuss.md`、`new-plan/SKILL.md`、`continue/SKILL.md` 及相關說明文檔：廢除「0 計畫文件 / 免開立目錄」描述，確立修訂計畫專注於非業務邏輯（UI/UX/DX、靜態參數、文檔調整）之正交定位，支援「無衍生來源（獨立計畫，可含選配 `P00`/`RXX` + `revision_log.md` + `changelog.md`）」與「衍生附掛於既有計畫（一般計畫、Umbrella 主計畫或 `sub_XX` 子計畫內直接建立 `revision_log.md`）」，並明定同條目多輪修改原地收斂、不記流水帳原則。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `PlanScanner` (`plan status`) 獨立修訂識別與正交免疫 | 更新 `agents_workflow/plans/scanner.py:get_plan_info`：當計畫目錄已具備 Umbrella、Fast Track 或 Full Track (`P01~P07`) 主體時，附掛之 `revision_log.md` **不干擾、不改變**該計畫之 Track 模式與當前狀態判定；唯當計畫為無其他開發主體之獨立修訂計畫（存在 `revision_log.md`，不論是否伴隨 `P00_discuss.md` 或 `RXX`）時，將 Track 模式識別為 `"Revision"`，狀態解析自 `revision_log.md` 標頭（如 `In Progress`、`Completed` 等）。 | P0 | [P00:DR-03] |
| **FR-04** | `PlanVerifier` (`plan verify`) 納入 `revision_log.md` 合規稽核 | 更新 `agents_workflow/plans/verifier.py:_map_file_to_template`：將 `revision_log.md` 映射至 `"revision_log.md"` 標準模板，使其自動接受 Stage 4 全套檢核（Header 元數據與 `> 模型：` 必填、未替換佔位符攔截、禁含 HTML 註解、章節標題動態鏡像對齊，以及狀態為 `Completed` / `Concluded` 時未勾選 `- [ ]` 剛性阻斷）。 | P0 | [P00:DR-03] |
| **FR-05** | `PlanArchiver` (`plan archive`) 納入獨立與附掛 `revision_log.md` 完成度守門 | 更新 `agents_workflow/plans/archiver.py:archive_plan`：(1) 支援獨立修訂計畫以 `revision_log.md` 標記 `Completed` 作為計畫完成依據；(2) 當一般計畫、Umbrella 主計畫或其 `sub_*` 子計畫目錄內存在附掛之 `revision_log.md` 時，歸檔前必須額外驗證所有存在之 `revision_log.md` 均已標記為 `Completed`（除非指定 `--force`），確保所有修訂均已收尾無遺漏。 | P0 | [P00:DR-03] |
| **FR-06** | `P06` 業務測試專注與轉入 `P07` -> `Revision` 主動引導規範 | 更新 `development-sop/references/phase_06_test.md`（及 `auto/SKILL.md` 相關銜接說明）：明確規範 Phase 6 聚焦於業務功能與邏輯正確性測試；當開發者不再反饋邏輯 Bug 或錯誤行為，轉而提出 UI/UX/DX、參數或文檔微調需求時，Agent 必須主動詢問開發者：「核心業務功能是否已確認無問題？是否先進入 P07 完成結案與 SOP 審查後，再建立 `revision_log.md` 進行後續修訂？」。 | P0 | [P00:DR-04] |
| **FR-07** | `agents-workflow` 通用工作流與模板去特化純化 | 全面盤點並清除 `agents-workflow` 模組內（含 `revision_log.md`、`plan_modes.md`、`phase_05_task.md`、`phase_06_test.md`、`phase_07_walkthrough.md` 等）硬編碼之 YSCB 自引用模組開發特化規則（如 `@build` 直裝、`dev test <mod>`、`dev check <mod>`、`dev bump` / `dev release` 等），改為適用於任何宿主專案的通用測試、靜態檢查與發布表述；同時將 YSCB 專屬模組開發規則確保收斂於 `dev` 模組之 `yscb-module-dev` 技能或 Contributes Token 注入。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 獨立修訂計畫同時包含前置 `P00_discuss.md`（或 `RXX`）與 `revision_log.md` | `PlanScanner.get_plan_info` 判定優先級須高於單純 `Phase 0` 分支：只要無 `Umbrella` / `Fast Track` / `Full Track (P01)` 主體且存在 `revision_log.md`，Track 模式即應判定為 `"Revision"` 而非停留在 `"Phase 0"`。 |
| **EC-02** | 主計畫（Full Track / Fast Track / Umbrella）已標記 `Completed`，但附掛之 `revision_log.md`（位於主目錄或 `sub_*` 子目錄）狀態仍為 `In Progress` 或含有未勾選 Checkbox | 執行 `plan verify` 時，若 `revision_log.md` 標記 `Completed` 卻有未勾選 Checkbox 則回報 `FAIL`；執行 `plan archive`（未帶 `--force`）時，若發現主目錄或任何 `sub_*` 子目錄下之 `revision_log.md` 尚未標記 `Completed`，拋出 `PlanIncompleteError` 明確阻斷歸檔並提示尚有未完成之 `revision_log.md`。 |
| **EC-03** | `revision_log.md` 內新增多個 `[REV-01]`、`[REV-02]` 三級標題 (`###`) 時與 `PlanVerifier` 動態模板標題比對之相容性 | `PlanVerifier.get_resolved_template_headers` 預設會提取模板中的 `##` 與 `###` 標題。若 `revision_log.md` 模板中包含含佔位符的範例三級標題（如 `### [REV-01] [修訂主題簡述]`），必須確保 `PLACEHOLDER_PATTERNS` 與標題正規化不會導致實例化後的真實標題（如 `### [REV-01] 優化表格排版`）在模板鏡像比對時誤報缺少章節標題 `[P01:DR-01]`。 |
| **EC-04** | 將 `agents-workflow` 內文去特化時，本專案自身開發仍需維持模組開發防呆紀律 | 檢查 `dev/contributes/agents-workflow.json` 與 `yscb-module-dev/SKILL.md`，確保 `@build`、沙盒測試與禁止擅自 `bump/release` 等規則在 `dev` 模組技能與 CLI Guild 中已完整覆蓋，去特化不會削弱本專案 Agent 的防呆保護。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 測試與靜態檢查 | `agents-workflow` 與 `dev` 模組既有與新增單元測試 100% 通過；`dev check` 0 Errors、0 Warnings。 |
| **NFR-02** | 模板與發布同步 | 修改後透過 `agents-workflow release` 原子同步至 `.agents/`，且 `plan verify` 對當前活躍計畫 100% 檢核通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` [P01:DR-01] `PlanVerifier` 動態章節標題提取對 `###` 子標題與佔位符的交互影響**：
  - 查閱 `agents_workflow/plans/verifier.py:220-233` 可知，`get_resolved_template_headers` 會提取模板內所有 `##` 與 `###` 開頭的行並經過 `normalize_header_title` 存入預期標題清單；而 `_verify_markdown_file` 會要求目標檔案必須模糊匹配模板中每一個預期標題。
  - 若 `revision_log.md` 模板中將 `[REV-01]` 寫成 `### [REV-01] ...`，模板解析出的預期標題會包含該字串，當實際文件寫成具體主題名稱時可能因字串不匹配而觸發 `TEMPLATE` FAIL。
  - **設計對策**：在 `revision_log.md` 模板中，一級結構使用 `## 1. 修訂紀錄清單 (Revision Entries)` 與 `## 2. 結案與合規檢核 (Completion & Compliance Checklist)`，而將 `[REV-01]` 條目格式規範設計為無額外佔位文字的固定錨點或清單結構（或於 `PlanVerifier.normalize_header_title` / `get_resolved_template_headers` 對 `[REV-XX]` 動態條目頭做正規化支援），於 Phase 2 詳加設計。
- **`[!NOTE]` Stage 0 快取與雙空間對齊**：
  - 修改 `source/agents-workflow/` 模板與技能後，必須安裝 `@build` 並執行 `agents-workflow compile` / `release` 使 `.agents/.yscb/templates/revision_log.md` 物化，確保 `PlanVerifier` 能讀取到最新展開後之模板。

