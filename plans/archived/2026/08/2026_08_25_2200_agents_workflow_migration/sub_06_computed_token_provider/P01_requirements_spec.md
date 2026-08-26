# 需求規格說明書 (Phase 1: Requirements Specification)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements, FR)

| 需求編號 | 對應 P00 語意 | 需求名稱 | 具體規格與行為描述 | 驗收標準 (Acceptance Criteria) |
| :---: | :--- | :--- | :--- | :--- |
| **FR-01** | 第 2.1 節 | `code.func://` 協議解析 | 支援解析 `code.func://<module>/<subpath>:<func>` 格式，分離模組名、相對路徑與函式名稱。 | 能精確解析模組與符號，並透過 VFS 尋找實體路徑。 |
| **FR-02** | 第 2.1 節 | 符號動態載入器 (`resolve_callable`) | 透過 Python `importlib` 安全加載目標模組，獲取函式物件並驗證 `callable`。 | 成功返回可執行的 Python Callable 物件；帶快取機制。 |
| **FR-03** | 第 2.2 節 | Contributes `type: "computed"` 宣告 | `manifest.json` 的 `insert` 支援 `type: "computed"`，`value` 填入 `code.func://...`。 | Schema 驗證放行，識別為動態計算 Token。 |
| **FR-04** | 第 2.2 節 | 工廠解算階段即時調用與上下文注入 | 在 `compile` 產物解算階段，調用 Provider 並注入 `CompilerContext` 物件。 | Provider 獲得完整上下文，編譯產物正確替換為動態字串。 |
| **FR-05** | 第 2.3 節 | `agents-workflow` 路徑地圖實裝 | 提供 `providers.py:get_dynamic_context_map(ctx)`，在 `manifest.json` 宣告注入 `DYNAMIC_CONTEXT_MAP`。 | 產生的 `ContextInit.md` 包含即時動態 Markdown 表格。 |

---

## 2. 邊界條件與例外處理清單 (Edge Cases, EC)

| 例外編號 | 觸發情境與前置條件 | 預期行為與防禦策略 | 錯誤訊息 / 回傳值規格 |
| :---: | :--- | :--- | :--- |
| **EC-01** | `code.func://` URI 語法錯誤（無 `:` 或模組不存在） | 阻斷載入並拋出明確的語意結構異常。 | 拋出 `ValueError` 或 `SymbolNotFoundError`，指明無效格式。 |
| **EC-02** | 目標模組存在但函式不存在或不可呼叫 | 捕獲 `AttributeError` 並驗證 `callable`。 | 拋出 `SymbolNotFoundError: Function '{func}' not found or not callable`。 |
| **EC-03** | Provider 函式內部拋出例外 | 捕獲異常並包裝為編譯期結構化錯誤訊息。 | 拋出 `RuntimeError: Failed to execute computed token '{token}': {e}`。 |
| **EC-04** | Provider 回傳 `None` 或非 `str` 物件 | 自動轉換型別為字串（`str(result)`）或空字串。 | 確保編譯產物不因型別崩潰，正常完成字串拼接。 |

---

## 3. 非功能需求 (Non-Functional Requirements, NFR)

- **NFR-01 (零外部依賴)**：100% 依賴 Python 標準庫（`importlib`、`sys`、`inspect`）。
- **NFR-02 (執行效能與快取)**：對同一個 `code.func://` 模組實施 `sys.modules` 命名空間隔離與載入快取，避免重複 I/O。
- **NFR-03 (測試覆蓋與相容性)**：新增測試用例 100% 通過，全專案 104+ 測試無回歸損壞。
