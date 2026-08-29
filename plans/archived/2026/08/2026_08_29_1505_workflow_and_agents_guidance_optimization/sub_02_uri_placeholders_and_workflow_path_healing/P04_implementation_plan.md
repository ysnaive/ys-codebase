# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-03 在 `compiler.py`、資產清單與測試中有具體承接。
- [x] **邊界防護**：EC-01 (空格容錯)、EC-02 (複合多佔位符)、EC-03 (未知協議降級) 有具體防護。
- [x] **依賴純淨**：符合 NFR-01 (208+ 測試 Passed) 與 NFR-02 (合法 CommonMark)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 新增 `[DN-AW-08]` 記錄 Stage 2 佔位符二分法解析與反引號剝除架構決策 |
| **維度 3** | `docs/agents-workflow/FACTORY_PIPELINE.md` | Modify | 更新 Stage 2 解析流程說明與 Standalone/Inline 範例 |
| **維度 7** | `project://CHANGELOG.md` | Append | Phase 7 追加 `sub_02` 發布日誌 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在 Markdown 中撰寫 `` `__#{uri}__` ``，但其意圖本來就是要作為 code block 展示路徑而非超連結，剝除反引號是否會改變原意？  
> 💡 **防護解法**：在 Markdown 中，若欲展示程式碼區塊，標準做法為雙反引號或顯式代碼標籤（如 ```` `__#{uri}__` ```` 或 `<code>__#{uri}__</code>`）；佔位符系統的唯一語意即為被動路徑轉譯。若需在生成文本中呈現 code 樣式，寫作者可在外層加上代碼樣式（如 `` `__${project://AGENTS.md}__` `` 在非 Standalone 情境下自然保留反引號）。此外，所有標準工作流與模板超連結均為 `[text](`__#{uri}__`)`，完全替代後精確回歸合法的 `[text](url)`。

> ❓ **尖銳問題 2**：將工作流檔案中的 `__#{...}__` 換為 `__${...}__` 後，若該工作流被發布至其他 IDE 平台（如 Claude、Codex），路徑是否仍然相對於專案根目錄正確運作？  
> 💡 **防護解法**：是的。`__${...}__` 協議由 `resolve_stage2_uri` 統一以 `project_root` 計算相對路徑，不受目標檔案投影至 `.agents/`、`.claude/` 或 `.codex/` 巢狀深度的影響，確保所有平台下的 Agent 均能在專案根目錄 CWD 下精準直達。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：修改 `source/agents-workflow/agents_workflow/compiler.py`，實作 `resolve_stage2_uri` 的 Standalone vs Inline 二分法。
- [ ] **TASK-02**：批次校正 `source/agents-workflow/assets/` 下的工作流、標準與模板檔案（`ContextInit.md` 等），全面切換 Agent 讀檔動線為 `__${...}__` 並修復非標準協議前綴。
- [ ] **TASK-03**：在 `source/agents-workflow/tests/test_compiler.py` 新增單元測試，覆蓋 Standalone 剝除反引號、Inline 保留反引號與 Markdown 連結場景。
- [ ] **TASK-04**：執行全生態系構建與測試驗證（`dev test` + `run_regression.py` 100% Passed）。
- [ ] **TASK-05**：執行 Dogfooding 同步部署至消費空間（`install` + `--ide-antigravity`），並驗證物化產物。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：確認 Stage 2 佔位符二分法解析機制與反引號剝除規則定稿。
- **[P04:DR-02]**：確認全工作流 Agent 讀檔動線全面採用 `__${...}__` 定稿。
