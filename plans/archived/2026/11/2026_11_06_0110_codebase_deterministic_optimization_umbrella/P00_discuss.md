# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全專案八大模組確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 狀態：In Progress  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `ys-codebase` 除 `gdrive-support` 以外之全部 8 個模組（`vscode-support`、`server`、`file-space`、`dev`、`knowledge-db`、`agents-workflow`、`ast`、`core`），分別針對業務程式碼（依 `/code-optimizer` `D1~D5` 與 `S1~S6` 加上實作邏輯與併發修復）與測試程式碼（依 `testing-sop` `T-01~T-06` 與 `D1~D5`）執行五步盲測子代理閉環（最多 3 輪，達成 `P0=0, P1=0, P2=0` 即觸發融斷）。
- **核心目標**：對外 SDK 與 CLI 維持 Mode B 100% 向下相容，內部私有輔助函式採 Mode A 收斂，並確保全數單元測試 100% 通過且 `0 ResourceWarning`、`Checker` `0 FAIL, 0 WARN`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `issue_report.md` 判定鐵律**：僅限真正的「功能缺失（尚未設計或未實作的功能規格、需跨模組新增架構契約之能力缺口）」方可記入 `issue_report.md` 並忽略；凡屬「實作邏輯錯誤、併發問題、非同步生命週期缺陷、狀態失步、資源洩漏、型別與邊界防禦疏失」，一律於子計畫內直接修復並由單元測試驗證。
- **[P00:DR-02] 相容性模式**：外部公開 SDK 與 CLI 採 `Mode B`（100% 向後相容）；內部零跨模組引用之私有輔助函式與測試內部結構採 `Mode A`（單一正典入口，零轉發殼層）。

---

## 3. 開放議題與確認紀錄

- 6 個無遺留功能缺失之子計畫（`sub_03_file_space` ~ `sub_08_core`）執行 Review Gate 與 P07 結案；`sub_01_vscode_support` 與 `sub_02_server` 因尚存 `issue_report.md` 跨模組功能缺失項，維持 `Passed` 待後續決策。
