# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：`sub_02_agents_workflow_injection_optimization` (agents workflow 注入內容優化)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 P03 規格書中均有具體 Markdown 文字契約與路徑對應。
- [x] **邊界防護**：EC-01（未命中降級）與 EC-02（Token 結構安全）均有具體規範指引與測試閘門。
- [x] **依賴純淨**：嚴格遵守 NFR-01 (Token 控制) 與 NFR-02 (100% 全量回歸)。
- [x] **測試前置定稿**：P06 測試計畫同步定稿為 `Confirmed`。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- :--- | :---: | :--- |
| **維度 1 (標準規範)** | `docs/knowledge-db/README.md` | Update | 同步更新檢索決策樹與推薦參數說明 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在日常開發中未安裝 `knowledge-db` 或尚未執行第一次 build/index，Agent 查表執行決策樹會否報錯崩潰？  
> 💡 **防護解法**：`knowledge-db search` 在 `sub_01` 中已具備 JIT 智慧熱自愈機制，檢索入口會自動偵測索引並在背景極速建立；若模組未安裝，CLI 也會安全提示，不引發未預期異常。

> ❓ **尖銳問題 2**：`AGENTS.md` 注入過多詳細決策說明，是否會大幅膨脹 System Prompt 導致 Agent 遵循度下降？  
> 💡 **防護解法**：決策樹採用極簡的三步分支（1. 唯一簽章 ➔ grep；2. 明確分類 ➔ 複合詞 search；3. 語意探索 ➔ 語意 search）與清晰條列，將文字量控制在 30 行以內，精煉直觀且 Token 開銷極低。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：編輯 `ys_codebase/source/knowledge-db/assets/KnowledgeAgentsStandards.md`，寫入剛性檢索決策樹、定向閱讀哲學與 Docstring 符號防護規範。
- [ ] **TASK-02**：編輯 `ys_codebase/source/knowledge-db/assets/phase00_guild.md`，更新 Phase 0 定向檢索與 `-s` 參數指引。
- [ ] **TASK-03**：編輯 `ys_codebase/source/knowledge-db/assets/research_guild.md`，更新 Research 調研預檢與複合詞檢索建議。
- [ ] **TASK-04**：編輯 `ys_codebase/source/knowledge-db/assets/phase07_guild.md`，移除強制手動 index 敘述，替換為 JIT 熱自愈說明。
- [ ] **TASK-05**：執行 Stage 2 打包構建 `python yscb_cli.py installer build knowledge-db`。
- [ ] **TASK-06**：執行 Stage 3 回歸測試 `python test/run_regression.py`，確保 100% Passed。
- [ ] **TASK-07**：執行 Stage 4 Dogfooding 同步，重新生成 `agents-workflow` 並核驗 `AGENTS.md` 軟合併無損。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全階段規格定稿**：P01~P04 與 P06 測試計畫確認一致，正式進入 Phase 5 程式碼與資產實作。
