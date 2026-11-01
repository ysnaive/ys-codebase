# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：主流 AI 開發平台 release_target 矩陣擴充、同路徑並聯渲染告警與宣告式環境嗅探  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `contributes/agents-workflow.json` 中 8 大預設 `release_target`（`antigravity`, `claude`, `codex`, `cursor`, `copilot`, `windsurf`, `opencode`, `roo`）均被正確解析，且文檔與 Schema 契約 100% 合規 | FR-05, NFR-02 | `python yscb.py dev test agents-workflow -k test_ft_01 -q` |
| **FT-02** | 整合與邊界測試 | 驗證 5 大擴充 Target 投影拓撲、`copilot` 子目錄 `.github/copilot-instructions.md` 相對連結 `./skills/...` 基準對齊、`.gitignore` 排除保護、以及多 Target 共用實體路徑（`antigravity` + `codex` + `cursor`）之專有名詞與相對連結 `" / "` 並聯去重渲染、移除保護與 `[publisher:warning]` 本機 `config.local.json` 覆寫提示，且重複發布維持冪等 | FR-01, FR-02, FR-03, EC-01, EC-02, EC-03, EC-04, NFR-01 | `python yscb.py dev test agents-workflow -k test_ft_08 -q` |
| **FT-03** | 單元測試 | 驗證 `core/locale.py` 宣告式環境變數嗅探規則表 `DEFAULT_HOST_DIALECT_RULES` 與自訂規則注入能精準識別 8 大 AI IDE / CLI 宿主環境變數 | FR-04 | `python yscb.py dev test core -k test_sub02_unqualified_global_lookup_and_host_dialect_sniffing -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `contributes check` (15 files PASS) 與 `test_targets.py:test_ft_01` 通過，8 大預設 Target 100% 註冊無誤 | 2026-11-01 |
| **FT-02** | `Passed` | `test_targets.py:test_ft_08` 通過：`.github/copilot-instructions.md` 連結為 `./skills/development-sop/SKILL.md`；`antigravity+codex+cursor` 並聯輸出雙路徑與雙專有名詞，並輸出 `[publisher:warning]` | 2026-11-01 |
| **FT-03** | `Passed` | `test_locale.py:test_sub02_unqualified_global_lookup_and_host_dialect_sniffing` 通過，8 大平台宣告式嗅探與自訂 `rules` 注入全數綠燈 | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py agents-workflow release-target --list`，確認終端機完整列出 `antigravity`、`claude`、`codex`、`cursor`、`copilot`、`windsurf`、`opencode`、`roo` 共 8 大預設 Target 及狀態標記 | `[測試通過]` | 開發者實機試調用確認通過 (2026-11-01) |

