# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (High)  

> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `testing-sop/SKILL.md` 存在、Frontmatter 具備環境型三段式結構、內建六大測試鐵律與 `__@{TESTING_SOP_STANDARDS}__` 錨點 | `FR-01` | `python yscb.py dev test agents-workflow -k model_record` |
| **FT-02** | 單元測試 | 驗證 `testing-sop/references/test_suite_audit_and_purification.md` 存在，完整定義 `T-01`~`T-06` 六大病灶與三步純化工作流 | `FR-02` | `python yscb.py dev test agents-workflow -k model_record` |
| **FT-03** | 單元測試 | 驗證 `AgentsStandards.md` §2 路由表包含 `testing-sop`，且 `phase_04_plan.md`、`phase_05_task.md`、`phase_06_test.md` 及 `plan_modes.md` 均包含 `testing-sop` 強制引用連結與雙重守門檢核 | `FR-03` | 檔案靜態比對與 `contributes check` |
| **FT-04** | 單元測試 | 驗證 `research/SKILL.md` 與 `discuss/SKILL.md` 內化支柱一唯讀廣域探索委派指引、檔案路徑傳址與 150~300 Tokens 摘要格式 | `FR-04` | 檔案規範結構檢核 |
| **FT-05** | 單元測試 | 驗證 `auto/SKILL.md`、`phase_05_task.md` 與 `phase_06_test.md` 內化支柱二門檻判定（$\ge 3$ 個任務組）、強制序列派發、二振失敗熔斷與 Single-Writer 鐵律 | `FR-05` | 檔案規範結構檢核 |
| **FT-06** | 單元測試 | 驗證 `phase_07_walkthrough.md` 內化支柱三 Fresh-Eyes Review、Untracked 新檔防護、三類硬性契約與三步結案時序 | `FR-06` | 檔案規範結構檢核 |
| **FT-07** | 單元測試 | 驗證 `RoadmapManager.promote_roadmap` 對同目錄已存在 `roadmap.md` 之目標目錄執行遷入時，能無損追加合併內容並移除原路線圖 | `FR-07` | `python yscb.py dev test agents-workflow -k test_roadmap` |
| **ET-01** | 邊界測試 | 驗證無 Subagent 工具支援之環境下的降級規範說明（Graceful Fallback） | `EC-01` | 檔案規範結構檢核 |
| **ET-02** | 邊界測試 | 驗證支柱二連續 2 次測試失敗之處理規範（二振熔斷回傳 `STATUS: MAJOR_BLOCKER`） | `EC-02` | 檔案規範結構檢核 |
| **ET-03** | 邊界測試 | 驗證支柱三 Reviewer Subagent 對待未加入 git index 之 `Untracked (??)` 新建檔案審查防護 | `EC-03` | 檔案規範結構檢核 |
| **ET-04** | 邊界測試 | 驗證支柱三 Reviewer Subagent 面對主觀風格與排版微調之防吹毛求疵邊界 | `EC-04` | 檔案規範結構檢核 |
| **ET-05** | 邊界測試 | 實機測試 `RoadmapManager.promote_roadmap()` 當目標目錄已存在 `roadmap.md` 時之追加合併防護 | `EC-05` | `python yscb.py dev test agents-workflow -k test_roadmap` |
| **PT-01** | 效能測試 | 驗證 `testing-sop/SKILL.md` 主檔小於 120 行，且 Subagent 傳址委派與結構化回傳小於 300 Tokens | `NFR-01` | 行數統計 (58 行 $\le 120$) 與 Token 經濟性檢視 |
| **RT-01** | 回歸測試 | 執行全套單元測試套件確保既有與新增測試 100% 通過 | `NFR-02` | `python yscb.py dev test agents-workflow -q` |
| **RT-02** | 回歸測試 | 執行 `contributes check`、`compile` 與 `plan verify --all` 確保全域合規 | `NFR-02` | `python yscb.py contributes check && python yscb.py agents-workflow compile && python yscb.py agents-workflow plan verify --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `testing-sop/SKILL.md` (58 行) 通過三段式 description 與 Gotchas 檢驗 | 2026-10-24 06:01 |
| **FT-02** | `Passed` | `references/test_suite_audit_and_purification.md` 完整包含 T-01~06 六大病灶與三步純化流程 | 2026-10-24 06:01 |
| **FT-03** | `Passed` | `AgentsStandards.md` §2、`phase_04`、`phase_05`、`phase_06`、`plan_modes.md` 成功植入連鎖觸發 | 2026-10-24 06:01 |
| **FT-04** | `Passed` | `research/SKILL.md`、`discuss/SKILL.md` 成功內化 Pillar 1 唯讀探索隔離與 150~300 Tokens 摘要約定 | 2026-10-24 06:01 |
| **FT-05** | `Passed` | `auto/SKILL.md`、`phase_05_task.md`、`phase_06_test.md` 成功內化 Pillar 2 門檻判定、序列實作、二振熔斷與 Single-Writer | 2026-10-24 06:01 |
| **FT-06** | `Passed` | `phase_07_walkthrough.md` 成功內化 Pillar 3 唯讀 Fresh-Eyes Review、Untracked 新檔防護與三類硬性契約 | 2026-10-24 06:01 |
| **FT-07** | `Passed` | `test_promote_roadmap_append_when_already_exists` 實機驗證多路線圖合流追加合併成功 | 2026-10-24 06:02 |
| **ET-01** | `Passed` | 三支柱手冊中均載明「無子代理環境自動降級為由主視窗內聯執行」 | 2026-10-24 06:02 |
| **ET-02** | `Passed` | 支柱二載明內部測試連續 2 次修復失敗立即停手回傳 `STATUS: MAJOR_BLOCKER` 轉入 `/discuss` | 2026-10-24 06:02 |
| **ET-03** | `Passed` | 支柱三載明 Reviewer 結合 `P04` 清單與 `git status --short` 直讀未追蹤新檔 | 2026-10-24 06:02 |
| **ET-04** | `Passed` | 支柱三載明僅查核三類硬性契約，無缺失強制直接回傳 `REVIEW_STATUS: PASSED` | 2026-10-24 06:02 |
| **ET-05** | `Passed` | 實機測試 `test_promote_roadmap_append_when_already_exists` 通過，目標 roadmap.md 成功追加兩份路線圖且原檔已移除 | 2026-10-24 06:02 |
| **PT-01** | `Passed` | `testing-sop/SKILL.md` 全文共 58 行 ($\le 120$ 行)，Subagent 回傳結構化約定為 150~300 Tokens | 2026-10-24 06:03 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow -q`: 131 Passed (100.0%), 0 Fail (含 `test_ft_09_sub03_testing_sop_and_three_pillar_subagent_delegation` 反向延伸斷言) | 2026-10-24 06:22 |
| **RT-02** | `Passed` | `contributes check` (12 definition files valid), `compile` (52 cached, 10 inserts, 18 tokens), `release` (53 published) 通過 | 2026-10-24 06:22 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視編譯發布後之 `.agents/skills/testing-sop/SKILL.md` 與各 SOP 手冊，確認錨點替換正常、格式優雅易讀 | `[跳過/免測]` | 開發者明確指示免測 |

