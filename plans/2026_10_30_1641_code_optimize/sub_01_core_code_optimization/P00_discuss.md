# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_code_optimization  
> 建立日期：2026-10-30  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `core` 模組執行 `/code-optimizer` 技能審查，採用可破壞性變更（`Mode A`），並將雙子代理（Auditor A / Auditor B）高收斂共識之優化報告整理為分類型主計畫 `code_optimize` 下的 `sub_01: R01` 調研報告。
- **核心目標**：
  1. 以「單一模組（`ys_codebase/source/core/`，含 `core/` 與 `scripts/cli.py`，共 21 檔 / 7,611 LOC）」為檢視範圍，落實包含式階層（`單一模組 ⊃ 單一檔案`），完整涵蓋跨檔依賴拓撲、`S1` 業務階段拆解與 `S2` 無狀態邏輯剝離。
  2. 以「`Mode A：新功能收斂期（Convergence Mode / 可破壞性變更）`」為生命週期模式，盤點所有薄轉發層、相容別名、廢棄空表與 0 調用死代碼，給出單一正統入口收斂清單與跨模組調用遷移影響面。
  3. 產出 [`R01_code_optimization_audit.md`](./R01_code_optimization_audit.md) 調研報告，作為後續升級 `Full Track`（或跨模組同步遷移）之唯一規格基線。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段為 `R01` 靜態診斷與重構處方立項階段，不直接修改 `ys_codebase/source/core/` 生產代碼或 `tests/` 測試案例。
- **架構影響範圍**：
  - 調研診斷標的：`ys_codebase/source/core/core/`（20 檔）與 `ys_codebase/source/core/scripts/cli.py`（1 檔）。
  - 跨模組入向調用盤點範圍：`ys_codebase/source/dev/`、`ys_codebase/source/agents-workflow/`、`ys_codebase/source/knowledge-db/`、`ys_codebase/source/server/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 檢視範圍與生命週期定錨（`Module Scope` × `Mode A`）**：
  - 範圍鎖定 `ys_codebase/source/core/` 全部 21 支業務源碼檔（7,611 LOC），並依包含式範圍原則逐一深入各檔案內部執行 `S1` 階段拆解與 `S2` 無狀態剝離。
  - 生命週期鎖定 `Mode A（新功能收斂期 / 可破壞性變更）`：對歷史遺留之薄轉發層（如 `uri.py` 底部 15 個 VFS 轉發函式）、相容別名（`Config`、`emit`、`translate`、`get_execution_context`、`isfile`/`isdir`、`cli.py` 底部 `cmd_*` 轉發等）與 0 調用死代碼採零容忍物理清除策略，並完整列出內部與跨模組調用方同步更新清單。
- **[P00:DR-02] 雙子代理獨立盲測交叉驗證收斂**：
  - 經兩個獨立子代理（Auditor A 與 Auditor B）平行執行五維度靜態診斷，兩者在基線盤點（21 檔 / 7,611 LOC）、`Mode A` 轉發層/別名/死代碼座標（含 `engine.py:_seed_or_update_config` 死方法內殘留 `core` 初次 `locale` 初始化之隱藏瑕疵）、9 大巨型類別/長函式之 `S1/S2` 拆解標的，以及跨檔重複邏輯（5 處 `_resolve_yscb_root`、2 處 `.gitignore` 合併、4 處 CLI 群組 Help 渲染）達成 >90% 實質重疊，現將兩者共識與互補亮點完整收斂入 `R01_code_optimization_audit.md`。

---

## 3. 開放議題與確認紀錄

- 已完成 `R01_code_optimization_audit.md` 調研報告落檔，待開發者後續檢閱並裁決流轉出口（出口 ① 原地升級 `Full Track` 執行重構、出口 ② 轉入 `/roadmap` 或 `/todo`、出口 ③ 結案存檔）。

