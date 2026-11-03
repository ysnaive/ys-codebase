# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：P3 效能與穩健性細節打磨 (sub_05_p3_polish)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature / Polish & Optimization  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 [R01_issue_triage.md](../R01_issue_triage.md) 與 [umbrella_overview.md](../umbrella_overview.md) §2，推進最後一個子計畫 `sub_05_p3_polish`，完成 `T-22` ~ `T-40`（其中 `T-27` 轉入 `/roadmap` 並標記為尚未完整調研，`T-36` 一併順手修補）以及 `sub_01` 移交之 `DEV-01`。
- **核心目標**：
  1. **`yscb.py` 與 `core` 基礎設施打磨 (`T-22`, `T-23`, `T-30`, `T-36`, `T-37`, `T-40`, `DEV-01`)**：
     - **`T-22 (Y-11)`**：強化 `yscb.py:_parse_simple_semver` 與 `core/engine.py` 版本解析比較，支援預發布標籤（如 `-alpha`, `-beta`, `-rc1`）排在同版號正式版之前，避免直接剝除非數字字元導致 `"0-rc1"` 變成 `1` 排錯序。
     - **`T-23 (Y-12)`**：移除 `yscb.py:_write_json_lf` 在 `os.replace(tmp_path, path)` 前多餘的 `os.remove(path)`，消除非原子空窗。
     - **`T-30 (PERF-09)`**：於 `core/uri.py:_build_scheme_token_map` 快取已合併之 `token_map` 並加上 `100ms` 單調時鐘視窗（綁定 `contributes.meta.json` / `contribute.json` 狀態與重入守衛），消除單次指令內數百次 `uri.resolve()` 重複 `stat` 與字典淺拷貝。
     - **`T-36 (PERF-16)`**：於 `core/vfs/os_backend.py:OSBackend.__init__` 預先計算並快取 `self._real_root_dir`，使 `assert_safe_path` 在 `root is None` 時直接複用並簡化布林返回。
     - **`T-37 (PERF-17)`**：於 `core/telemetry.py:_rotate_telemetry_file` 與 `read_telemetry_records`（當 `cutoff_epoch is None` 且指定 `limit > 0` 時）優先由尾端切片或 `collections.deque` 擷取候選行再執行 `json.loads`。
     - **`T-40 (EX-3)`**：於 `core/platform/lock.py:_try_lock_fd` 區分鎖競爭（`EACCES`, `EAGAIN`, `EWOULDBLOCK`）與檔案系統不支援檔案鎖（`ENOTSUP`, `EOPNOTSUPP`, `ENOSYS`, `EINVAL`）或其他 `OSError`，不支援鎖時拋出或回報明確異常而非誤判為「已被鎖定」。
     - **`DEV-01`**：於 `core/commands/dispatcher.py:_try_hot_dispatch` 對齊安全語意：僅在「請求尚未被 Worker 接收（`accepted=False`）」時回傳 `None` 降級至本地冷派發；若請求已被 Worker 接收並開始執行（`accepted=True`）卻因逾時或中斷失敗，直接回傳非零退出碼 `res.exit_code`，杜絕同一指令被重複執行第二次。
  2. **`server` 與 `dev` 穩健性與檢核快取打磨 (`T-24`, `T-25`, `T-26`, `T-31`, `T-39`)**：
     - **`T-24 (Y-13)`**：於 `server/master.py` 改用 `core.platform.venv.get_venv_site_packages` 取代重複手寫的 site-packages 路徑探測邏輯。
     - **`T-25 (Y-14)`**：於 `server/master.py` 將 `self._tasks_executed += 1` 移入鎖保護區段內遞增。
     - **`T-26 (Y-16)`**：於 `server/tests/test_server.py` 以條件輪詢輔助函式取代固定短 `time.sleep` 時序等待，提升測試穩定度。
     - **`T-31 (PERF-10)`**：於 `dev/checker.py:Checker.check_module` 建立單次模組檢核生命週期之 AST 解析快取，避免對同一 `.py` 檔案重複讀取與 `ast.parse()`。
     - **`T-39 (EX-2)`**：於 `server/streamer.py:DebouncedIOStreamer` 實作 `max_buffer_bytes=4096` 緩衝上限與 `debounce_ms` 批次合併（避免每遇到換行就立即觸發一次跨進程 IPC flush，僅在緩衝達上限、防抖計時到期或 `flush()` 時送出）。
  3. **`ast`、`knowledge-db` 與 `agents-workflow` 效能細節打磨 (`T-28`, `T-29`, `T-32`, `T-33`, `T-34`, `T-35`, `T-38`)**：
     - **`T-28 (PERF-07)`**：修正 `ast_engine/schema.py:UnifiedSymbol.from_dict`，不再為每個 `MemberInfo` 重複建立多餘的 `UnifiedSymbol` 放入 `children`（統一保持 `Tuple[MemberInfo, ...]`），消除從磁碟載入快照時的雙重實例化與型別不一致，並保持 `to_dict()` 格式 100% 向下相容。
     - **`T-29 (PERF-08)`**：於 `ast_engine/linker.py` 將 BFS 佇列 `list.pop(0)` 改為 `collections.deque.popleft()`，並快取繼承關係映射（`class_bases`, `base_derived`, `methods_by_class`），加速 `expand_contract_symbol_ids`。
     - **`T-32 (PERF-12)`**：於 `agents_workflow/compiler.py:compile_stage1` 快取單輪編譯之 `inserts` 解析結果並以 `@functools.lru_cache` 快取標籤 Regex；於 `publisher.py:release_all` 避免重複無意義重算相同指紋。
     - **`T-33 (PERF-13)`**：於 `knowledge_db/retrieval.py:BM25Engine._score_candidate_documents` 在計分迴圈前提前過濾不符 `flt.spaces`、`flt.languages`、`flt.kinds` 與 `allowed_ftypes` 之 `doc_id`。
     - **`T-34 (PERF-14)`**：於 `knowledge_db/retrieval.py:SnippetExtractor` 與 `ast_engine/resolver.py:SnippetExtractor` 新增以 `(real_path, mtime_ns)` 為鍵的檔案行快取（上限 32 檔），避免同檔多符號聚合時重複讀檔且保證長生命週期實例不讀到舊內容。
     - **`T-35 (PERF-15)`**：於 `ast_engine/parsers/treesitter.py` 與 `python_ast.py` 之 `extract_call_sites` 迴圈前預先按行數跨度（span）排序 `target_symbols`，迴圈內以 `next(...)` 線性取首個匹配符號，保持原語意且消除 $O(C \cdot S \log S)$ 重複排序。
     - **`T-38 (PERF-18)`**：於 `agents_workflow/plans/verifier.py:PlanVerifier` 預編譯佔位符正則表達式並移出內層重複 `re.sub` 計算。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `server/master.py` 直接復用 `core.platform.venv.get_venv_site_packages`。
  - `core/commands/dispatcher.py:_try_hot_dispatch` 直接復用 `sub_01` 已建立之 `_hot_dispatch_attempt` 與 `_HotDispatchResult(exit_code, accepted)`。
- **邊界排除 (Explicitly Excluded)**：
  - **`T-27 (Y-17)`**：依開發者裁示，已轉入 [plans/roadmap/doc_and_plan_archive_governance.md](../../roadmap/doc_and_plan_archive_governance.md) 並標記為「尚未完整調研」，不在本子計畫改動。
  - **`T-28` 直接 Pickle 實例**：依開發者裁示採選項 A，僅修正 `UnifiedSymbol.from_dict` 消除雙重實例化，保持 `to_dict()` 字典格式向下相容。
- **架構影響範圍**：`yscb.py`、`core`、`server`、`dev`、`ast`、`knowledge-db`、`agents-workflow` 及對應單元測試。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]**（Q1 / `T-27` 定案）：`T-27 (Y-17)` 僅轉入 `/roadmap`（`plans/roadmap/doc_and_plan_archive_governance.md`）並於標頭與內文標記為「尚未完整調研」，不在 `sub_05` 修改。
- **[P00:DR-02]**（Q2 / `DEV-01` 定案）：採選項 A，非嚴格模式下 `_try_hot_dispatch` 僅在「請求未送達 (`accepted=False`)」時 fallback 至本地冷派發；若請求已由 Worker 接收執行（`accepted=True`）卻逾時或失敗，直接返回非零退出碼，不重複執行第二次。
- **[P00:DR-03]**（Q3 / `T-28` 定案）：採選項 A，修正 `UnifiedSymbol.from_dict` 不再為每個 `MemberInfo` 重複實例化 `UnifiedSymbol` 放入 `children`（統一保持 `Tuple[MemberInfo, ...]`），同時保留 `to_dict()` 相容格式。
- **[P00:DR-04]**（Q4 / `T-36` 定案）：`T-36 (PERF-16)` 一併於 `OSBackend.__init__` 順手修補快取 `self._real_root_dir`。

---

## 3. 開放議題與確認紀錄

- **全部議題已定案**：Q1→DR-01、Q2→DR-02、Q3→DR-03、Q4→DR-04。

