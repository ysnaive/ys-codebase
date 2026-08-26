# 語意需求書 (Phase 0: Semantic Requirements)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 計畫類型：Level 1 Full Track  
> 模板版本：v1.1  

---

## 1. 原始需求描述 (Raw User Requirements)

- **使用者意圖**：
  1. 在 `ContextInit.md` 等工作流模板中，存在需要由執行期動態計算並注入的即時路徑表（如 `DYNAMIC_CONTEXT_MAP`）。需要擴充 Contributes 體系支援 Computed Token，使編譯期能夠動態調用計算函式產生地圖或動態內容。
  2. 趁此次機會統一專案中各模組對程式碼函式/符號的指向方案，建立全專案標準的**「`code.func://` 函式定位協議」**（未來可向後相容擴充 `code.param://` 等）。

---

## 2. 核心邊界與語意範疇 (Semantic Scope & Boundaries)

- **包含範疇 (In Scope)**：
  1. **`core` 模組：`code.func://` 協議解析與 Callable 加載子系統**：
     - 語法規格：`code.func://<module>/<subpath>:<function_name>`。
     - 提供標準 API（如 `resolve_callable(uri_str) -> Callable`），自動處理模組在安裝態 (`modules/`)、源碼態 (`source/`) 或 Zip 隔離環境下的 Python package/module 尋址與動態載入。
  2. **`core` 模組：Contributes insert 擴充支援 `type: "computed"`**：
     - 支援在 `manifest.json` 中宣告 `type: "computed"`，以 `value` 指向 `code.func://...`。
     - 在 `compile` 工廠解算階段即時調用該 Provider 函式，並傳遞編譯期/執行期上下文 `CompilerContext`（包含全量已注入模組狀態、URI 解析器、專案設定等）。
  3. **`agents-workflow` 模組：宣告與實作 `DYNAMIC_CONTEXT_MAP` Provider**：
     - 建立 `providers.py`，實作 `get_dynamic_context_map(context)` 函式，動態組裝最新語意 URI Markdown 表格。
     - 在 `manifest.json` 中以 `code.func://agents-workflow/providers:get_dynamic_context_map` 宣告注入。
  4. **全模組單元測試與回歸驗證**。

- **排除範疇 (Out of Scope)**：
  1. `code.param://` 等其他尚未規劃的 code 族系協議（留待未來需求擴充）。
  2. 現有 Hook / CLI 指令架構暫維持現況，待未來有獨立重構需求時再平滑遷移至 `code.func://`。

---

## 3. 已達成之架構決策 (Architecture Decisions)

- **[SUB06:DR-01] 統一函式定位協議命名**：
  全專案程式邏輯與符號指向協議統一命名為 **`code.func://`**（規格：`code.func://<module>/<path>:<func>`），由 `core` 模組集中負責解析與動態載入。
- **[SUB06:DR-02] Contributes 宣告式 Computed Token**：
  ```json
  {
    "type": "computed",
    "token": "DYNAMIC_CONTEXT_MAP",
    "value": "code.func://agents-workflow/providers:get_dynamic_context_map",
    "mode": "replace"
  }
  ```
- **[SUB06:DR-03] 執行期時序與上下文注入**：
  在 `compile` 工廠解算階段即時調用 Provider，並注入包含全量已完成注入之模組狀態與 URI 解析器的上下文物件。

---

## 4. 變更紀錄 (Changelog Pointer)

- 本計畫微觀歷史請參見同目錄之 [changelog.md](./changelog.md)。
