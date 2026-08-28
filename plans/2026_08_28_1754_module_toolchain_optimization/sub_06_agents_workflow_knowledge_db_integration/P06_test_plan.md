# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Passed  
> 模板版本：v1.3  


---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `knowledge-db/configurable/contribute.json` 預設 spaces 為空字典 | FR-01 | `test_space.py` / `load_spaces()` |
| **FT-02** | 整合測試 | 驗證 `agents-workflow` 宣告之 `docs` 空間被 `SpaceManager` 正確載入 (`origin="module:agents-workflow"`) | FR-02 | `test_space.py` / `load_spaces()` |
| **FT-03** | 整合測試 | 驗證專案特化 `config/knowledge-db/contribute.json` 宣告之 `source` 空間被正確載入 | FR-03 | `test_space.py` / `load_spaces()` |
| **FT-04** | 單元測試 | 驗證 `AgentsStandards.md` 包含 `__@{AGENTS_STANDARDS}__` 且發布時無殘留佔位符 | FR-04 | `test_compiler.py` / `compile_stage1()` |
| **FT-05** | 發布測試 | 驗證 `agents-workflow release` 後，生成的 `AGENTS.md` 正確包含 `KnowledgeAgentsStandards.md` 內容 | FR-05, FR-06 | `test_publisher.py` / `release_all()` |
| **FT-06** | 發布測試 | 驗證 `P00` 與 `P07` 模板頂部 JIT 註解正確注入 `search` 與 `index` 指引 | FR-05, FR-06 | `test_publisher.py` / `release_all()` |
| **ET-01** | 邊界防禦 | 驗證未安裝 `knowledge-db` 時 `agents-workflow` 發布不崩潰且無未匹配標籤 | EC-01 | `test_compiler.py` |
| **RT-01** | 全生態系回歸 | 全生態系 4 大核心模組沙盒跑測維持 100% Passed (181+ 案例) | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |

| **FT-01** | `Passed` | 實機驗證 `knowledge-db/configurable/contribute.json` 預設 spaces 為空字典 | 2026-08-28 21:19 |
| **FT-02** | `Passed` | 實機驗證 `agents-workflow` 宣告之 `docs` 空間被 `SpaceManager` 載入 | 2026-08-28 21:19 |
| **FT-03** | `Passed` | 實機驗證專案特化 `config/knowledge-db/contribute.json` 之 `source` 空間載入 | 2026-08-28 21:19 |
| **FT-04** | `Passed` | 實機驗證 `AgentsStandards.md` 包含 `__@{AGENTS_STANDARDS}__` 且無殘留佔位符 | 2026-08-28 21:19 |
| **FT-05** | `Passed` | 實機驗證 `agents-workflow release` 後，`AGENTS.md` 成功注入知識庫規範 | 2026-08-28 21:19 |
| **FT-06** | `Passed` | 實機驗證 `P00` 與 `P07` 模板頂部 JIT 註解正確注入 `search` 與 `index` 指引 | 2026-08-28 21:19 |
| **ET-01** | `Passed` | 實機驗證未匹配之 Token 自動清理，不殘留佔位標籤 | 2026-08-28 21:19 |
| **RT-01** | `Passed` | 全生態系 4 大模組沙盒跑測 183/183 Passed (100% Ready, 17.045s) | 2026-08-28 21:19 |


---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01 (CLI 空間清單與產物排版體驗)**：
  - 實機執行 `python yscb.py knowledge-db status` 檢驗空間列表（包含 `docs` 與 `source` 空間）。
  - 實機檢視發布後的 `AGENTS.md` 與 `P07_walkthrough.md` 頂部 JIT 註解內容。

