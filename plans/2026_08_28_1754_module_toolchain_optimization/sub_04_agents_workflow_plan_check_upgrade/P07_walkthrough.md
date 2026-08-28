# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

本子計畫 (`sub_04_agents_workflow_plan_check_upgrade`) 全面升級了 `agents-workflow` 模組中的開發計畫檢核與規範守門體系 (`PlanVerifier` & `plan check`)：
1. **動態模板章節標題鏡像核對 (`[FAIL]`)**：
   - `PlanVerifier` 動態讀取 `.cache/agents-workflow/resolved_contents/templates/<template>.md`（展開後之標準模板），提取 Markdown `# Header`，檢查產出文件是否 100% 具備並鏡像對應模板章節標題，缺漏標記 `[FAIL]`。
2. **5 步計畫合規流水線 (5-Stage Verification Pipeline)**：
   - **Stage 1 (Structure & Depth Guard)**：目錄層級限制 $\le 2$ 層，Umbrella 主計畫 `umbrella_overview.md` 存在性與清冊一致性。
   - **Stage 2 (Changelog Integrity Guard)**：`changelog.md` 伴隨存在性、標準表格與有效紀錄。
   - **Stage 3 (Dynamic Template Resolver)**：動態載入模板標題解析。
   - **Stage 4 (Markdown File & ID Guard)**：Header 元數據完整性、佔位符與嚴禁殘留任何 HTML 註解、標準 ID 前綴格式 (`FR-XX`, `EC-XX`, `FT-XX`, `ET-XX`)。
   - **Stage 5 (Severity Aggregator)**：三級嚴重度聚合 (`[PASS]`, `[WARN]`, `[FAIL]`) 與向下相容 Tuple 解包支援。
3. **Noise-Free 聚焦終端排版與機器可讀輸出**：
   - 全數通過時單行收斂 (`[*] Plan: <name> [PASS]`)；有違規時自動隱藏 Pass 檔案，僅聚焦展示 Fail/Warn 問題項目與行號。
   - 支援 `--json` 格式化輸出。
4. **PlanArchiver 剛性歸檔守門阻斷**：
   - `plan archive` 在歸檔前自動執行 plan check，若存在 `[FAIL]` 且未加 `--force` 時剛性阻斷歸檔。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 實作 5 步檢核流水線、動態模板 Header 鏡像核對、佔位符/HTML 註解偵測與 PlanReport 資料結構 |
| `source/agents-workflow/agents_workflow/plans/archiver.py` | Modify | 整合 PlanVerifier 剛性歸檔守門阻斷機制 |
| `source/agents-workflow/agents_workflow/plans/__init__.py` | Modify | 匯出 PlanSeverity, PlanIssue, PlanReport |
| `source/agents-workflow/scripts/cli.py` | Modify | 升級 `cmd_plan` 支援 `plan check` / `plan verify`、Noise-Free 排版與 `--json` |
| `source/agents-workflow/contributes/core.json` | Modify | 增補 `plan check` 指令說明 |
| `source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 重構單元測試覆蓋 FT-01~07 與 ET-01~02 檢核案例 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：全生態系 4 大模組沙盒回歸測試 **178/178 Passed (100% Ready, 12.008s)**。
- **實機 UX / CLI 驗證**：
  - 實機執行 `python yscb.py agents-workflow plan check 2026_08_28_1754_module_toolchain_optimization/sub_04_agents_workflow_plan_check_upgrade`：**100% PASS**（單行收斂無雜訊）。
  - 實機執行 `--json` 輸出：正確生成結構化 JSON 物件。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | ✅ 已更新 | 增補 `plan check` / `plan verify` CLI 使用說明與 API 簽名 |
| **維度 3** | `docs/agents-workflow/TOPICS/plan_verification.md` | ✅ 已交付 | 5 步檢核流水線架構與嚴格合規規範說明 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow,plan): upgrade plan verification toolchain with dynamic template header alignment and noise-free diagnostic output

- Implement 5-stage plan verification pipeline in `PlanVerifier`: structure/depth guard, changelog guard, dynamic template resolver, markdown/ID guard, severity aggregator.
- Add dynamic template `#Header` mirroring verification against `.cache/agents-workflow/resolved_contents/templates/`.
- Enforce strict detection of placeholders and HTML comments (<!-- ... -->) across plan files.
- Introduce `PlanSeverity` ([PASS], [WARN], [FAIL]), `PlanIssue`, and `PlanReport` with backward-compatible tuple unpacking.
- Upgrade `plan check` / `plan verify` CLI with noise-free terminal formatting (mute passed files) and `--json` support.
- Integrate rigid validation gate in `PlanArchiver.archive_plan()` to block invalid plans without `--force`.
- Pass 178/178 hermetic regression tests across all 4 modules.
```
