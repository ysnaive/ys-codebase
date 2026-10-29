# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-28  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 將 YSCB 的 i18n 與宿主專有名詞治理內建為 `core.locale` 核心功能，支援多層優先級退避（例如 `[nouns-antigravity|nouns-claude|nouns-codex] -> zh-TW -> zh -> en`）。
  - 各模組在 `contributes/core.json` 中的宣告式貢獻設計改為檔案指標映射：
    ```json
    "locales": {
      "definition": "locales/definition.json",
      "lang-id": "locales/lang-id.json",
      "lang-id2": "locales/lang-id2.json"
    }
    ```
  - 直接立項，將前述討論收斂為 `R01`，建立增量分類型主計畫（Umbrella Incremental），其中 `sub_01` 為核心功能實現（不包含各模組開始接入使用）。
- **核心目標**：
  1. **擴充 `core` 的 Contributes Schema (`contributes/_format.json` & `_manifest.md`)**：新增頂層擴充點 `"locales"`，定義 `"definition": "str!"` 必填語意解釋檔路徑與 `"*": "str!"` 動態語系/方言檔路徑映射。
  2. **實作 `core.locale` 核心引擎 (`ys_codebase/source/core/core/locale.py`)**：
     - 支援解析與載入已聚合或指定模組之 `locales`（含 `definition` 與各 `<lang-id>` 字典）。
     - 支援顯式多層優先級退避鏈（Explicit Priority Fallback Chain，如 `["nouns-antigravity", "zh-TW", "zh", "en"]`），嚴格依陣列順序查找，不做隱式 `-` 字串切分父語系猜測。
     - 支援跨鍵專有名詞遞迴插值（例如模板內含 `{tool.read_range}` 或 `{core:tool.read_range}` 時，自動沿同一優先級鏈查找對應名詞並完成參數格式化）。
     - 支援從 `config.project.json` / `config.local.json`（或環境變數/顯式參數）讀取預設語系鏈設定。
  3. **擴充 Contributes 聚合與靜態契約校驗 (`core.contributes`、`core.validator`、`dev.checker`)**：
     - 在 `ContributesAggregator` 聚合時收集各模組註冊之 `locales` 映射並支援快取查找。
     - 在 `contributes check` 與 `dev check` 中，針對宣告了 `"locales"` 的模組，自動讀取其 `"definition"` 檔案與各 `"<lang-id>"` 檔案，執行確定性契約校驗：
       - 檢查檔案是否存在且為合法 JSON 物件。
       - 檢查 `definition` 內每個條目的結構合規性（包含 `description` 語意說明與選填之 `placeholders` 清單）。
       - 檢查各 `<lang-id>` 檔案中是否存在未定義於 `definition` 的孤兒鍵（Orphan Keys）。
       - 檢查各 `<lang-id>` 翻譯字串中的 `{placeholder}` 佔位符是否符合 `definition` 宣告之契約。
- **邊界排除 (Explicitly Excluded)**：
  - **不包含各模組業務字串的實際接入與遷移**：`sub_01` 僅完成 `core.locale` 引擎、Schema 與校驗機制本身（及單元測試），不在本子計畫中修改 `knowledge-db`、`agents-workflow`、`server` 等模組的業務輸出字串。
- **架構影響範圍**：
  - `ys_codebase/source/core/contributes/_format.json`、`ys_codebase/source/core/contributes/_manifest.md`
  - `ys_codebase/source/core/core/locale.py`（新增核心模組）
  - `ys_codebase/source/core/core/contributes.py`、`ys_codebase/source/core/core/validator.py`、`ys_codebase/source/core/core/commands/contributes_cmd.py`
  - `ys_codebase/source/dev/dev/checker.py`（開發期源碼靜態檢查對接）
  - `ys_codebase/source/core/tests/`、`ys_codebase/source/dev/tests/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 內核原語定位 (`core.locale`)**：將語系與專有名詞引擎直接內建於 `core.locale`，避免獨立模組造成的底層循環依賴，讓 `core`、`dev`、`server`、`knowledge-db`、`agents-workflow` 均可零門檻直接 `from core import locale` 調用。
- **[P00:DR-02] 檔案指標與 `"definition"` 語意契約分離**：`contributes/core.json` 的 `"locales"` 僅存放相對檔案路徑（`{"definition": "...", "<lang-id>": "..."}`），由 `"definition"` 檔案統一描述每個 Key 的語意解釋（`description`）與插值變數（`placeholders`），兼顧 `core.json` 潔淨度、AI 可讀性與靜態校驗剛性。
- **[P00:DR-03] 宿主方言與多語系統一於單一退避鏈**：將宿主環境專有名詞（如 `nouns-antigravity`、`nouns-claude`、`nouns-codex`）視為稀疏語系覆寫層（Sparse Dialect Layer），置於優先級鏈最前端，與後續的自然語言退避鏈（`zh-TW -> zh -> en`）無縫融合。
- **[P00:DR-04] 增量分離推進**：主計畫採增量型 Umbrella，`sub_01` 100% 聚焦於核心機制實作與測試验证，與後續各模組的業務接入完全解耦。

---

## 3. 開放議題與確認紀錄

- 核心設計（`core.locale` 定位、`"locales": {"definition": "...", "<lang-id>": "..."}` 宣告式結構、多層 Fallback 鏈與 `sub_01` 範圍邊界）均已與開發者確認完畢，無未決開放議題。

