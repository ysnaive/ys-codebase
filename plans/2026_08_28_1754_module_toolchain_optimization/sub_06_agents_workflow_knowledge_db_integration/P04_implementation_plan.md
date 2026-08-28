# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格與 JSON Schema 中均有精確定義與承接
- [x] **邊界防護**：EC-01 ~ EC-03 有具體防禦（未安裝模組自動清理錨點、空空間安全略過、軟合併隔離）
- [x] **依賴純淨**：100% 透過 Contributes JSON 與 Markdown 資產實現，零 Python 業務邏輯飄移 (NFR-01)
- [x] **測試定稿**：P06 測試案例 (FT-01 ~ FT-06, ET-01, RT-01) 已完成前置映射與剛性定稿

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 3** | `docs/knowledge-db/README.md` | Update | 補充說明 Space 雙向聚合體系（`agents-workflow` 貢獻 `docs` 空間、專案特化 `source` 空間、模組預設空空間） |
| **維度 4** | `docs/agents-workflow/README.md` | Update | 補充說明 `AGENTS_STANDARDS` 錨點與多模組行為準則注入機制 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若專案 `config/knowledge-db/contribute.json` 尚未建立或未宣告 `source` 空間，會發生什麼事？  
> 💡 **防護解法**：`SpaceManager` 設計為純宣告式載入，若專案未宣告 `source` 空間，系統僅載入由 `agents-workflow` 貢獻之 `docs` 空間，`knowledge-db status` 正常印出清單，不拋出任何未捕獲例外，完全符合漸進增量配置原則。

> ❓ **尖銳問題 2**：`AgentsStandards.md` 尾部追加 `__@{AGENTS_STANDARDS}__` 是否會干擾 Section 4 使用者自訂專案規範？  
> 💡 **防護解法**：錨點位於中央標準區塊 (`<!-- YSCB_AGENTS_BEGIN -->` ... `<!-- YSCB_AGENTS_END -->`) 內部，`ReleasePublisher` 的 `_soft_merge_agents_md` 僅比對並更新中央標記區塊，Section 4 位於標記區塊之外，100% 受到軟合併防護，絕對零損毀。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：清空 `source/knowledge-db/configurable/contribute.json` 預設空間 (FR-01)
- [ ] **TASK-02**：建立本專案 `config/knowledge-db/contribute.json` 宣告 `source` 空間 (FR-03)
- [ ] **TASK-03**：更新 `source/agents-workflow/assets/standards/AgentsStandards.md` 補齊錨點，並於 `agents-workflow.json` 宣告 Token (FR-04)
- [ ] **TASK-04**：建立 `source/agents-workflow/contributes/knowledge-db.json` 宣告 `docs` 空間 (FR-02)
- [ ] **TASK-05**：於 `source/knowledge-db/assets/` 建立 4 個平鋪標準資產 (`KnowledgeAgentsStandards.md`, `phase00_guild.md`, `research_guild.md`, `phase07_guild.md`) (FR-05)
- [ ] **TASK-06**：建立 `source/knowledge-db/contributes/agents-workflow.json` 宣告 `insert` 注入映射 (FR-06)
- [ ] **TASK-07**：更新單元測試並執行全生態系沙盒回歸跑測 (FT-01 ~ FT-06, ET-01, RT-01)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 雙向 Contributes 剛性定稿**：確認 `agents-workflow` 向 `knowledge-db` 提供 `spaces.docs`，`knowledge-db` 向 `agents-workflow` 提供 `AGENTS_STANDARDS` 與 JIT 註解。
- **[P04:DR-02] 測試全域覆蓋**：以單元測試覆蓋 Space 聚合、Compiler 錨點展開與發布軟合併。
