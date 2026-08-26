# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：agents-workflow 核心骨架與 SOP 本體遷移 (Core Skeleton & SOP Body Migration)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 計畫類型：Refactor / Migration  
> 狀態：`Confirmed`  
> 擴充項目：無  
> 模板版本：v1.4  

---

## 1. 使用者原始需求與意圖 (User Intent)

本子計畫 `sub_01` 聚焦於 **`agents-workflow` 核心骨架與 SOP 本體遷移**：
- **專注範疇**：SOP 本體流程與骨架遷移。
- **邊界排除 (Explicitly Excluded)**：
  - 暫不包含 `sop_ext://` (ext) 擴充指令。
  - 暫不包含 IDE 指令擴充（如多 IDE 動態轉譯/生成器）。
- **細節描述**：等待開發者敘述具體需求與細節，Agent 嚴禁自行臆測。

---

## 2. 核心決策與三大維度架構規格 (Core Decisions & Architecture)

依據專題調研報告 [R01_core_skeleton_and_sop_redesign.md](./R01_core_skeleton_and_sop_redesign.md)，確立本子計畫之三大維度架構規格：

### 維度 1：純淨通用內核資產劃分 (Pure Generic Kernel)
- **[P00:DR-01] 資產三位一體分類法**：
  - **規範 (`standards/`)**：`DocumentationStandards.md`（文檔標準規範）、`DevelopmentStandards.md`（開發標準規範 SOP 0~7）。
  - **流程 (`workflows/`)**：僅保留 `ContextInit.md`（上下文熱啟動），其餘流程後續詳定義後再逐一移植。
  - **模板 (`templates/`)**：13 大標準模板完全鏡像移植（`P00`~`P07`, `FT_plan`, `umbrella_overview`, `changelog`, `R_research_report`, `handoff`）。
  - **模組通用性**：徹底剝離本專案特化規則，保持模組 100% 抽象通用。

### 維度 2：協議產物工廠化與宣告式依賴注入 (Artifact Factory & Injection)
- **[P00:DR-02] 宣告式 Contributes 規格**：
  - `export`：宣告資產導出註冊（`type`, `source`, `description`）。
  - `insert`：宣告錨點注入註冊（`type: const|uri`, `token`, `value`, `mode: replace|below|above`）。
  - `token`：宣告錨點元數據註冊（`value`, `description`），供自省查詢。
- **[P00:DR-03] 多輪遞迴錨點解算狀態機**：
  - Step 1: 建立文本當前 `<!-- __TOKEN__ -->` 快照紀錄。
  - Step 2: 依模組依賴拓撲順序進行注入（支援多模組對同一 Token 連續 below/above 追加）。
  - Step 3: 根據 (1.) 紀錄移除本輪已解算之 Token 錨點標籤。
  - Step 4: 遞迴檢查是否仍有新 Token：
    - 4.True ➔ 回到 Step 1 啟動下一輪解算。
    - 4.False ➔ 解算收斂完成。
  - Step 5: 保持 `<!-- __URI(...)__ -->` 延遲解算原樣，分流儲存至 `module://exports/{standards|workflows|templates}/`。

### 維度 3：CLI 指令集與 Hook 自治閉環 (CLI Commands & Hook)
- **[P00:DR-04] 工廠與自省 CLI 指令**：
  - `compile` (別名 `build`)：執行 4-Step 工廠物化流水線。
  - `tokens` (別名 `--list-token`)：列出全系統已註冊的 Token 錨點清冊與說明。
  - `list`：列出當前已導出的 Standards、Workflows 與 Templates 清冊。
  - 計畫治理工具鏈（`verify`, `scan`, `archive`）明確留待後續子計畫實作。
- **[P00:DR-05] 微內核 Hook 自治閉環**：
  - 註冊 `scripts/hook.core.py` 監聽 `on_reload` 事件，在 `yscb reload` 後自動觸發編譯物化。

---

## 3. 開放議題與確認紀錄

- [x] **維度 1（資產劃分）**：規範 2 項、流程 1 項、模板 13 項，100% 通用純淨。
- [x] **維度 2（注入工廠）**：export / insert / token Schema 與 5-Step 多輪遞迴解算狀態機。
- [x] **維度 3（CLI 與 Hook）**：`compile`, `tokens`, `list` 與 `hook.core.py` 自治閉環。



