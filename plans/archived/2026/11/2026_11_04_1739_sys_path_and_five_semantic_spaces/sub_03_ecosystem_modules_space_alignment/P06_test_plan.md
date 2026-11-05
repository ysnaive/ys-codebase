# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全生態系模組五大語意空間映射對齊與既有資產無損遷移 (Ecosystem Modules Five Semantic Spaces Alignment)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Medium)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元與整合測試 | 驗證 `gdrive-support` 預設 `credentials_uri` / `token_uri` 對齊 `config.local://`、`sync_state.json` / `readme_sync_state.json` 對齊 `storage.local://`、`sync.lock` / `sync.log` 留駐 `cache://`、`is_sensitive_credential_path` 攔截 `.config.local` 與 `.storage.local`，以及 `1.0.1.x.py` 版本晉升遷移 | FR-01, FR-04, EC-02, EC-03 | `python yscb.py dev test gdrive-support -q --sync` |
| **FT-02** | 單元與整合測試 | 驗證 `file-space`、`ast`、`knowledge-db` 預設儲存路徑對齊 `storage.local://`、`.ast_index.lock` 與 `.kdb_index.lock` 於預設模式下分離至 `cache://` 且於測試沙盒模式下隔離於沙盒內部、以及 `1.0.1.x.py` / `1.2.1.x.py` 遷移腳本 | FR-02, FR-04, EC-01, EC-02, NFR-02 | `python yscb.py dev test file-space -q --sync && python yscb.py dev test ast -q --sync && python yscb.py dev test knowledge-db -q --sync` |
| **FT-03** | 單元與整合測試 | 驗證 `agents-workflow` 三大持久清冊對齊 `storage.local://`、拔除 `_migrate_legacy_manifest` 執行期歷史分支、`1.2.4.x.py` 遷移腳本、`core` `DYNAMIC_CACHE_URI` 對齊 `storage.local://core/gitignore_dynamic.json` 與 `1.2.7.x.py` 遷移腳本 | FR-03, FR-04, EC-02, NFR-01 | `python yscb.py dev test core -q --sync && python yscb.py dev test agents-workflow -q --sync` |
| **FT-04** | 靜態合規與全域健康度驗證 | 驗證全倉 9 大模組 (`core`, `dev`, `server`, `vscode-support`, `file-space`, `ast`, `knowledge-db`, `agents-workflow`, `gdrive-support`) 100% 通過 `dev check`、`uri check`、`status` 與 `agents-workflow release` | FR-05, NFR-01, NFR-02 | `python yscb.py dev check <all> && python yscb.py uri check && python yscb.py status && python yscb.py agents-workflow release` |
| **FT-05** | 臨時兄弟目錄 (`/workspace/test_sibling_yscb`) 端到端升級、自癒遷移與 `tmpfs` 抹除實機測試 | 於隔離兄弟工作區植入舊版 9 模組與舊路徑資產 (`config/*/config.local.json`, `config/gdrive-support/credentials.json`, `.cache/gdrive-support/{token,sync_state,readme_sync_state}.json`, `.cache/core/gitignore_dynamic.json`, `.cache/file-space/snapshots/*`, `.cache/ast/indices/*`, `.cache/knowledge-db/models/*`, `.cache/agents-workflow/*.json`)，實機執行 `install *@build` 觸發 6 大版本晉升遷移腳本、驗證 CLI 讀寫與 `.cache/` (`tmpfs`) 全抹除後之持久資產存活率 | FR-01 ~ FR-05, EC-01 ~ EC-03, NFR-01, NFR-02 | `python scratch/verify_sibling_workspace.py` (20/20 斷言全數通過，測畢已清理 `/workspace/test_sibling_yscb`) |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `gdrive-support` 測試 27/27 (100.0%) Passed；同步安裝 `gdrive-support@1.0.1.build` 並自動執行 `1.0.1.x.py` 將母倉 `credentials.json`、`token.json`、`sync_state.json`、`readme_sync_state.json` 無損遷移至 `.config.local/` 與 `.storage.local/` | 2026-11-05 04:14 |
| **FT-02** | `Passed` | `file-space` 17/17、`ast` 26/26、`knowledge-db` 109/109 (100.0%) Passed；同步安裝 `@build` 並觸發 `1.0.1.x.py` / `1.2.1.x.py` 將 `snapshots/`、`cursors/`、`indices/`、`bundles/` 與 91MB `models/` 無損遷移至 `.storage.local/` | 2026-11-05 04:14 |
| **FT-03** | `Passed` | `core` 246/246、`agents-workflow` 142/142、`dev` 87/87、`server` 56/56、`vscode-support` 11/11 (100.0%) Passed；自動執行 `core` `1.2.7.x.py` 與 `agents-workflow` `1.2.4.x.py` 將 `config.local.json`、`gitignore_dynamic.json` 與發布清冊遷移至 `.config.local/` 與 `.storage.local/` | 2026-11-05 04:14 |
| **FT-04** | `Passed` | 全倉 9 模組 `dev check` 100% PASSED；`uri check` 全數 `[OK]` (`Overall URI Status: HEALTHY`)；`status` 顯示 9 模組 `Healthy (100% Ready)`；`knowledge-db status` 與 `ast status` 確認根目錄已切換至 `.storage.local/` | 2026-11-05 04:15 |
| **FT-05** | `Passed` | 於臨時兄弟目錄 `/workspace/test_sibling_yscb` 從舊版 (`core@1.2.6.0` 等) 升級至 9 模組 `@build`，20/20 項實機斷言全數通過（含 6 大遷移腳本搬移與舊檔清除、`credentials.json`/`token.json` `0o600` 權限與 `config.project.json` URI 改寫、`file-space scan` / `ast outline` / `knowledge-db index & search` / `agents-workflow release` 實機運行，以及清空 `.cache/*` 模擬容器 `tmpfs` 重啟後 `.config.local/` 與 `.storage.local/` 100% 完好且免重建索引直接檢索命中）；順帶修復 `core/engine.py` `act_solve_deps` 中安裝含相依性模組時對已安裝相容 `@build` 相依模組之保留邏輯 | 2026-11-05 04:31 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `python yscb.py uri check`、`python yscb.py status`、`python yscb.py knowledge-db status` 與 `python yscb.py gdrive status`，確認全生態系 9 大模組皆已對齊五大語意空間且本機既有憑證、模型與索引已完成無損遷移 | `[測試通過]` | 經臨時兄弟目錄端到端升級、遷移與 `tmpfs` 快取抹除存活測試驗證通過 |

