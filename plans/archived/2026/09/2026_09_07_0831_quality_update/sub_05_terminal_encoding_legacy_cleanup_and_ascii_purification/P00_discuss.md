# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (Terminal Encoding Guard, Legacy Cleanup, ASCII Purification & Test Mark Passed)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：在主計畫 `2026_09_07_0831_quality_update` 下開立子計畫，修復釋出評估中除版本號以外的所有問題，並完全捨棄所有特殊字元。
- **核心目標**：
  1. **特殊字元徹底捨棄 (Complete ASCII Purification)**：全面移除全生態系 CLI 輸出、Help 渲染器（`HelpRenderer`）、日誌與診斷訊息中的所有 Emoji 與特殊 Unicode 字符（如 `🟢`、`🟡`、`🔴`、`🚨`、`🛡️`、`✨`、`📦` 等），全數替換為純 ASCII / 純文字標記（如 `[SAFE]`、`[CONDITIONAL]`、`[GATED]`、`[WARN]`、`[ERROR]`、`[PASS]`），徹底根除不同編碼終端（如 Windows CP950）之字符編碼相容性風險。
  2. **Windows 終端編碼雙重防護 (Windows UTF-8 Encoding Guard)**：在 `yscb.py` 宿主與 `core` 派發進入點，主動對 `sys.stdout` 與 `sys.stderr` 進行安全 UTF-8 重組與 `errors='replace'` 容錯防護。
  3. **舊版殘留架構清理 (Legacy Artifacts Cleanup)**：
     - 徹底刪除 `source/core/contributes.format.md`、`source/server/contributes.format.md`、`source/knowledge-db/contributes.format.md`。
     - 將 `source/knowledge-db/configurable/contribute.json` 修正為標準 `config.*.json` 命名。
  4. **測試狀態閉環標記 (Test Mark Passed Closure)**：為 `agents-workflow` (44 處) 與 `core` (17 處) 所有缺少 `self.mark_passed()` 的歷史測試案例補齊呼叫，使全生態系 511 測試達到 100% 顯式 Passed 閉環。
  5. **沙盒平行跑測穩定性與效能寬裕度加固**：微調 `test_pt_01_uri_resolve_perf` 效能評估門檻與沙盒環境建立之檔案鎖重試防護。
- **邊界排除 (Explicitly Excluded)**：
  - **暫不晉升版本號**：版本號（`bump-*`）與正式發布（`release`）留待後續由開發者另行授權指示執行。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全生態系 CLI 輸出全面純文字化 (ASCII/Plain Text Standard)**：
  - 放棄所有裝飾性 Emoji，全數改用國際標準方括號文字標記：`[SAFE]`、`[CONDITIONAL]`、`[GATED]`、`[PASS]`、`[FAIL]`、`[WARN]`、`[INFO]`。
  - 確保在任何無 UTF-8 支援或特化 Code Page（CP950、CP437、ASCII）的終端環境均能 100% 穩定渲染且零字元斷裂。
- **[P00:DR-02] yscb 進入點標準輸出防禦性編碼重組**：
  - 在 `yscb.py` 頂層與 `core.commands.dispatcher` 派發前，探測 `sys.stdout.reconfigure` 並安全啟用 UTF-8 編碼與字元置換防崩潰保護。
- **[P00:DR-03] 歷史測試 mark_passed 閉環與靜態檢核 0 Warning 達成**：
  - 補齊 `agents-workflow` 與 `core` 測試案例的 `self.mark_passed()`，使 `dev check --all` 與 `dev test --all` 達到 0 Failed / 0 Warning / 0 Unknown 的最高品質指標。

---

## 3. 開放議題與確認紀錄

- [x] 是否包含版本號升級？否（依指示排除版本號變更，僅聚焦程式碼、契約、清理與測試完善）。
- [x] 是否影響既有 Public API？否（純內部輸出渲染優化、殘留清理與測試補齊，0 破壞性變更）。
