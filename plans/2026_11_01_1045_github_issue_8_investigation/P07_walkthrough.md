# 成果展示與結案報告 (Walkthrough)

> 功能名稱：GitHub Issue #8 四大跨模組缺陷與架構完善修復 (server / knowledge-db / agents-workflow)  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`server` 狀態讀取修復與防孤兒鎖保護 (`FR-01`, `EC-01`)**：移除 `server/master.py:read_daemon_state(yscb_root)` 傳入 `vfs.read_json(state_file)` 的無效 `default=None` 參數，根治 `TypeError` 遭靜默吞沒導致 `server status` / `server stop` 永遠回報 `Stopped` 的問題；並於 `server/scripts/cli.py:stop()` 刪除失效 `daemon.json` 前增設非阻塞 `InterProcessLock(lock_file)` 探針，防止活體 Daemon 持有鎖時誤刪狀態檔形成孤兒程序。
  2. **跨執行模式自訂解析器動態載入與內建解析器副檔名擴充 (`FR-02`, `EC-03`, `NFR-01`)**：於 `server/master.py:_spawn_worker_locked`、`server/worker.py:WarmWorker.pre_warm` 及 `knowledge_db/parsers/registry.py:ParserRegistry` 注入 `project://`、`yscb.host://` 與 `module://<provider>` 至搜尋路徑（嚴格過濾 `/source` 路徑以恪守 `Zero Source Path Injection` 護欄），支援 `pkg.mod:Class`、相對檔案路徑與語意 URI `parser_entry`；並於 `_bind_configured_extensions` 將 `LanguageConfig.extensions` 動態合併為實例級 `SUPPORTED_EXTENSIONS` 新集合，使 `HtmlParser` 等內建解析器可直接透過 `contribute.json` 擴充 `.astro` 等副檔名而不污染類別共享屬性。
  3. **解析器載入異常顯式可觀測性與熱修復自癒 (`FR-03`, `EC-02`)**：於 `ParserRegistry` 新增 `self.load_errors` 記錄載入失敗之語言 ID 與錯誤原因，透過 `engine.status()["parser_load_errors"]` 暴露並於 `knowledge-db index` / `status` 向 `stderr` 輸出 `[WARN]` 告警，同時於 `get_engine()` 在 `load_errors` 非空時自動重試載入以支援熱修復。
  4. **`plan verify` 與 `plan status` 提示路徑動態對齊活躍 `release_targets` (`FR-04`, `EC-04`)**：於 `agents_workflow/plans/_common.py` 新增 `resolve_active_target_projected_path` 並接線至 `verifier.py` 與 `status.py`，當專案僅啟用 `claude` 等非預設 Target 時自動輸出 `.claude/.yscb/templates/...` 與 `.claude/skills/...`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/server/server/master.py` | Modify | 移除 `read_daemon_state` 無效 `default=None` 參數；於 `_spawn_worker_locked` 注入宿主與專案根目錄至 `PYTHONPATH`（過濾 `/source`） |
| `ys_codebase/source/server/server/worker.py` | Modify | 於 `WarmWorker.pre_warm` 將宿主與專案根目錄納入 `sys.path` |
| `ys_codebase/source/server/scripts/cli.py` | Modify | 於 `stop()` 清理 `daemon.json` 前非阻塞探測 `daemon.lock` |
| `ys_codebase/source/server/tests/test_server.py` | Modify | 新增 `test_daemon_state_roundtrip_and_stop_lock_protection` 單元與邊界測試 |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py` | Modify | 新增 `_ensure_search_paths`、`_instantiate_custom_parser`、`_bind_configured_extensions` 與 `load_errors` 診斷記錄 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 於 `status()` 暴露 `parser_load_errors` 並於 `get_engine()` 支援錯誤自癒重試 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 於 `status` 與 `index` 輸出 `parser_load_errors` 警告至 `stderr` |
| `ys_codebase/source/knowledge-db/tests/test_parsers.py` | Modify | 新增 `test_custom_parser_loading_extension_binding_and_error_diagnostics` 測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py` | Modify | 新增 `resolve_active_target_projected_path` 動態解析活躍 `release_targets` 投影路徑 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `_build_next_phase_hint` 改用動態模板投影路徑 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | `resolve_next_action` 與 `_resolve_research_next_action` 改用動態技能投影路徑 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 擴充驗證單一 `claude` Target 下之模板與技能動態路徑解析 |
| `docs/knowledge-db/contributes_guide.md` | Modify | 補充 `custom` 解析器三種 `parser_entry` 格式與實例級 `SUPPORTED_EXTENSIONS` 動態副檔名綁定說明 |
| `docs/knowledge-db/parsers.md` | Modify | 補充 `load_errors` 顯式診斷與熱修復自癒說明 |
| `docs/server/DESIGN_NOTES.md` | Modify | 更新 `[DN-07]` 記載宿主專案路徑注入、`read_daemon_state` 簽名契約與 `daemon.lock` 防誤刪邊界 |
| `CHANGELOG.md` | Modify | 登記 `2026_11_01_1045_github_issue_8_investigation` 結案發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`server` (`40/40`, 100%)、`knowledge-db` (`158/158`, 100%)、`agents-workflow` (`138/138`, 100%)；模組靜態合規檢查 `dev check` 3/3 全數 `PASSED`，且 Pre-UX 盲眼獨立審查 (`Reviewer Subagent`) 判定 `REVIEW_STATUS: PASSED`。
- **實機 UX / 人工驗證**：`UX-01` 依開發者指示標記為 `[跳過/免測]` 直接推進結案。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已交付 | 頂部新增 `2026_11_01_1045_github_issue_8_investigation` 結案條目 |
| **中觀 (Meso)** | `docs/knowledge-db/README.md` | 免更 | 高階架構拓撲不變 |
| **中觀 (Meso)** | `docs/knowledge-db/contributes_guide.md`, `docs/knowledge-db/parsers.md` | 已交付 | 同步更新自訂解析器路徑格式、動態副檔名綁定與 `load_errors` 診斷機制 |
| **中觀 (Meso)** | `docs/server/DESIGN_NOTES.md` | 已交付 | 更新 `[DN-07]` 記錄 `project://` 路徑注入與 `daemon.lock` 防孤兒鎖保護 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已交付 | `read_daemon_state`、`ParserRegistry` 與 `resolve_active_target_projected_path` Docstring 完整對齊 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(server,knowledge-db,agents-workflow): resolve GitHub Issue #8 daemon status, custom parser loading, and target path hints
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

