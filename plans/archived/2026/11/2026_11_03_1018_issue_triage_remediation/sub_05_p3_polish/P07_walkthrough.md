# 成果展示與結案報告 (Walkthrough)

> 功能名稱：P3 效能與穩健性細節打磨 (sub_05_p3_polish)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **宿主與 `core` 穩健性及熱路徑打磨 (`FR-01` ~ `FR-03`, `EC-01`)**：
     - **`DEV-01` 熱派發已接收後不降級冷派發**：於 `core/commands/dispatcher.py:_try_hot_dispatch` 檢查 `res.accepted`，僅在 `not res.accepted`（daemon 離線或握手前拒絕）時回傳 `None` 降級冷派發；一旦 `res.accepted == True`（請求已被 Worker 接收執行）後發生逾時或中斷，直接回傳非零退出碼（`1`），杜絕具副作用之指令被重複執行。
     - **SemVer 預發布排序與原子覆寫清理 (`T-22`, `T-23`)**：統一 `yscb.py` 與 `core/engine.py` 之 `_parse_simple_semver` 為與 `core/semver.py` 一致之 `(major, minor, patch, build, is_release, prerelease)` 6 元組，確保預發布版排在同版號正式版之前且不將 `"1.0.0-rc1"` 誤解析為 `"1.0.1"`；移除 `_write_json_lf` 在 `os.replace` 前冗餘之 `os.remove`。
     - **URI 詞元快取、VFS 根路徑快取、遙測尾端讀取與檔案鎖錯誤區分 (`T-30`, `T-36`, `T-37`, `T-40`)**：於 `core/uri.py` 新增 `_TOKEN_MAP_CACHE` 與 100ms 單調時鐘髒檢查視窗（並於 `core/contributes.py:get()` 補上 `_URI_REENTRANCY` 守門避免重入雙重掃描）；於 `OSBackend.__init__` 預計算 `self._real_root_dir`；將 `core/telemetry.py` 之 `_rotate_telemetry_file` 與 `read_telemetry_records` 改為 `os.SEEK_END` 64KB 尾端反向分塊讀取；於 `InterProcessLock._try_lock_fd` 針對 `ENOTSUP`/`EOPNOTSUPP`/`ENOSYS`/`EBADF` 直接拋出 `OSError` 而非誤判為鎖競爭。
  2. **`server` 與 `dev` 效能及併發細節打磨 (`FR-04`, `EC-05`)**：
     - **虛擬環境路徑複用、計數器鎖保護與 4KB 雙水位防抖串流 (`T-24`, `T-25`, `T-39`)**：於 `core/platform/venv.py` 新增共用 `get_venv_site_packages(venv_dir)` 並由 `server/master.py` 呼叫；將 `self._tasks_executed += 1` 移入 `with self._worker_lock:` 保護區；於 `server/streamer.py:DebouncedIOStreamer` 新增 `max_buffer_bytes: int = 4096`，取消每次 `\n` 立即 flush，改為累積達 `4096` bytes、滿 `500ms` 防抖計時器或任務結束時批次刷出。
     - **`Checker` 單次模組檢查 AST 快取 (`T-31`)**：於 `dev/checker.py:Checker.check_module` 建立生命週期內之 `self._parsed_py_cache`，使 `_check_ast_compliance`、`_check_package_dunder_version` 與 `_scan_undeclared_contributes_reads` 共享單次 `ast.parse` 結果。
  3. **`ast`、`knowledge-db` 與 `agents-workflow` 結構及演算法優化 (`FR-05`, `FR-06`, `EC-02` ~ `EC-04`, `NFR-01`, `NFR-02`)**：
     - **`UnifiedSymbol.from_dict` 輕量反序列化、BFS 拓撲連結與預排序 (`T-28`, `T-29`, `T-35`)**：將 `ast_engine/schema.py:UnifiedSymbol.from_dict` 之 `children` 與 `members` 反序列化為 `Tuple[MemberInfo, ...]`（支援 `.line`、`.fqn`、`.parent_id`、`.return_type`、`.parameters` 屬性並保持 `to_dict()` 相容），消除載入快照時雙重建立 `UnifiedSymbol` 的記憶體與耗時開銷；於 `ast_engine/linker.py` 改用 `collections.deque` 執行 BFS 並預建 `_class_bases`/`_base_derived`/`_methods_by_class_and_short` 索引；於 `treesitter.py` 與 `python_ast.py` 迴圈外預先按跨度 `s.end_line - s.line_number` 排序 `target_symbols`。
     - **BM25 計分前預過濾與 `SnippetExtractor` 帶 `mtime_ns` 檔案行快取 (`T-33`, `T-34`)**：於 `BM25Engine._score_candidate_documents` 在計分前先執行 `ftype`、`category` 與 `exclude_set` 過濾；於 `SnippetExtractor` 新增以 `(str(real_path), st_mtime_ns)` 為鍵之 `_file_lines_cache`（上限 256 檔，檔案修改後 `st_mtime_ns` 改變即自動失效）。
     - **工作流編譯/發布快取與預編譯佔位符 Regex (`T-32`, `T-38`)**：於 `agents_workflow/compiler.py` 以 `@lru_cache` 快取標記/錨點 Regex 並支援 `stage1_cache` 注入快取、於 `publisher.py` 傳入 `precomputed_fingerprint` 免除重複計算；於 `plans/verifier.py:PlanVerifier` 將佔位符 Regex 預編譯為類別常數 `_PLACEHOLDER_PATTERNS` 並外提 `re.sub`。
     - **路線圖登錄 (`T-27`)**：已於 `plans/roadmap/doc_and_plan_archive_governance.md` 登錄 `T-27 (Y-17)` 並明確標記為 `尚未完整調研`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | `T-22` 預發布 SemVer 排序 6 元組、`T-23` 移除 `os.replace` 前冗餘 `os.remove` |
| `ys_codebase/source/core/core/engine.py` | Modify | `T-22` 預發布 SemVer 排序、`T-23` 移除 `os.replace` 前冗餘 `os.remove` |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `DEV-01` `_try_hot_dispatch` 僅在 `not res.accepted` 時回傳 `None` 降級冷派發 |
| `ys_codebase/source/core/core/uri.py` | Modify | `T-30` `_TOKEN_MAP_CACHE` 與 100ms 單調時鐘髒檢查視窗 |
| `ys_codebase/source/core/core/contributes.py` | Modify | `T-30` `get()` 讀取快取時補上 `_URI_REENTRANCY` 保護防止重入雙重掃描 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | `T-36` `OSBackend.__init__` 預計算 `self._real_root_dir` |
| `ys_codebase/source/core/core/telemetry.py` | Modify | `T-37` `os.SEEK_END` 64KB 尾端反向分塊讀取 |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | `T-40` `_try_lock_fd` 針對 `ENOTSUP`/`ENOSYS`/`EBADF` 直接拋出 `OSError` |
| `ys_codebase/source/core/core/platform/venv.py` | Modify | `T-24` 新增 `get_venv_site_packages` 共用輔助函式 |
| `ys_codebase/source/core/core/platform/__init__.py` | Modify | `T-24` 匯出 `get_venv_site_packages` |
| `ys_codebase/source/server/server/master.py` | Modify | `T-24` 複用 `get_venv_site_packages`、`T-25` `_tasks_executed += 1` 納入 `_worker_lock` |
| `ys_codebase/source/server/server/streamer.py` | Modify | `T-39` `DebouncedIOStreamer` `max_buffer_bytes=4096` 雙水位防抖緩衝 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `T-31` `check_module` 單次生命週期內共享 `self._parsed_py_cache` |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | `T-28` `UnifiedSymbol.from_dict` 反序列化 `children`/`members` 為 `Tuple[MemberInfo, ...]` |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | `T-29` `collections.deque` BFS 與預建繼承映射 `_class_bases`/`_base_derived`/`_methods_by_class_and_short` |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | `T-35` 迴圈外預先按跨度 `s.end_line - s.line_number` 排序 `target_symbols` |
| `ys_codebase/source/ast/ast_engine/parsers/python_ast.py` | Modify | `T-35` 迴圈外預先按跨度 `s.end_line - s.line_number` 排序 `target_symbols` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `T-33` `BM25Engine` 計分前預過濾、`T-34` `SnippetExtractor` 帶 `mtime_ns` 鍵之檔案行快取 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `T-32` `@lru_cache` 標記/錨點 Regex 與 `stage1_cache` 注入快取 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | `T-32` 傳入 `precomputed_fingerprint` 消除重複指紋計算 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `T-38` 預編譯 `_PLACEHOLDER_PATTERNS` 常數並外提 `re.sub` |
| `ys_codebase/source/core/tests/test_cli_router.py` | Modify | 新增 `DEV-01` 單元測試 |
| `ys_codebase/source/core/tests/test_platform_primitives.py` | Modify | 新增 `T-22`、`T-37`、`T-40` 單元測試 |
| `ys_codebase/source/server/tests/test_server_lifecycle.py` | Modify | 新增 `T-39` `max_buffer_bytes` 單元測試 |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 新增 `T-28`、`T-29`、`T-35` 單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval_pipeline.py` | Modify | 新增 `T-33`、`T-34` 單元測試 |
| `plans/roadmap/doc_and_plan_archive_governance.md` | New | `T-27 (Y-17)` 登錄至 `/roadmap` 並標記為 `尚未完整調研` |
| `docs/server/daemon_architecture.md` | Modify | 同步更新 §2 `max_buffer_bytes=4096` 雙水位防抖串流協議與 §6 送達判準 |
| `docs/server/DESIGN_NOTES.md` | Modify | 同步更新 `[DN-11]` 熱派發於請求已送達 (`accepted=True`) 後絕不重試亦不降級冷派發 |
| `CHANGELOG.md` | Modify | 新增 `sub_05_p3_polish (Completed)` 並將主計畫 `2026_11_03_1018_issue_triage_remediation` 標記為 `Completed` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check --all`：`7 Total, 7 Passed, 0 Warnings, 0 Failed`
  - `core`：`246/246` 通過（100%）
  - `server`：`54/54` 通過（100%）
  - `dev`：`86/86` 通過（100%）
  - `ast`：`25/25` 通過（100%）
  - `knowledge-db`：`108/108` 通過（100%）
  - `agents-workflow`：`141/141` 通過（100%）
- **實機 UX / 人工驗證**：
  - Pre-UX Blind Reviewer (`f9792af7-f3ca-4543-bd97-4ff569dfd239`)：`REVIEW_STATUS: PASSED`。
  - 於臨時兄弟目錄 `/workspace/yscb-uat-sub05` 完成 `UAT-1` ~ `UAT-5` 端到端實測並清除臨時目錄，開發者確認 `通過` (`UX-01`)。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 新增 `sub_05_p3_polish (Completed)` 並將 `2026_11_03_1018_issue_triage_remediation` 更新為 `Completed` |
| **中觀 (Meso)** | `docs/server/README.md` | 免更 | 公開 CLI 與模組介面未變更 |
| **中觀 (Meso)** | `docs/server/daemon_architecture.md` | 已更新 | 更新 §2 `max_buffer_bytes=4096` + `500ms` 雙水位防抖串流協議與 §6 `accepted=true` 不降級冷派發 |
| **中觀 (Meso)** | `docs/server/DESIGN_NOTES.md` | 已更新 | 更新 `[DN-11]` 涵蓋非嚴格模式 `_try_hot_dispatch` 於 `accepted=True` 後不退回冷派發 (`DEV-01`) |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | 嚴格維護 `UnifiedSymbol.from_dict`、`MemberInfo`、`DebouncedIOStreamer`、`get_venv_site_packages`、`_try_hot_dispatch` Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
perf(all): complete sub_05 P3 polish, DEV-01 hot dispatch guard, and close issue triage umbrella

- core/yscb: guard _try_hot_dispatch against cold fallback once accepted=True (DEV-01), align prerelease semver tuple ordering (T-22), remove redundant os.remove before os.replace (T-23), add 100ms token map cache with reentrancy guard (T-30), cache OSBackend._real_root_dir (T-36), use 64KB tail reverse chunking in telemetry (T-37), and raise OSError on unsupported lock errno (T-40)
- server/dev: share get_venv_site_packages (T-24), guard _tasks_executed under _worker_lock (T-25), buffer DebouncedIOStreamer up to max_buffer_bytes=4096 (T-39), and cache parsed AST per check_module (T-31)
- ast/knowledge-db/agents-workflow: deserialize children/members as MemberInfo tuples in UnifiedSymbol.from_dict (T-28), optimize TopologyLinker with deque BFS and inheritance maps (T-29), pre-sort call site target symbols (T-35), pre-filter BM25 candidates (T-33), cache SnippetExtractor file lines by mtime_ns (T-34), and cache regex/stage1 compilation and fingerprint in agents-workflow (T-32, T-38)
- docs/plans: log T-27 in plans/roadmap/doc_and_plan_archive_governance.md, update server docs and CHANGELOG.md, and complete 2026_11_03_1018_issue_triage_remediation
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
