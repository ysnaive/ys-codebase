# 測試計畫 (Test Plan)

> 功能名稱：開發者工具模組 (Dev Developer Tools Module)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 功能 | FR-01 | 執行 `python yscb.py dev create my_plugin --desc="My test plugin"` | 成功於 `source/my_plugin/` 生成包含 `manifest.json`, `scripts/cli.py`, `my_plugin/__init__.py`, `tests/test_basic.py`, `.yscbignore` 之標準骨架。 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 執行 `python yscb.py dev check my_plugin` 檢查合法模組 | 檢查通過，輸出完整綠燈報告，Exit Code 為 0。 | ✅ Passed |
| **FT-03** | 功能 | FR-03 | 於 `source/my_plugin/` 製造 `__pycache__`, `.tmp`, `tests/` 後執行 `python yscb.py dev build my_plugin` | 成功建置至 `build/my_plugin/`，建置產物 100% 純淨且完全過濾快取、測試與暫存檔案。 | ✅ Passed |
| **FT-04** | 功能 | FR-02/03 | 執行 `python yscb.py dev check --all` 與 `python yscb.py dev build --all` | 批次掃描並建置 `source/` 下所有合法模組。 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | 嘗試 `create` 已存在的模組名稱 | 立即阻斷並報錯「Module already exists」，現有檔案未被覆蓋。 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 嘗試 `create` 非法模組名稱（如 `123-bad-name!`） | 立即阻斷並提示符合 Python 識別碼規範之模組命名規則。 | ✅ Passed |
| **ET-03** | 邊界 | EC-03 | 刻意破壞模組語法（如引發 SyntaxError）後執行 `check` | `check` 精確攔截並回報語法錯誤檔案與行號，Exit Code 為 1。 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 嘗試 `build` 不存在的模組 | 報錯「Source module not found」，立即終止。 | ✅ Passed |
| **PT-01** | 效能 | NFR-01 | 檢查 `source/dev/` 全部 Python 源碼之依賴清單 | 100% 純 Python 標準庫（`os`, `sys`, `shutil`, `re`, `ast`, `fnmatch`, `typing`），零第三方相依。 | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **UX-01** | `check` 終端報告視覺排版 | 執行 `python yscb.py dev check core` 與 `python yscb.py dev check --all` | 輸出整齊的檢查項目清單與狀態總結。 | ✅ Passed |
| **UX-02** | `build` 完成反饋體驗 | 執行 `python yscb.py dev build core` 與 `python yscb.py dev build --all` | 顯示建置步驟、檔案過濾統計與產物輸出路徑。 | ✅ Passed |

---

## 3. Bug 修復記錄 (Defect Log)

### BUG-01: `cli.py` 命令列 desc 參數字串跳脫修正
- **發現於**：代碼生成編譯階段
- **Root Cause & 修復方案**：多行字串生成時引號轉義導致 `strip(""'")` 語法錯誤。已修正為 `strip("\"'")`。
- **回歸確認**：`py_compile` 100% 通過。

### BUG-02: 建立跨模組動態路徑解析機制
- **發現於**：FT-01 CLI 派發測試
- **Root Cause & 修復方案**：在子進程調度模組進入點時，相依模組（如 `core`）位於同層 `modules/` 資料夾，預設 Python 無法跨模組查找套件。修復方案：於進入點自動將 `modules_root` 下的所有子目錄動態注入 `sys.path`。
- **回歸確認**：跨模組導入 100% 成功。

### BUG-03: 多模組工具定址協議規範化
- **發現於**：FT-04 批次建置測試
- **Root Cause & 修復方案**：在處理多模組情境時，使用 `module.source.root://<name>` 與 `module.build.root://<name>` 作為明確的來源/目標根定址協議，徹底避免 `{module}` 佔位符與當前模組上下文之混淆。
- **回歸確認**：`FT-01` ~ `FT-04` 100% 通過。

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已於 `./sandbox/` 完成 9 項全量自動化測試矩陣（100% Passed，0 Error / 0 Warning）
- [x] **開發者 UX / 手動測試確認**：開發者明確回覆「通過」，允許進入 Phase 7
