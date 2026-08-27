<!--

Phase 6 執行指引：
1. 目標：實機執行自動化測試、記錄真實日誌 (Execution Log)、完成 UX/人工驗證，確認實作品質 100% 達標。
2. Test-First 前置定稿回溯：測試項目已於 Phase 2 初始化、Phase 4 剛性定稿，本階段嚴禁憑空新增未定義測試。
3. 無 Log 即未驗證鐵律：若 CLI 測試受阻，嚴禁標記 Passed；必須標記 [未實機編譯/僅靜態檢查] 並呈遞精確指令請開發者於控制台執行回填。
4. UX / 手動測試 Checkpoint 強制等待關卡：CLI 自動化測試 100% 通過後，嚴禁自行推進至 Phase 7！必須呈遞測試結果並明確詢問開發者進行 UX 驗證，等待明確回覆「UX 驗證通過/指示免測」後方可將 P06 標記為 Passed。
5. 衍生問題處理：測試中若發現非本次範疇之缺陷，開立 sub_XX 衍生型子計畫（預設 Fast Track）。

-->

# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Completed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ReleaseTargetManager.list_targets()` 包含 `claude` 與 `codex` 且具備正確描述與初始狀態 | FR-01, FR-02, FR-04 | `test_targets.py:test_list_targets_includes_claude_and_codex` |
| **FT-02** | 單元測試 | 驗證啟用 `claude` target 發布時，工作流正確物化至 `.claude/commands/`、模板與標準正確輸出至 `.claude/.yscb/` 且包含 Frontmatter | FR-01, FR-03, EC-01 | `test_targets.py:test_publish_claude_target` |
| **FT-03** | 單元測試 | 驗證啟用 `codex` target 發布時，工作流正確物化至 `.codex/workflows/`、模板與標準正確輸出至 `.codex/.yscb/` 且包含 Frontmatter | FR-02, FR-03, EC-01 | `test_targets.py:test_publish_codex_target` |
| **FT-04** | 回歸測試 | 驗證全系統 `agents-workflow` 模組所有測試在虛擬沙盒中 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestReleaseTargets.test_ft_01_manifest_targets_discovery` & `test_ft_02_list_targets_output` 通過，確認包含 `claude` 與 `codex` | 2026-08-27 21:57 |
| **FT-02** | `Passed` | `TestReleaseTargets.test_ft_03_claude_projections_and_materialization` 通過，`.claude/commands` 投影路徑解析正確 | 2026-08-27 21:57 |
| **FT-03** | `Passed` | `TestReleaseTargets.test_ft_04_codex_projections_and_materialization` 通過，`.codex/workflows` 投影路徑解析正確 | 2026-08-27 21:57 |
| **FT-04** | `Passed` | `python yscb.py dev test agents-workflow` 沙盒全量跑測：23 Total, 23 Passed, 0 Failed (1.878s, 100% Ready) | 2026-08-27 21:57 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：執行 `python yscb.py agents-workflow release-target list` 檢查控制台正確列出 `antigravity` [ENABLED]、`claude` [DISABLED]、`codex` [DISABLED] 三大可用目標。
