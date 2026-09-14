# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_02_core_contributes_dispatcher_remediation  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  - 修復 `core` CLI `contributes` 指令內部未定義變數與未知子指令分發崩潰（ISSUE-02）：在 `source/core/scripts/cli.py` 中，`contributes()` 於 `else` 分支調用未在函式範疇導入之 `contributes_cmd.cmd(cmd_bags)`，引發 `NameError`。同時其底層模組無 `cmd()` 方法。
  - 正規化子指令分發包裝：建立 `sub_bags` 傳遞切片後參數 `args[1:]` 至 `contributes_list` 與 `contributes_check`，確保 `contributes list <mod>` 與 `contributes check <target>` 能正確提取目標模組名。
  - 當傳入非 `list` / `check` 之未知子指令時，輸出標準錯誤訊息提示可用子指令並回傳狀態碼 1，杜絕執行期未捕獲例外。
- **4 大守門條件合規核驗**：
  1. 修改檔案數：1 個 (`source/core/scripts/cli.py`) $\le 2$ 個（合規）
  2. 總行數預估：修改 15 行 $\le 100$ 行（合規）
  3. Public API 契約：0 變更，維持現有 API 簽名與呼叫約定（合規）
  4. 既有測試守門：`core` 全套 192/192 測試通過率 100% 守門（合規）
- **影響範圍**：`source/core/scripts/cli.py`、單元測試 `source/core/tests/test_contributes_cmd.py`。

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：修改 `source/core/scripts/cli.py` 中的 `contributes()` 分發函式，引入 `sub_bags` 參數切片，並將未知子指令替換為標準友善提示訊息與安全回傳。
- [x] **TASK-02**：於 `source/core/tests/test_contributes_cmd.py` 擴充 CLI 分發整合測試，驗證 `list`、`check` 以及未知子指令之行為。
- **測試案例**：
  - `FT-01`：`contributes list <module>` 正確過濾並成功印出目標模組擴充點（實機與單元測試通過）。
  - `FT-02`：`contributes check <module>` 正確驗證目標模組 Schema（實機與單元測試通過）。
  - `FT-03`：`contributes unknown_sub` 輸出友好錯誤提示並回傳 1，不拋出 `NameError`（實機與單元測試通過）。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - `scripts/cli.py` 之 `contributes()` 增加 `sub_bags` 切片傳遞，並將未定義之 `contributes_cmd.cmd()` 徹底替換為安全友善提示訊息與返回碼 1。
  - `tests/test_contributes_cmd.py` 新增 FT-08 單元測試，覆蓋預設無參數、`list <mod>`、`check <mod>` 及未知子指令防呆。
- **實機測試日誌**：
  - 單元測試：`python yscb.py dev test core` -> 192 Total, 192 Passed, 0 Failed, 0 Skipped (14.931s)。
  - 靜態合規：`python yscb.py dev check core` -> PASSED (0 warnings, 0 errors)。
  - 本地直裝：`python yscb.py install core@build --force` -> Successfully installed。
  - 實機指令驗證：
    - `python yscb.py contributes get knowledge-db spaces` -> `[core:contributes] Unknown subcommand 'get'. Available: list, check`（退出碼 1，無崩潰）。
    - `python yscb.py contributes list knowledge-db` -> 精準輸出 5 個擴充點契約。
    - `python yscb.py contributes check core` -> 驗證通過（Checked 2 file(s)）。
    - `python yscb.py contributes` -> 正確輸出全系統 14 個擴充點清冊。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed`
