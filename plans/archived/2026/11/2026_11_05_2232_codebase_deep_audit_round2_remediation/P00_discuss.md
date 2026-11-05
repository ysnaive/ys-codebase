# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全專案第二輪八維度深度審計與反向溯源收斂修復 (Codebase Deep Audit Round 2 Remediation)
> 建立日期：2026-11-05
> 所屬主計畫：N/A
> 狀態：Confirmed
> 模型：Unknown
> 計畫類型：Bug Fix
> 模板版本：v1.2

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對全專案執行第二輪 `/codebase-deep-auditor` 盲眼深度健康檢查，並透過盲眼子代理（Devil's Advocate 原型 ③）結合全倉 63 個單元測試檔案從候選問題反向溯源排查真實性，確認無誤後以 `/auto` 模式直接連續推進至 `P06` 驗證斷點。
- **核心目標**：
  1. 落實經雙階段盲眼審計與反向溯源證偽確認成立之 **24 項實質處方（`AUD-01 ~ AUD-24`：10 項 P1、9 項 P2、5 項 P3）**。
  2. 100% 遵守 Devil's Advocate 反向查驗攔截到的單元測試契約與架構邊界，確保全倉既有測試零退化並補齊邊界防護。
  3. 同步遵循 `CodeQualityStandards.md` §1.4「零工單與審計編號註解鐵律」，清理 `core`、`server` 與 `agents-workflow` 共 12 個檔案生產註解與 Docstring 中殘留的舊規格編號（同時嚴格保留 `test_core_commands.py` 斷言之 `(EC-02) ~ (EC-08)` 執行期錯誤訊息字串）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.platform.lock.InterProcessLock` 非阻塞探測與 POSIX `fstat`/`stat` Inode 比對機制。
  - 復用 `file_space.scanner._atomic_write_bytes` 之 Windows `PermissionError` 指數退避重試模式強化 `knowledge_db.service.write_worker_state`。
  - 復用 `knowledge_db.pipeline.IndexingPipeline._reset_consumer_cursor` 單點游標重置介面，避免 `engine.clean` 直接調用全域單例污染宿主環境。
  - 復用 `agents_workflow.plans.status.PlanStatusResolver.resolve_phase_file` 與 `_verifier_healer.auto_heal_companions` 統一階段解析與子計畫伴隨檔自癒。
- **邊界排除 (Explicitly Excluded)**：
  - **排除已通過零問題驗收之模組**：`Unit 01 (gdrive-support)` 與 `Unit 02 (vscode-support)` 於第二輪盲審中達成 `0 Issues Found (PASSED)`，本計畫不觸碰該兩模組。
  - **排除經反向溯源證偽之假陽性**：
    1. 排除原 `AUD-17`（`ast_engine/schema.py:L299-L307` `UnifiedSymbol.from_dict`，現行源碼實為 `members_list == children_list`，係為滿足 `test_ast_engine.py:L64` 之 `assertIs` 共享元組斷言）。
    2. 排除 `yscb.py:_is_modules_dirty` 對設定檔手寫 `"build"` 之豁免修改（刻意設計以觸發 `cmd_restore` 物化回寫具體版號）。
    3. 排除對 `core` 執行期異常訊息字串內 `(EC-02) ~ (EC-08)` 的刪改（屬 `test_core_commands.py` 外部測試契約）。
- **架構影響範圍**：`core`、`server`、`dev`、`agents-workflow`、`file-space`、`ast`、`knowledge-db` 七大模組共 40 個檔案。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `core` 跨平台鎖、Win32 ABI、重載快取、macOS 路徑與 VFS 防護（`AUD-01 ~ AUD-05`, `AUD-11 ~ AUD-12`）**：
  - `InterProcessLock.acquire` 在 POSIX 下取得 `flock` 後核對 `fstat(fd).st_ino == stat(lock_file).st_ino`；`AtomicEngine.act_lock` 於過期時先釋放本進程 `_active_locks` 再以 `probe.acquire(blocking=False)` 探測外部進程鎖，保留 `act_unlock` 刪除 `.yscb.lock` 以 100% 相容 `test_engine.py:L114-L129, L668`。
  - `process.py:can_spawn_background_daemon` 將 `IsProcessInJob` 輸出指標由 1-byte `c_bool` 修正為 4-byte `wintypes.BOOL`。
  - `dispatcher.py` 新增 `clear_cache()` 供 `engine.py:act_reload` 調用，並對 `_load_registry` 之 `os.listdir` 排序（`"core"` 優先）且對別名衝突輸出 `stderr` 警告而不崩潰。
  - `gitignore.py` 在 `normalize_pattern`、`_resolve_roots` 與 `_cleanup_obsolete_nested_gitignores` 統一以 `os.path.realpath` 正規化比對端點；`pip_manager.py:_bootstrap_pip` 防護 `getattr(ensurepip, "_WHEEL_PKG_DIR", None)` 為 `None` 的情況並探測 `_bundled` 與 `/usr/share/python-wheels`。
  - `venv.py:_is_source_tree_path` 支援自動解析 `yscb_root` 並僅針對工作區內相對路徑判斷 `source/`，消除上層目錄含 `/source/` 時誤濾 `.modules/*` 的問題；`os_backend.py:copy` 加入同源路徑相等守衛與子目錄遞迴攔截。
  - `semver.py:_match_single_clause` 限定三段式匹配僅在雙方無 `prerelease` 且無 `is_build` 時才忽略第 4 段；`engine.py:act_solve_deps` 支援雙範圍算符約束合併；`validator.py` 採用括號平衡 `_split_top_level_comma` 解析 `dict[K, V]` 並統一寫入快取；`contributes.get()` 對最終回傳子項執行 `deepcopy` 並對齊單檔 `contributes.json` 驗證與指令/語系收集。
- **[P00:DR-02] `dev`、`agents-workflow` 與 `server` 雙軌同步、編碼與競態修復（`AUD-06 ~ AUD-09`, `AUD-13 ~ AUD-16`, `AUD-20`）**：
  - `dev/testing/case.py:create_mock_source_module` 保留預設寫入 `tests/test_dummy.py`，將 `L261` 跳過清單收斂為 `("manifest.json", "scripts/cli.py")`。
  - `dev/tester.py:_run_test` 在 `cfg.is_all or not cfg.target_param` 時以 `TestDiscovery.discover_modules(None)` 補齊 `tested_mods`。
  - `agents_workflow/plans/verifier.py:verify_plan` 檢核 `sub_*` 子計畫時，對齊根計畫三步管線（先驗證 Markdown、在 `not sub_has_new_fails and enable_auto_heal and has_non_seed_md` 時呼叫 `_auto_heal_companions` 並補驗新建 `P06`、最後檢查結構與追溯性）。
  - `dev/releaser.py:_run_git_cmd` 與 `agents_workflow/plans/session_trace.py:_get_git_changed_files` 補齊 `encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL` 與 `timeout`。
  - `status.py:_resolve_p00_next_action` 改用 `cls.resolve_phase_file(p, "P00")`；`agents-workflow` 之 `contributes/core.json` 與 `scripts/cli.py` 補齊 `init` 的 `default` 與 `path-roadmap` 等選項；`sandbox.py:cleanup_sandbox` 將 `_ACTIVE_SANDBOXES.discard` 移至活躍沙盒守門之後並於守門比對時使用 `normcase`；`server/master.py` 以區域變數快照讀取 `_worker_proc.pid`；`server/watcher.py` 將 `_is_core_transaction_locked()` 移入快照差異分支內。
- **[P00:DR-03] `knowledge-db`、`file-space`、`ast` 與跨模組零工單註解合規（`AUD-10`, `AUD-17 ~ AUD-19`, `AUD-21 ~ AUD-24`）**：
  - `knowledge_db/service.py:write_worker_state` 為 `os.replace` 加上 5 次短指數退避重試（`0.005 * 2**attempt`）與異常暫存檔清理。
  - `knowledge_db/engine.py:clean` 統一委派 `self.pipeline._reset_consumer_cursor(space_name=None, consumer_id="knowledge-db")`，同步重置全空間游標且絕不污染宿主環境。
  - `knowledge_db/retrieval.py:_cs_type_key` 對齊 `s.language in ("c_sharp", "csharp") or bool((s.metadata or {}).get("is_partial"))`。
  - `file_space/service.py:notify_file_event` 以 O(1) 純字串比對處理 Windows 大小寫與 macOS `/private/` 軟連結前綴；`file_space/manager.py:file_belongs_to_space` 於單檔 `include` 命中時檢驗 `cfg.is_file_included(inc_root.name)`。
  - `ast_engine/linker.py:_compute_symbols_map_fingerprint` 改讀 `line_number`；`ast_engine/bundler.py` 移除零引用孤兒方法 `_parse_and_dedup_file`。
  - 清理 `core`、`server`、`agents-workflow` 共 12 個檔案註解與 Docstring 中的舊規格編號，並於 `resolver.py` 排除單一 `"-"` 誤判及於 `core/scripts/cli.py` 補齊 `_normalize_bags`。

---

## 3. 開放議題與確認紀錄

- 全數 24 項處方均已完成盲眼 Devil's Advocate 反向溯源核實，無開放議題，依使用者指示直接透過 `/auto` 推進至 `P06` 驗證斷點。
