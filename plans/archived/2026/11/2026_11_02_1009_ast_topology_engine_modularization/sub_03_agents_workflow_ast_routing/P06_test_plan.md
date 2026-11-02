# 測試計畫與驗證報告 (`P06_test_plan.md`) — `agents-workflow` 與 `knowledge-db-search` 技能對齊 `yscb ast` 路由與文檔更新 (`sub_03`)

> 功能名稱：agents-workflow 與 knowledge-db-search 技能對齊 yscb ast 路由與文檔更新
> 建立日期：2026-11-02
> 所屬主計畫：2026_11_02_1009_ast_topology_engine_modularization
> 狀態：Passed
> 模型：Gemini 4 Argon (Low)

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 合規與結構檢查 | 驗證 `ast`、`knowledge-db` 與 `agents-workflow` 模組之 `manifest.json`、`contributes/agents-workflow.json`、三點式 `usage_guide.md` / `config_guide.md` 與 Stage 1 / Stage 2 編譯零警告 | `FR-01`, `FR-02`, `NFR-01`, `NFR-02` | `python yscb.py dev check ast`、`python yscb.py dev check knowledge-db`、`python yscb.py dev check agents-workflow` 與 `test_ft_10_sub04_onboarding_and_config_coaching_skills` |
| **FT-02** | 單元與邊界測試 | 驗證 `_trace_parser.py` 對 `yscb.py ast outline/callers/callees/impact` 自動歸零 `consecutive_source_reads` 並啟用 $\le 160$ 行區段讀取盲讀豁免（`unindexed_blind_reads == 0`） | `FR-03`, `EC-01` | `TestPlansModelRecord.test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **ET-01** | 二層物化同步與契約檢核 | 驗證 `contributes check`、`agents-workflow compile` 與 `agents-workflow release` 將 `.agents/skills/knowledge-db-search/SKILL.md`（44 行，$\le 65$ 行）、`.agents/skills/knowledge-db-search/references/registered-spaces.md` 與 `AGENTS.md` 100% 同步物化，`yscb:ignore` 維護註記已自動剝除且無未閉合標籤 | `FR-04`, `EC-02`, `NFR-01` | `python yscb.py contributes check && python yscb.py agents-workflow compile && python yscb.py agents-workflow release` |
| **RT-01** | 全量回歸測試 | 驗證 `agents-workflow` 全量 141 項測試（含 3 項自動契約與 138 項自訂單元/環境測試）100% 通過零回歸 | `NFR-02` | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :--- |
| **FT-01** | `Passed` | `dev check` 於 `ast`、`knowledge-db`、`agents-workflow` 全數 `[PASS]`；`test_ft_10` 驗證 5 大模組 (`core`, `dev`, `server`, `ast`, `knowledge-db`) 之導覽與組態指南 100% 合規 | 2026-11-02 20:32 |
| **FT-02** | `Passed` | `test_ft_15` 新增 `rev06_ast_funnel.jsonl` 驗證執行 `python yscb.py ast outline Window.cs --public --methods --json` 後連讀 5 個 $\le 160$ 行分部檔案區段，`unindexed_blind_reads == 0` | 2026-11-02 20:32 |
| **ET-01** | `Passed` | `contributes check` (22 files `[PASS]`)、`agents-workflow compile` (71 cached, 22 inserts, 25 tokens) 與 `release` (72 published) 0 Warning 完成；`.agents/skills/knowledge-db-search/SKILL.md` (44 LOC)、`references/registered-spaces.md` 與 `AGENTS.md` 完成同步，且 `yscb:ignore` 註記已剝除 | 2026-11-02 20:47 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow`：`141 Total, 141 Passed, 0 Failed, 0 Skipped (13.325s)` | 2026-11-02 20:32 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視已物化之 `.agents/skills/knowledge-db-search/SKILL.md`、`.agents/skills/knowledge-db-search/references/registered-spaces.md`、`.agents/skills/how-to-yscb/SKILL.md` 與 `AGENTS.md`，並經 `/blind-subagent` A/B 基準測試、三路盲眼探索與全技能零 `--json` 暴力搜索確認三階段漏斗檢索、空間清單按需下沉與 `yscb:ignore` 註記剝除已完整生效 | `[測試通過]` | 開發者確認驗收通過 |

