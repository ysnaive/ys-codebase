# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在架構設計 (P02) 與介面規格 (P03) 中均有 1:1 明確對應。
- [x] **邊界防護**：EC-01 (未注入自動 Purge)、EC-02 (短歷史適應)、EC-03 (全合規簡約呈現) 均有完整策略。
- [x] **依賴純淨**：符合 NFR-01~03 約束，保持 `agents-workflow` 核心 100% 通用解耦。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `contributes.format.md` | Modify | 新增 `RETRO_CHECK_ITEMS` 擴充宣告語法與 `knowledge-db` / `core` 注入範例說明 |
| **維度 4** | `assets/standards/DevelopmentStandards.md` | Modify | 於工作流導引章節追加 `/Retro` 自檢工作流與使用定位 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若下游模組（如 `knowledge-db`、`core`）透過 `insert` 多 Donor 同時注入 `RETRO_CHECK_ITEMS`，注入順序與排版是否會混亂？  
> 💡 **防護解法**：複用已於 `sub_02` / `sub_03` 驗證之 `compiler.py` 多 Donor 聚合機制，依據 topological order 依序向下插入（`mode: below`），並在各模組規範中強制採用標準 H4 標題與清單縮排，確保 Markdown 語法層級完全一致。

> ❓ **尖銳問題 2**：若無任何模組注入 `RETRO_CHECK_ITEMS`，編譯產物是否會遺留空的錨點或破壞文檔？  
> 💡 **防護解法**：`compiler.py` 的 `compile_stage1` 於所有注入處理完畢後，強制執行 `make_purge_regex` 抹除殘留標籤行，自動吞噬整行縮排與換行，達成 0 殘留。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：新建 `source/agents-workflow/assets/workflows/Retro.md` 工作流資產（含頂部文檔溯源剛性紀律、核心自檢異常過濾、`__@{RETRO_CHECK_ITEMS}__` 與 `__@{WORKFLOW_RETRO}__` 錨點）。
- [ ] **TASK-02**：於 `source/agents-workflow/contributes/agents-workflow.json` 註冊 `Retro.md` 導出與 `RETRO_CHECK_ITEMS` / `WORKFLOW_RETRO` Token。
- [ ] **TASK-03**：更新 `source/agents-workflow/contributes.format.md` 與 `source/agents-workflow/assets/standards/DevelopmentStandards.md`。
- [ ] **TASK-04**：於 `source/agents-workflow/tests/test_compiler.py` 新增單元測試 `test_retro_workflow_export_and_token`。
- [ ] **TASK-05**：實機執行 `python yscb.py dev test agents-workflow` 與自引用物化 `python yscb.py install agents-workflow@build --force`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全流程 Test-First 與自檢完整性**：
  - 嚴格落實 P06 測試前置定稿，所有 TASK 實作後必須 100% 通過單元、契約與回歸測試，方能放行本機物化。
