# 需求規格說明書 (Requirements Specification)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core` 擴充點 `"locales"` Schema 定義與導覽手冊同步 | 1. 於 `ys_codebase/source/core/contributes/_format.json` 新增頂層擴充點 `"locales"`，其 `format` 規定包含必填欄位 `"definition": "str!"` 與動態語系/方言映射 `"*": "str!"`。<br/>2. 於 `ys_codebase/source/core/contributes/_manifest.md` 同步補齊 `"locales"` 擴充點之語意說明與宣告範例。<br/>3. 驗收條件：執行 `python yscb.py contributes check --format core` 與 `contributes list` 可正確檢驗並列出 `core` 的 `locales` 擴充點（`[P01:DR-01]`）。 | P0 | [P00:DR-02] |
| **FR-02** | `ContributesAggregator` 按模組分桶聚合 `locales` 與快取追蹤 | 1. 於 `core.contributes` 的 `ContributesAggregator.scan_and_inject` 中，當目標為 `core` 且 Donor 宣告了 `"locales"` 時，除頂層合併外，比照 `commands.__modules__` 模式將各 Donor 的 `locales` 宣告獨立保存於 `aggregated["core"]["locales"]["__modules__"][donor]`（並支援 `config://core/contribute.json` 專案層級覆寫）。<br/>2. 於 `_scan_contributes_inputs()` 中，將各模組 `locales` 宣告所指向之實體 JSON 檔案納入 `(mtime, size)` 快照追蹤，確保語系檔修改時自動觸發 JIT 熱重載。<br/>3. 驗收條件：多模組同時向 `core` 貢獻 `"locales"` 時，各模組的 `"definition"` 與 `"<lang-id>"` 路徑映射互不覆蓋，且修改任一語系 JSON 檔後 `contributes.get("core", "locales")` 能感知變更。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `core.locale` 顯式多層優先級退避鏈（Explicit Priority Fallback Chain） | 1. 新增 `ys_codebase/source/core/core/locale.py` 並於 `core/__init__.py` 註冊 PEP 562 延遲載入映射 `"locale": ("core.locale", None)`。<br/>2. **100% 顯式優先級鏈（嚴禁隱式拆分 `-` 自動插入父語系）**：<br/>   • 退避鏈完全依照配置或傳入之 `lang-id` 列表順序逐層查找（例如顯式指定 `["nouns-antigravity", "zh-TW", "zh", "en"]` 或下游自訂之任意 `<lang-id>` 識別符），**絕不對含 `-` 的 ID 進行自動切分猜測父語系**，避免誤傷非 `nouns-` 開頭之自訂方言或複合識別符（`[P01:DR-02]`）。<br/>   • 若未顯式傳入 `chain`，則從環境變數 `YSCB_LOCALE`（支援逗號分隔鏈，如 `"nouns-antigravity,zh-TW,zh,en"`）或 `config://core` 之 `locale`（支援 `list[str]` 或逗號分隔字串，預設退避鏈為 `["zh-TW", "zh", "en"]`）讀取。<br/>3. 驗收條件：給定稀疏覆寫之自訂 `<lang-id>` 列表，查詢任意 Key 時 100% 嚴格依顯式宣告之優先級鏈順序返回首個命中值，零隱式字串切分副作用。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | `core.locale` 跨鍵專有名詞遞迴插值與參數格式化 (`t` / `translate`) | 1. 提供標準檢索與格式化 API `locale.t(key: str, *, module: Optional[str] = None, chain: Optional[List[str]] = None, default: Optional[str] = None, **kwargs: Any) -> str`（支援 `"<module>:<key>"` 命名空間語法或由 `module` / `uri.get_module_context()` 推導所屬模組）。<br/>2. **二階遞迴插值機制**：當命中的模板字串包含 `{placeholder}` 時：<br/>   • 優先使用呼叫端傳入之 `kwargs[placeholder]` 替換。<br/>   • 若 `placeholder` 不在 `kwargs` 中，則自動將 `placeholder` 視為語系/專有名詞鍵（支援同模組鍵如 `{tool.read_range}` 或跨模組鍵如 `{core:tool.read_range}`），沿**同一條優先級退避鏈**遞迴解析並替換（最大遞迴深度限制為 `5` 層，防範循環引用）。<br/>3. 驗收條件：當 `cli.snippet.truncated_hint` 模板含 `{rem}` 與 `{tool.read_range}`，且僅傳入 `rem=50` 時，引擎能自動從退避鏈首層 `nouns-antigravity` 解析 `tool.read_range` 並合成完整字串。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-05** | 基於 `"definition"` 語意解釋檔的確定性靜態契約校驗 (`core.locale` / `contributes check` / `dev check`) | 1. 實作靜態契約校驗器 `locale.validate_module_locales(module_name: str, locales_decl: Dict[str, str], base_dir_or_uri: str) -> ValidationResult`，並串聯至 `core/commands/contributes_cmd.py` (`check_contributes`) 與 `dev/checker.py` (`_check_core_injection`)。<br/>2. 校驗規則涵蓋：<br/>   • **檔案存在性與 JSON 語法**：`definition` 與所有 `<lang-id>` 指向之相對路徑檔案必須存在，且內容為 JSON Object (`dict`)。<br/>   • **`definition` 結構合規性**：`definition` 內每個 Key 的值必須為 `dict`，包含非空字串 `"description"`（語意解釋）與選填之 `"placeholders"`（`list[str]`）；若未顯式填寫 `"placeholders"`，預設為 `[]`（`[P01:DR-03]`）。<br/>   • **孤兒鍵攔截（No Orphan Keys）**：任何 `<lang-id>` 檔案中出現的 Key 若不存在於 `definition` 中，判定為 `ERROR` / `FAIL` 並透過 `difflib` 提供拼寫建議。<br/>   • **佔位符契約一致性（Placeholder Contract）**：提取 `<lang-id>` 翻譯字串中的所有 `{...}` 佔位符，若出現未在該 Key 之 `definition.placeholders` 中宣告的未知佔位符，或遺漏了必備動態參數佔位符，判定為 `ERROR` / `FAIL`。<br/>3. 驗收條件：針對含孤兒鍵、缺失檔案、非法 `definition` 結構或佔位符不匹配的測試模組執行 `contributes check` 與 `dev check` 時，100% 精準報錯攔截。 | P0 | [P00:DR-02], [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `contributes/core.json` 的 `"locales"` 缺少 `"definition"` 鍵或路徑指向不存在的檔案 | `ContributesValidator` 於 Schema 層攔截缺少 `"definition"` 必填欄位；檔案契約校驗器回報明確缺失路徑錯誤，執行期 `core.locale` 則容錯記錄警告並降級返回 `default` 或原始 `key`。 |
| **EC-02** | 遞迴專有名詞插值發生直接或間接自我循環引用（如 `A -> "{B}"`, `B -> "{A}"`） | `core.locale` 插值器維護當前解析鏈 `visited_keys` 集合與最大深度上限（`MAX_INTERPOLATION_DEPTH = 5`）；一旦偵測到循環引用或超深，立即停止展開並保留原樣 `{key}` 字面量，絕不拋出 `RecursionError`。 |
| **EC-03** | 翻譯模板字串中包含雙花括號轉義 `{{` / `}}`（例如程式碼片段或 JSON 範例）或呼叫端漏傳 `kwargs` 參數 | 1. 佔位符提取與替換正則嚴格識別並保護雙花括號 `{{...}}` 轉義為單花括號字面量 `{...}`，不誤判為佔位符變數。<br/>2. 若執行期呼叫 `locale.t()` 漏傳某個未知佔位符且退避鏈亦查無此名詞鍵，安全保留 `{missing_var}` 原文不拋出 `KeyError` 崩潰。 |
| **EC-04** | `dev check` 對 `core` 模組自身執行靜態檢查時，原先 `_check_core_injection` 頂部有 `if name == "core": return` 跳過檢查 | 修改 `dev/checker.py` 的 `_check_core_injection`，使 `name == "core"` 僅跳過「缺少 `contributes/core.json` 警告」，但仍正常對 `core` 自身的 `contributes/_format.json`、`contributes/core.json` 及 `locales` 契約執行完整靜態檢驗。 |
| **EC-05** | 語系檔案路徑包含 `..` 路徑穿越嘗試（如 `"../../etc/passwd"`） | 靜態校驗與執行期載入均強制檢驗解析後之實體路徑必須位於該模組根目錄（或專案 `config://` 目錄）內部，拒絕任何越界路徑並報錯。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 (Zero-Pip) | `core.locale` 與擴充之驗證器 100% 使用 Python 標準庫（`json`, `re`, `os`, `difflib`, `typing`）實作，嚴禁引入任何第三方套件（遵循 `docs/core/DESIGN_NOTES.md` `[DN-08]`）。 |
| **NFR-02** | 記憶體快取與冷啟動效能 | 1. 遵循 `[DN-11]`，`core/__init__.py` 維持 PEP 562 延遲載入，不增加 `import core` 冷啟動開銷（維持 $< 5\text{ms}$）。<br/>2. `core.locale` 對已載入之模組語系 JSON 實施基於 `(file_path, mtime)` 的記憶體快取，熱路徑單次 `locale.t()` 解析耗時 $< 0.5\text{ms}$。 |
| **NFR-03** | 範疇隔離紀律 | 嚴格遵守 `sub_01` 邊界排除約束：本子計畫僅交付 `core.locale` 引擎、Schema 與靜態檢查器，零跨界修改 `knowledge-db`、`agents-workflow` 或 `server` 的業務輸出邏輯。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` [DN-08] 微內核零 Pip 純標準庫鐵律**（查閱自 [DESIGN_NOTES.md](file:///workspace/ys-codebase/docs/core/DESIGN_NOTES.md#L128-L137)）：`core` 微內核所有模組（含新增之 `core.locale` 與 `core.validator`）必須 100% 採用 Python 標準庫實作，嚴禁引入外部套件。
- **`[!CAUTION]` [DN-11] `core/__init__.py` PEP 562 延遲載入**（查閱自 [DESIGN_NOTES.md](file:///workspace/ys-codebase/docs/core/DESIGN_NOTES.md#L165-L174)）：於 `core/__init__.py` 導出 `locale` 時，必須註冊於 `_MODULE_MAP` 與 `if TYPE_CHECKING:` 區塊內，嚴禁於檔案頂層直接 `import core.locale`。
- **`[!WARNING]` [DN-02] Contributes 快照寫入 `cache://` 與零空檔物化**（查閱自 [DESIGN_NOTES.md](file:///workspace/ys-codebase/docs/core/DESIGN_NOTES.md#L63-L70)）：聚合後之 `locales` 元資料統一隨 `ContributesAggregator` 寫入 `cache://core/contributes.merged.json`，不得寫入 `config://`。
- **`[!WARNING]` [DN-DEV-01] 測試方法顯式 `self.mark_passed()` 契約**（查閱自 [DESIGN_NOTES.md](file:///workspace/ys-codebase/docs/dev/DESIGN_NOTES.md#L36-L46)）：為 `core` 與 `dev` 新增的所有 `YSCBTestCase` 測試方法，結尾必須顯式呼叫 `self.mark_passed()`。

