# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：GitHub Issue #8 四大跨模組缺陷與架構完善調研 (server / knowledge-db / agents-workflow)  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 GitHub Issue #8（`server 啟用時無法載入專案自訂解析器；server status 永遠回報 Stopped`，回報者：`coachnian`）先立項進行深度調研報告，剖析 4 項跨模組異常之根因、擴散半徑與架構修復候選方案。
- **核心目標**：
  1. **問題一 (`server`)**：釐清為何 `server status` 與 `server stop` 永遠偵測不到運作中的 Daemon（`read_daemon_state` 回傳 `None`），以及 `server stop` 為何在未確認鎖狀態下誤刪 `daemon.json` 留下孤兒程序。
  2. **問題二 (`server` / `knowledge-db` / `core`)**：釐清為何專案透過 `config/knowledge-db/contribute.json`（或第三方 YSCB 模組）註冊之 `custom` 解析器（如 `.astro`、`JsonParser`）在 Cold Run 可正常載入，但在 `server` Warm Worker 與 `ProcessPoolExecutor` 子進程下卻因 `sys.path` 差異或內建 Parser `can_parse` 硬編碼副檔名而載入失敗。
  3. **問題三 (`knowledge-db` / `server`)**：釐清為何自訂解析器載入失敗時，`server start --console` 或前景執行 `knowledge-db index` / `status` 的客戶端終端機完全無警告（僅靜默少掉符號）。
  4. **問題四 (`agents-workflow`)**：釐清為何專案僅啟用 `claude` 目標（移除 `antigravity`）時，`plan verify` 的 `[NEXT PHASE GATE]` 與 `plan status --resume` 的 `Required Reference` 仍硬編碼顯示 `.agents/...` 而非 `.claude/...`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `core.vfs` (`VFS.read_json`)、`core.uri` (`resolve("project://")`, `resolve("yscb.host://")`, `resolve("module://<donor>")`)。
  - `server.master` (`read_daemon_state`, `_spawn_worker_locked`)、`server.worker` (`WarmWorker.pre_warm`, `_prepare_execution_env`)、`server.service` (`ServiceManager._load_service_item` 之 `__provider__` 路徑注入模式)。
  - `knowledge_db.parsers.registry` (`ParserRegistry._load_from_contributes`)、`knowledge_db.parsers.{html_parser,css_parser,spice_parser}`。
  - `agents_workflow.targets` (`ReleaseTargetManager.get_classified_targets`)、`agents_workflow.compiler` (`ArtifactCompiler.get_release_targets`)。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段為純技術調研與架構方案評估（`Research Plan`），於開發者拍板流轉出口前，不直接修改 `ys_codebase/source/` 下任何業務程式碼。
  - 不破壞 `dispatcher.py` 既有的「嚴禁在運行時將 `ys_codebase/source/` 注入 `sys.path`」之剛性安全護欄（`test_worker_and_master_zero_source_path_injection`）。
- **架構影響範圍**：
  - `server`：`ys_codebase/source/server/server/master.py`、`ys_codebase/source/server/server/worker.py`、`ys_codebase/source/server/scripts/cli.py`
  - `knowledge-db`：`ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py`、`ys_codebase/source/knowledge-db/knowledge_db/parsers/{html_parser,css_parser,spice_parser}.py`、`ys_codebase/source/knowledge-db/knowledge_db/engine.py`、`ys_codebase/source/knowledge-db/scripts/cli.py`、`docs/knowledge-db/{contributes_guide,parsers}.md`
  - `agents-workflow`：`ys_codebase/source/agents-workflow/agents_workflow/plans/{verifier,status}.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `read_daemon_state` 異常根因與 `server stop` 孤兒進程防護方向**：
  - 根因確認：`2026_10_30_1641` (`sub_03`) 將 `read_daemon_state` 改為 `vfs.read_json(state_file, default=None)`，但 `VFS.read_json(self, path_or_uri, encoding="utf-8")` 並不接受 `default` 參數，每次呼叫必然拋出 `TypeError: VFS.read_json() got an unexpected keyword argument 'default'`，且被外層 `except Exception: pass` 靜默吞沒（違反核心原則 3 反模式 1），導致 `read_daemon_state()` 100% 回傳 `None`。
  - 連帶防護：移除 `default=None` 並縮小 `except (OSError, ValueError, TypeError)`（指 `ServerDaemonState(**data)` 缺欄位時的解構保護，而非吞掉 API 簽名錯誤），且在 `cli.py:stop()` 當 `read_daemon_state` 為 `None` 但 `daemon.lock` 仍被持有時，不應盲目刪除 `daemon.json`。
- **[P00:DR-02] 跨執行模式（Cold Run / Warm Worker / ProcessPool 子進程）自訂解析器載入與內建 Parser 副檔名動態綁定**：
  - 根因確認：
    1. **路徑落差**：Cold Run 執行 `python yscb.py` 時，Python 自動將 `yscb.py` 所在目錄（`yscb.host://` / 專案根目錄）置於 `sys.path[0]`；但 `master.py:_spawn_worker_locked` 啟動 `worker.py` 時，`cwd=self.yscb_root`（即 `ys_codebase/`），`PYTHONPATH` 僅含 `yscb_root`、`.modules`、`.modules/core`、`.modules/server`，缺少 `project://` 與 `yscb.host://`，且未像 `ServiceManager._load_service_item` 一樣將 `languages` 的 Donor 模組路徑（`module://<__provider__>`）加入 `sys.path`。
    2. **語意 URI 支援**：`parser_entry` 若支援 `project://path/to/file.py:ClassName`、`module://<mod>/...:ClassName` 及標準 `pkg.mod:ClassName`（自動確保 `project://`、`yscb.host://` 與 `module://<__provider__>` 在載入時可達），即可在 Cold Run、Warm Worker（含 `pre_warm` 階段）與 `ProcessPoolExecutor` 子進程中 100% 一致運作。
    3. **內建 Parser 副檔名擴充**：`HtmlParser`、`CssParser`、`SpiceParser` 的 `__init__` 未接收 `LanguageConfig`，`can_parse()` 僅檢查類別常數 `SUPPORTED_EXTENSIONS`，導致使用者在 `contribute.json` 為 `"html"` 加上 `".astro"` 或註冊新語言指向 `HtmlParser` 時無法生效。
- **[P00:DR-03] 解析器載入異常之顯式可觀測性 (Observability)**：
  - 根因確認：`ParserRegistry` 在 `WarmWorker.pre_warm()` 背景執行緒中初始化（此時尚未進入 CLI Task 的 `DebouncedIOStreamer` 捕獲區間），且後續 `index` / `search` 複用 `_GLOBAL_ENGINE_INSTANCE` 單例，不再重跑 `_load_from_contributes()`，因此客戶端終端機完全看不到 `logger.warning`。
  - 處置方向：於 `ParserRegistry` 持久化保存 `load_errors: Dict[str, str]`，在 `knowledge-db status` 與 `knowledge-db index` 執行時主動顯示解析器載入錯誤警告（含 `status --json` 結構化欄位），並於 `ParserRegistry` 載入失敗時輸出清晰診斷。
- **[P00:DR-04] `plan verify` 與 `plan status` 提示路徑動態對齊活躍 `release_targets`**：
  - 根因確認：`verifier.py:_build_next_phase_hint` (L752) 硬編碼 `.agents/.yscb/templates/{tmpl_name}`，`status.py:PlanStatusResolver.resolve_next_action` (L432, L504-505) 硬編碼 `.agents/skills/...`。
  - 處置方向：透過 `ReleaseTargetManager.get_classified_targets()["union"]` 與 `ArtifactCompiler.get_release_targets()` 動態解析當前啟用 Target 的 `projections.template.target_dir` 與 `projections.skill.target_dir`（多 Target 啟用時取首個活躍 Target 或並聯顯示，無活躍 Target 時 fallback 至 `.agents/...`）。

---

## 3. 開放議題與確認紀錄

- **Q1**：已依指示先行建立 `Research Plan` 並完成 `R01_github_issue_8_investigation.md` 深度調研報告，待開發者審閱報告後裁決後續流轉出口。

