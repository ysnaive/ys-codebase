# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_06_agents_workflow 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `ys_codebase/source/agents-workflow/` 模組（含 22 個業務程式碼檔案與 8 個測試程式碼檔案）執行雙目標五步盲測子代理閉環優化（`OPT-01 ~ OPT-18` 與 `AUD-01 ~ AUD-32`）。
- **核心目標**：依 `/code-optimizer` (`D1~D5` & `S1~S6`) 執行確定性結構收斂並直接修復所有實作邏輯錯誤、併發問題與邊界防禦缺漏；依 `testing-sop` (`T-01~T-06`) 純化測試套件，達成 `142 / 142` 測試 100% 通過且 `0 ResourceWarning`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 原業務缺失判定鐵律**：僅限真正的「功能缺失（尚未設計或未實作的功能規格、需跨模組新增架構契約之能力缺口）」方可登錄 `issue_report.md` 忽略；凡屬「實作邏輯錯誤、併發問題、非同步生命週期缺陷、狀態殘留、資源洩漏、型別與邊界防禦疏失」，一律於本子計畫內直接修復並補齊單元測試。
- **[P00:DR-02] 相容性模式**：對外公開 SDK 與 CLI 採 `Mode B`（100% 向下相容）；模組內部零跨模組引用之私有輔助函式與測試內部輔助採 `Mode A`（單一權威入口、零轉發殼）。

---

## 3. 開放議題與確認紀錄

- 經五步盲測閉環（A1/A2 -> B1/B2 -> C1/C2 -> D -> E）驗證，本模組 `issue_report.md` 為 `0` 項遺留功能缺失，已達 `P0=0, P1=0, P2=0` 融斷標準並完成 P07 結案。
