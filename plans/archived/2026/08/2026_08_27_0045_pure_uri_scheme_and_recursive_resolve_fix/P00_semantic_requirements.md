# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：純淨語意 URI 協議與遞迴解算缺陷修復 (Pure Semantic URI Protocol & Recursive Resolution Fix)  
> 建立日期：2026-08-27  
> 狀態：Confirmed  
> 計畫類型：Bugfix & Refactoring  
> 分流層級：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 1. "ContextInit.md 動態語意解析池不該為 undefined 啊? config.project.json 中確實有設定"
  > 2. "core.uri._DEPRECATED_SCHEME_REDIRECTS 刪除當前所有重定向，現為純淨版本，不考慮重定向，禁止調用python yscb.py dev release，先修復邏輯就好"
  > 3. "以 fast track 模式紀錄完整歷程"
  > 4. "合併紀錄於本次 fast track，於 on_reload 時自動運行一次 agent workflow release"

- **核心目標**：
  1. **修復 Core 遞迴解算異常**：修復 `core.uri.resolve` 在解算 `type: "config"` 且值為 URI 協議（如 `project://plans`）時誤用未定義變數 `mod` 導致的 `NameError`。
  2. **清除舊版協議重定向（純淨版本）**：清空 `core.uri._DEPRECATED_SCHEME_REDIRECTS`，不再向後相容轉譯 `storage.root`、`cache.root` 等歷史廢棄協議，回歸嚴格的純淨 Canonical 協議模型。
  3. **正規化 Agents-Workflow 協議查詢與模板**：將 `providers.py` 與 `ContextInit.md` 中的協議名稱與參照全數統一對齊為官方註冊之 `workflow.plans`、`workflow.archived`、`workflow.docs`。
  4. **嚴守 Dogfooding 空間邊界紀律**：所有修改均在 `source/` 源碼空間進行，暫不調用 `python yscb.py dev release`，確保源碼測試 100% 通過。
  5. **掛載 `on_reload` Hook 自動發布**：在 `agents-workflow/scripts/hook.core.py` 中實作 `on_reload` 自動調用 `ReleasePublisher().release_all()`，達成環境 reload 時自動完成工作流發布與產物物化。

- **邊界排除 (Explicitly Excluded)**：
  1. **不保留舊協議容錯**：`_DEPRECATED_SCHEME_REDIRECTS` 清空後，調用未註冊的舊協議將直接拋出 `ValueError`。
  2. **不執行正式 Module Release**：僅完成 `source/` 源碼修復、本地 `build` 打包與測試驗證，不推進至 `release/` 與正式發布。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] (清空舊協議重定向表)**：
  - **議題**：是否保留 `*.root` 與 `temp` 等舊版協議相容別名？
  - **結論**：依使用者指示全面清空 `_DEPRECATED_SCHEME_REDIRECTS = {}`，系統進入 100% Pure Canonical 協議模式。
- **[P00:DR-02] (修復 Core 遞迴解算作用域變數)**：
  - **議題**：`core.uri.resolve()` 第 527 行因變數名稱筆誤拋出 `NameError`。
  - **結論**：將 `resolve(val_str, current_module=mod, ...)` 修正為 `current_module=active_mod`。
- **[P00:DR-03] (Agents-Workflow 協議命名空間統一)**：
  - **議題**：`providers.py` 與 `ContextInit.md` 使用無命名空間的短名稱（`plans`、`archive`、`docs`）導致無法解析。
  - **結論**：全數更新為 `workflow.plans`、`workflow.archived`、`workflow.docs`。
- **[P00:DR-04] (Dogfooding 空間與測試閉環)**：
  - **議題**：何時觸發發布流水線？
  - **結論**：僅在 `source/` 空間完成修復，執行 `dev test core` 與 `dev test agents-workflow` 達成 100% 通過，不調用 `dev release`。
- **[P00:DR-05] (`on_reload` Hook 自動觸發原子發布)**：
  - **議題**：如何在 `core` 重載環境時自動更新工作流與 IDE 投影片產物？
  - **結論**：在 `source/agents-workflow/scripts/hook.core.py` 中掛載 `on_reload` 事件處理常式，直接呼叫 `ReleasePublisher().release_all()`。

---

## 3. 開放議題與確認紀錄

- [x] 是否已確認清空所有舊版協議重定向？（已於 [P00:DR-01] 定義）
- [x] 是否已確認修復遞迴解算變數與 Providers 查詢清單？（已於 [P00:DR-02], [P00:DR-03] 定義）
- [x] 是否已確認掛載 `on_reload` Hook 自動執行 workflow release？（已於 [P00:DR-05] 定義）
- [x] 是否已確認依 Fast Track 模式完成歷程記錄？（已確認）
