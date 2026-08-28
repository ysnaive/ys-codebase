# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 建立 `knowledge-db` 與 `agents-workflow` 之間的雙向 Contributes 宣告式協同。
  - 清空 `source/knowledge-db/configurable/contribute.json` 預設空間，消除模組硬編碼假設。
  - 由 `agents-workflow` 透過 `contributes/knowledge-db.json` 貢獻 `docs` 空間（指向 `workflow.docs://`）。
  - 由本專案透過 `config/knowledge-db/contribute.json` 宣告專案特化之 `source` 源碼空間（指向 `project://source`, `project://ys_codebase`）。
  - 於 `AgentsStandards.md` 底部補齊 `AGENTS_STANDARDS` 擴充錨點。
  - 注入平鋪標準資產（檢索優先紀律、Docstring 結構防護、SOP search/index JIT 指引）。
- **核心目標**：
  - 模組完全解耦、零硬編碼假設。
  - 透過宣告式 Contributes 自動化注入行為準則與 JIT 操作指引。
- **邊界排除 (Explicitly Excluded)**：
  - 空間邊界防護計算（避免 Agent 過度計算空間反模式）。
  - 維度 2（STANDARD 擴充）：確認無需求，予以排除。
  - 修改 `knowledge-db` 或 `agents-workflow` 底層 Python 業務代碼。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Space 空間解耦**：清空 `knowledge-db` 預設空間，改由 `agents-workflow` 貢獻 `docs` 空間，專案 config 貢獻 `source` 空間。
- **[P00:DR-02] 錨點修正**：確認於 `AgentsStandards.md` 底部補齊 `AGENTS_STANDARDS` 錨點並宣告 Token。
- **[P00:DR-03] SOP 聚焦**：確認 SOP JIT 註解聚焦於「引導 search 精準查找」與「Phase 7 調用 index 更新索引庫」。
- **[P00:DR-04] 資產平鋪存放**：所有知識庫標準資產平鋪存放於 `source/knowledge-db/assets/`，不分多層子目錄。

---

## 3. 開放議題與確認紀錄

- [x] 完成 Phase 0 意圖與情境釐清。
- [x] 確認採 Level 1 (Full Track) 推進。
