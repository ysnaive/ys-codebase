# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書與架構設計中有具體承接介面
- [x] **邊界防護**：EC-01 ~ EC-03 具備具體錯誤處理與容錯策略
- [x] **依賴純淨**：符合 NFR 指標約束，無非法模組相依

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | Modify | 增補 `plan check` / `plan verify` CLI 使用說明與 API 簽名 |
| **維度 3** | `docs/agents-workflow/TOPICS/plan_verification.md` | New | 5 步檢核流水線架構與嚴格合規規範說明 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：動態模板標題鏡像對齊時，如何防止因標題副標題或中英空白產生誤報？  
> 💡 **防護解法**：`PlanVerifier` 採用章節標題正規化比對 (Normalized Title Match) 策略，去除前綴 `#`、數字編號、符號與空白後進行包含與主幹比對。

> ❓ **尖銳問題 2**：CLI 在全數 Pass 與有問題時如何做到視覺噪聲完全隔離？  
> 💡 **防護解法**：排版格式化器採用篩選流水線，僅在有問題時展開清單，並自動隱藏 Pass 檔案，達成 Noise-Free 聚焦診斷。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (PlanVerifier 核心引擎與 5 步流水線升級)**：
  - [x] 在 `source/agents-workflow/agents_workflow/plans/verifier.py` 定義 `PlanSeverity`, `PlanIssue`, `PlanReport`。
  - [x] 實作動態模板標題解析 (`_load_resolved_template_headers`)。
  - [x] 實作 5 步檢核流水線：巢狀目錄與 Umbrella 結構 (FR-05), changelog 合規 (FR-04), Header 元數據 (FR-03), 佔位符與 HTML 註解檢測 (FR-06), 動態 Header 鏡像對齊 (FR-01), 標準 ID 前綴與 FT/ET 測試 (FR-02)。
- [x] **TASK-02 (PlanArchiver 剛性守門阻斷整合)**：
  - [x] 在 `source/agents-workflow/agents_workflow/plans/archiver.py` 整合 `PlanVerifier` 檢核，當存在 `[FAIL]` 且未加 `--force` 時剛性阻斷。
- [x] **TASK-03 (CLI 噪聲抑制排版與格式化輸出)**：
  - [x] 升級 `source/agents-workflow/scripts/cli.py` 中 `cmd_plan_check` / `cmd_plan_verify`，實作全 Pass 單行收斂、有錯時自動隱藏 Pass 文件、以及 `--json` 格式化輸出。
- [x] **TASK-04 (單元測試與沙盒回歸)**：
  - [x] 建立/更新 `source/agents-workflow/tests/test_plans_toolchain.py` 覆蓋 FT-01~07 與 ET-01~02。
  - [x] 執行全模組 `python yscb.py dev test --all` 沙盒回歸跑測。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[sub_04:P04:DR-01] 5 步流水線解耦與動態模板比對**：確立動態載入模板標題進行鏡像比對，保障專案規範之確定性。
- **[sub_04:P04:DR-02] 歸檔守門剛性阻斷**：任何未通過合規檢核之計畫不得歸檔，維護歷史庫純淨。
