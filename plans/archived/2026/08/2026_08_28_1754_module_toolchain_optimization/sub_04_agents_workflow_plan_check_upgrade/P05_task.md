# 實作任務清單 (Task Breakdown)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

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

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **DEV-01** | Minor | 將 `module.source://` 改為 `ArtifactCompiler` 動態解析模板以嚴格遵守三層空間邊界 | 直接改用微內核 SDK 與快取路徑解析 |
