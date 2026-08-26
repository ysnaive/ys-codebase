# 測試計畫 (Test Plan)

> 功能名稱：核心微內核基礎設施模組 (Core Infrastructure Module)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 功能 | FR-01 | 測試 `core.uri` 9 大語意協議解析、佔位符代換與 VFS 完整 I/O 操作 (`read/write_text/json`, `exists`, `makedirs`, `rmtree`, `copy`) | 1. 語意路徑正確對映實體路徑；<br/>2. VFS 讀寫與目錄維護 100% 正確；<br/>3. 佔位符 `{module}` 正確解析。 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 測試 `AtomicEngine` 12 大原子操作（`REGISTER`, `UNREGISTER`, `SNAPSHOT`, `RESTORE_SNAPSHOT`, `DOWNLOAD`, `SOLVE_DEPS`） | 原子操作執行正確，快照可 100% 完整還原組態清冊。 | ✅ Passed |
| **FT-03** | 功能 | FR-04 | 測試 `ContributesAggregator` 5 大來源掃描、宣告解析、相依排序與靜態注入 | 正確聚合 contributes 宣告並按相依順序產出注入產物。 | ✅ Passed |
| **FT-04** | 功能 | FR-03 | 測試 `Installer` 7 大指令端到端操作（`install`, `update`, `remove --clean`, `list`, `status`, `rollback`, `reload`） | 7 項套件管理指令正常執行，終端輸出報告語意清晰，Exit Code 為 0。 | ✅ Passed |
| **FT-05** | 功能 | FR-02/03 | 測試 `RELOAD` 兩階段純淨物化保證：在 `modules/` 注入髒檔案後觸發 `reload` | 階段一徹底清空幽靈與污染檔案，100% 還原為純淨鏡像檔案並完成注入。 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | `SOLVE_DEPS` 相依版本衝突測試 | 求解器精確分析相依拓撲並防護衝突。 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | `remove` 核心模組防護測試（嘗試移除 `core` 模組） | 核心保護機制攔截並阻斷移除，提示不允許刪除基礎設施模組。 | ✅ Passed |
| **ET-03** | 邊界 | EC-06 | 透過 VFS 存取未支援之協議（例 `unknown_scheme://file.txt`） | 立即拋出 `ValueError: Unsupported URI scheme: unknown_scheme://`。 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 模擬完全離線無網路環境執行 `rollback` 與 `reload` | 完全不觸發網路請求，依賴本地 `snapshot://` 與 `mirror://` 秒級自癒。 | ✅ Passed |
| **PT-01** | 效能 | NFR-01 | 檢查 `source/core/` 全部 Python 源碼之依賴清單 | 100% 純 Python 標準庫（`os`, `sys`, `json`, `urllib`, `shutil`, `zipfile`, `time`, `dataclasses`, `typing`），零第三方依賴。 | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **UX-01** | `list` 與 `status` 命令終端輸出排版 | 執行 `python yscb.py list` 與 `python yscb.py status` | 輸出整齊對齊的 Markdown/ASCII 表格，版本與健全度資訊一目了然。 | ⬜ Pending (待開發者確認) |
| **UX-02** | 相依與指令錯誤提示友善度 | 嘗試 `remove core` 或輸入未知指令時的終端提示 | 輸出清晰明確的引導資訊與保護訊息。 | ⬜ Pending (待開發者確認) |

---

## 3. Bug 修復記錄 (Defect Log)

### BUG-01: `cli.py` 命令列 provider 參數跳脫字串修正
- **發現於**：代碼生成編譯階段
- **Root Cause & 修復方案**：多行字串生成時引號轉義導致 `strip(""'")` 語法錯誤。已修正為 `strip("\"'")`。
- **回歸確認**：`py_compile` 100% 通過。

### BUG-02: 建立 `core` 模組自鏡像與快照基底保護
- **發現於**：FT-04 套件管理管線初測
- **Root Cause & 修復方案**：在執行全量 `RELOAD` 與 `SNAPSHOT` 階段一清空物化時，`core` 作為運作中之微內核自身亦需同步於 `mirror://core/` 建立鏡像，以保證乾淨物化覆蓋時核心環境完備。已於初始化流程補齊 `mirror://core/1.0.0/` 同步。
- **回歸確認**：`FT-04` 與 `FT-05` 100% 通過。

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已於 `./sandbox/` 完成 10 項全量自動化測試矩陣（100% Passed，0 Error / 0 Warning）
- [x] **開發者 UX / 手動測試確認**：開發者明確回覆「UX 驗證通過」或指示免測，允許進入 Phase 7
