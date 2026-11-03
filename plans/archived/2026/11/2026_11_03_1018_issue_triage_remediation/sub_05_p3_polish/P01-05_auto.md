# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：P3 效能與穩健性細節打磨 (sub_05_p3_polish)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 非嚴格模式熱派發已接收請求不重複冷派發 (`DEV-01`) | 於 `core/commands/dispatcher.py:_try_hot_dispatch` 對齊 `strict_hot_dispatch` 安全語意：僅當 `_hot_dispatch_attempt` 回傳 `res.accepted == False`（Daemon 離線或握手階段失敗，請求尚未被 Worker 執行）時回傳 `None` 以降級至本地冷派發；若 `res.accepted == True`（請求已被 Worker 接收並執行，但發生逾時或中途異常，此時 `res.exit_code is not None`），則直接回傳 `res.exit_code`，禁止再次執行本地冷派發。 | P1 | [P00:DR-02] |
| **FR-02** | `yscb.py` 與 `core/engine.py` SemVer 預發布標籤排序與原子寫入收斂 (`T-22`, `T-23`) | ① 於 `yscb.py:_parse_simple_semver` 與 `core/engine.py:_parse_version_tuple` 支援預發布標籤（如 `1.2.0-rc1`、`1.2.0.0-alpha.1`），確保相同主版號三/四元組下「無預發布標籤之正式版 > 有預發布標籤之預發布版」，且不會因單純濾除非數字字元將 `"0-rc1"` 誤解析為數字 `1`；② 於 `yscb.py:_write_json_lf` 移除 `os.replace(tmp_path, path)` 前多餘之 `os.remove(path)`，消除目標檔短暫不存在之非原子空窗。 | P2 | [P00:DR-01] |
| **FR-03** | `core` 高頻 URI 協議表快取、`OSBackend._real_root_dir` 快取、遙測尾端讀取與檔案鎖錯誤分流 (`T-30`, `T-36`, `T-37`, `T-40`) | ① `T-30`：於 `core/uri.py:_build_scheme_token_map` 快取已合併之唯讀 `token_map` 並設 `100ms` 單調時鐘視窗（重入時繞過快取，且每個調用端取得淺拷貝字典項目或不可變映射），免除單次指令內數百次 `uri.resolve()` 重複 `stat`；② `T-36`：於 `core/vfs/os_backend.py:OSBackend.__init__` 預先計算 `self._real_root_dir`，使 `assert_safe_path` 在 `root is None` 時直接複用並簡化布林返回；③ `T-37`：於 `core/telemetry.py:_rotate_telemetry_file` 由尾端反向收集 `keep_lines` 筆有效 JSON 行，並於 `read_telemetry_records` 在 `cutoff_epoch is None` 且 `limit > 0` 時先以 `collections.deque` 切片尾端候選行再解析；④ `T-40`：於 `core/platform/lock.py:_try_lock_fd` 僅將鎖競爭錯誤碼（`EACCES`, `EAGAIN`, `EWOULDBLOCK` 及 Windows `ERROR_LOCK_VIOLATION=33` / `EACCES`）視為鎖定失敗回傳 `False`，對檔案系統不支援鎖（`ENOTSUP`, `EOPNOTSUPP`, `ENOSYS`）或其他非預期 `OSError` 往上拋出。 | P2 | [P00:DR-04] |
| **FR-04** | `server` 與 `dev` 穩健性、串流緩衝與 AST 快取打磨 (`T-24`, `T-25`, `T-26`, `T-31`, `T-39`) | ① `T-24`：於 `server/master.py` 改用 `core.platform.venv.get_venv_site_packages` 取代重複手寫的 site-packages 路徑探測；② `T-25`：於 `server/master.py` 將 `self._tasks_executed += 1` 置於鎖保護內遞增；③ `T-26`：於 `server/tests/test_server.py` 以條件輪詢取代固定短 `time.sleep`；④ `T-31`：於 `dev/checker.py:Checker.check_module` 建立單次模組檢核級 `_parsed_py_cache`，供 `_check_package_dunder_version`、`_check_cli_compliance`、`_check_source_files`、`_check_test_classes` 與 `_check_sandbox_hooks` 共享單次讀檔與 `ast.parse()` 結果；⑤ `T-39`：於 `server/streamer.py:DebouncedIOStreamer` 新增 `max_buffer_bytes: int = 4096`，寫入時僅在緩衝累積達 `max_buffer_bytes` 或防抖計時器到期／`flush()` 時才觸發跨進程 IPC flush，不再每逢 `\n` 立即 flush。 | P2 | [P00:DR-01] |
| **FR-05** | `ast` 雙重實例化消除、繼承拓撲快取與呼叫點預排序 (`T-28`, `T-29`, `T-35`) | ① `T-28`：於 `ast_engine/schema.py:UnifiedSymbol.from_dict` 將 `children` 與 `members` 統一反序列化為 `Tuple[MemberInfo, ...]`（若輸入含巢狀 `UnifiedSymbol` 字典則相容轉換，不再為每個 `MemberInfo` 重複建立合成 `UnifiedSymbol` 放入 `children`），消除載入快照時雙倍物件分配與型別不一致，同時維持 `to_dict()` 格式 100% 向下相容；② `T-29`：於 `ast_engine/linker.py` 將 BFS 佇列 `list.pop(0)` 改為 `collections.deque.popleft()`，並於 `TopologyLinker` 建立繼承映射快取（`_class_bases`, `_base_derived`, `_methods_by_class_short`），加速 `expand_contract_symbol_ids`；③ `T-35`：於 `ast_engine/parsers/treesitter.py` 與 `python_ast.py` 之 `extract_call_sites` 在進入呼叫點迴圈前預先將 `target_symbols` 按 `(s.end_line - s.line_number)` 升冪排序一次，迴圈內以 `next(...)` 取得首個包含該行號之最小跨度符號，100% 保持原排序語意並消除 $O(C \cdot S \log S)$ 重複排序。 | P2 | [P00:DR-03] |
| **FR-06** | `knowledge-db` 與 `agents-workflow` 檢索與編譯快取打磨 (`T-32`, `T-33`, `T-34`, `T-38`) | ① `T-33`：於 `knowledge_db/retrieval.py:BM25Engine._score_candidate_documents` 建立候選 `doc_id` 預過濾（提前檢驗 `flt.spaces`、`flt.languages`、`flt.kinds` 與 `allowed_ftypes`），不符條件之文件直接跳過四欄位 BM25 浮點計分與字串切割；② `T-34`：於 `knowledge_db/retrieval.py:SnippetExtractor` 與 `ast_engine/resolver.py:SnippetExtractor` 新增以 `(str(real_path), mtime_ns)` 為鍵之 `_file_lines_cache`（LRU 上限 32 檔），避免同檔多符號重複讀檔且保證檔案修改後自動失效；③ `T-32`：於 `agents_workflow/compiler.py` 以 `@functools.lru_cache(maxsize=128)` 快取標籤 Regex，於 `compile_stage1` 單輪編譯內快取 `inserts` 之 `uri` 檔案讀取與 `computed` 計算結果，並於 `publisher.py:release_all` 復用相鄰一致之指紋計算；④ `T-38`：於 `agents_workflow/plans/verifier.py:PlanVerifier` 快取預編譯之佔位符 `re.Pattern` 清單，並在 `_check_changelog_content` 將 `re.sub` 移出內層 pattern 迴圈外單次計算。 | P2 | [P00:DR-01] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `_try_hot_dispatch` 在 Worker 接收請求前（如 socket 連線被拒、握手失敗）與接收請求後（如任務執行逾時 120s 或 Worker 崩潰）之差異 | `accepted == False` 時回傳 `None` 透明降級至本地冷派發；`accepted == True` 時回傳非零退出碼（如 `1`），絕不重複冷派發執行第二次。 |
| **EC-02** | `UnifiedSymbol.from_dict` 讀取舊版 `.bin.gz` 快取（其中 `children` 欄位可能存放舊版 `UnifiedSymbol.to_dict()` 格式或 `MemberInfo.to_dict()` 格式） | `from_dict` 兼容兩種字典格式，統一收斂為 `Tuple[MemberInfo, ...]`（若傳入完整子 `UnifiedSymbol` 則保留或轉換為 `MemberInfo`），且 `to_dict()` 輸出鍵值維持不變。 |
| **EC-03** | 長生命週期 Server Worker 中 `SnippetExtractor` 讀取之原始碼檔案在兩次檢索間被編輯修改 | 快取鍵包含 `stat().st_mtime_ns`，檔案一旦修改 `mtime_ns` 即改變，100% 命中最新檔案內容，絕不回傳過期程式碼片段。 |
| **EC-04** | `extract_call_sites` 中存在巢狀函式或類別方法（多個符號皆涵蓋呼叫點行號 `line_no`） | 預排序嚴格維持原鍵 `key=lambda s: (s.end_line - s.line_number)`（Python Timsort 穩定排序），`next((s for s in sorted_syms if s.line_number <= line_no <= s.end_line), None)` 選出與原本 `matching_syms.sort(...); matching_syms[0]` 完全一致的最小跨度符號。 |
| **EC-05** | `DebouncedIOStreamer` 接收到未滿 4096 bytes 的短輸出後任務立即結束 | `close()` / `flush()` 時強制將剩餘緩衝區完整送出並取消防抖計時器，確保零遺失任何尾端輸出。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 向後相容性 | 全數 7 個模組之 Public API 簽名與 CLI 參數契約 100% 向下相容。 |
| **NFR-02** | 測試與靜態合規 | `dev check --all` 7 模組 0 錯誤 0 警告；涉及之 `core`、`server`、`dev`、`ast`、`knowledge-db`、`agents-workflow` 單元測試 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` (`R01_issue_triage.md` §1 / `T-34`, `T-35`)**：原審計報告對 `PERF-14` (`T-34`) 建議無條件按路徑快取檔案行，在常駐 Worker 中會讀到舊內容，**必須將 `mtime_ns` 納入快取鍵**；原報告對 `PERF-15` (`T-35`) 建議改按 `kind` 優先級排序會改變語意，**必須僅按行數跨度 `s.end_line - s.line_number` 預排序**。
- **`[!NOTE]` (`docs/server/DESIGN_NOTES.md` `[DN-11]`)**：`sub_01` 已在 `core/commands/dispatcher.py` 建立 `_HotDispatchResult(exit_code, accepted)`，`_try_hot_dispatch` 可直接依據 `res.accepted` 區分「未送達」與「已送達後失敗」。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Subagent Group A: yscb.py + core + server + dev]
  ├── yscb.py                       : T-22 (_parse_simple_semver 預發布排序), T-23 (_write_json_lf 移除冗餘 os.remove)
  ├── core/engine.py                : T-22 (_parse_version_tuple 預發布排序)
  ├── core/commands/dispatcher.py   : DEV-01 (_try_hot_dispatch 檢查 res.accepted)
  ├── core/uri.py                   : T-30 (_build_scheme_token_map 100ms 單調時鐘快取 + invalidate)
  ├── core/vfs/os_backend.py        : T-36 (_real_root_dir 預計算快取)
  ├── core/telemetry.py             : T-37 (_rotate_telemetry_file 與 read_telemetry_records 尾端切片)
  ├── core/platform/lock.py         : T-40 (_try_lock_fd 區分鎖競爭與不支援鎖之 OSError)
  ├── server/master.py              : T-24 (復用 get_venv_site_packages), T-25 (_tasks_executed 鎖內遞增)
  ├── server/streamer.py            : T-39 (DebouncedIOStreamer max_buffer_bytes=4096 緩衝)
  └── dev/checker.py                : T-31 (check_module 單次模組 AST 解析快取)

[Subagent Group B: ast + knowledge-db + agents-workflow]
  ├── ast_engine/schema.py          : T-28 (UnifiedSymbol.from_dict 消除雙重實例化)
  ├── ast_engine/linker.py          : T-29 (collections.deque + 繼承拓撲索引快取)
  ├── ast_engine/parsers/treesitter.py & python_ast.py : T-35 (extract_call_sites 預排序)
  ├── ast_engine/resolver.py        : T-34 (SnippetExtractor (path, mtime_ns) 快取)
  ├── knowledge_db/retrieval.py     : T-33 (BM25 提前過濾), T-34 (SnippetExtractor (path, mtime_ns) 快取)
  ├── agents_workflow/compiler.py & publisher.py : T-32 (lru_cache regex + Stage 1 inserts 快取)
  └── agents_workflow/plans/verifier.py : T-38 (預編譯佔位符 regex + 移出內層 re.sub)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | `T-22` 預發布版號排序權重、`T-23` `_write_json_lf` 移除 `os.remove` |
| `ys_codebase/source/core/core/engine.py` | Modify | `T-22` `_parse_version_tuple` 支援預發布標籤排序權重 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `DEV-01` `_try_hot_dispatch` 在 `res.accepted` 為真時不降級冷派發 |
| `ys_codebase/source/core/core/uri.py` | Modify | `T-30` `_build_scheme_token_map` 快取與 `100ms` 單調時鐘視窗 |
| `ys_codebase/source/core/core/vfs/os_backend.py` | Modify | `T-36` `OSBackend.__init__` 預先計算 `self._real_root_dir` |
| `ys_codebase/source/core/core/telemetry.py` | Modify | `T-37` `_rotate_telemetry_file` 與 `read_telemetry_records` 尾端讀取優化 |
| `ys_codebase/source/core/core/platform/lock.py` | Modify | `T-40` `_try_lock_fd` 僅攔截鎖競爭 `errno`，其餘 `OSError` 拋出 |
| `ys_codebase/source/server/server/master.py` | Modify | `T-24` 復用 `get_venv_site_packages`、`T-25` `_tasks_executed` 鎖內遞增 |
| `ys_codebase/source/server/server/streamer.py` | Modify | `T-39` `DebouncedIOStreamer` 4096 bytes 緩衝與防抖批次沖刷 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `T-31` `Checker` 單次模組檢核 AST 解析快取 |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | `T-28` `UnifiedSymbol.from_dict` 統一 `children`/`members` 為 `Tuple[MemberInfo, ...]` |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | `T-29` `collections.deque` 與繼承拓撲映射快取 |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | `T-35` `extract_call_sites` 預排序 `target_symbols` |
| `ys_codebase/source/ast/ast_engine/parsers/python_ast.py` | Modify | `T-35` `extract_call_sites` 預排序 `target_symbols` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | `T-34` `SnippetExtractor` 帶 `mtime_ns` 鍵之檔案行快取 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `T-33` BM25 計分前過濾、`T-34` `SnippetExtractor` 帶 `mtime_ns` 鍵之快取 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `T-32` `@lru_cache` Regex 與 `compile_stage1` `inserts` 預先求值快取 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | `T-32` `release_all` 避免無變更時重複重算相同來源指紋 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | `T-38` `PlanVerifier` 預編譯佔位符 Regex 與移出內層 `re.sub` |
| `ys_codebase/source/core/tests/test_core_commands.py` | Modify | 新增 `DEV-01` 單元測試 |
| `ys_codebase/source/core/tests/test_platform.py` | Modify | 新增 `T-22`, `T-30`, `T-36`, `T-37`, `T-40` 單元測試 |
| `ys_codebase/source/server/tests/test_server.py` | Modify | `T-26` 條件輪詢與 `T-39` `DebouncedIOStreamer` 4096 緩衝測試 |
| `ys_codebase/source/ast/tests/test_ast_engine.py` | Modify | 新增 `T-28`, `T-29`, `T-35` 單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 新增 `T-33`, `T-34` 單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 將 19 項實作項依模組正交邊界拆分為 Group A（`yscb.py` + `core` + `server` + `dev`）與 Group B（`ast` + `knowledge-db` + `agents-workflow`）兩個平行實作軌道，零共用檔案衝突。
- **[P02:DR-02]** `SemVer` 預發布比較元組擴充為 `(major, minor, patch, revision, is_release_not_prerelease, prerelease_tag, is_build)`，使 `1.2.0-rc1` `<` `1.2.0`，且相容既有 `Tuple` 解構或索引。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/commands/dispatcher.py
def _try_hot_dispatch(
    module_name: str,
    cmd_path: List[str],
    sub_args: List[str],
    yscb_abs: str,
) -> Optional[int]: ...

# ys_codebase/source/server/server/streamer.py
class DebouncedIOStreamer(io.TextIOBase):
    def __init__(
        self,
        stream_name: str,
        send_callback: Callable[[str, str], None],
        debounce_ms: int = 500,
        max_buffer_bytes: int = 4096,
    ) -> None: ...

# ys_codebase/source/ast/ast_engine/schema.py
class UnifiedSymbol:
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSymbol": ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `InterProcessLock._try_lock_fd`：當 `OSError.errno` 屬於鎖競爭（`EACCES`, `EAGAIN`, `EWOULDBLOCK`）時回傳 `False`；當屬於檔案系統不支援鎖或其他系統錯誤時直接向上拋出 `OSError`。
- **階段決策紀錄**：`[P03:DR-01]` `_parse_simple_semver(v_str)` 為相容既有 `not _parse_simple_semver(v)[4]` 索引，`index 4` 維持 `is_build: bool`，新增預發布排序鍵於 `index 5`（或將每段格式化為 `(num, is_final, prerelease_str)`），確保 `len` 與索引 `[4]` 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 完整覆蓋 `T-22 ~ T-26`、`T-28 ~ T-40` 與 `DEV-01`（`T-27` 已入庫 `/roadmap`）。
- [x] **邊界防護**：EC-01 ~ EC-05 均具明確防護與測試案例。
- [x] **依賴純淨**：100% 符合 NFR 指標約束，零外部新依賴。
- **靈魂拷問與防護解法**：
  - *問*：在 `yscb.py:_parse_simple_semver` 修改返回結構會不會破壞 `yscb.py` 內部呼叫 `_parse_simple_semver(v)[4]`（檢查 `is_build`）？
  - *答*：保持返回元組前 5 個元素 `(major, minor, patch, revision, is_build, prerelease_weight)`，其中 `[0..3]` 為純數字版號（取連字號 `-` 之前的部分解析數字），`[4]` 維持 `is_build: bool`，`[5]` 為 `(1, "")`（正式版）或 `(0, prerelease_tag)`（預發布版）。如此 `_parse_simple_semver(v)[4]` 100% 不變，且元組整體比較時同版號正式版 `(..., False, (1, ""))` 自然大於預發布版 `(..., False, (0, "rc1"))`！

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 補充非嚴格模式熱派發已接收請求不重試冷派發說明 (`DEV-01`) |
| **專題手冊** | `docs/server/daemon_architecture.md` | Modify | 補充 `DebouncedIOStreamer` `max_buffer_bytes=4096` 雙水位防抖串流機制 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 更新 `[DN-11]` 涵蓋非嚴格模式已接收請求不重試冷派發 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新變更函式與方法之 Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_05_p3_polish` 發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認上述規格與兩組平行實作分派，立即執行 Pre-Code Analyze Gate 與實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 Group A（`yscb.py`, `core`, `server`, `dev`：`DEV-01`, `T-22` ~ `T-26`, `T-30`, `T-31`, `T-36`, `T-37`, `T-39`, `T-40`）與對應單元測試。
- [x] **TASK-02**：實作 Group B（`ast`, `knowledge-db`, `agents-workflow`：`T-28`, `T-29`, `T-32` ~ `T-35`, `T-38`）與對應單元測試。
- [x] **TASK-03**：執行全模組 `dev check --all` 與 6 模組單元測試回歸驗證。
- [x] **TASK-DOC**：同步更新微觀代碼 Docstrings。

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| TASK-02 | Minor | `knowledge-db` 測試 `test_schema.py` 存取 `restored.children[0].fqn` / `parent_id` / `return_type` / `parameters`；於 `ast_engine.schema.MemberInfo` 補齊該 4 個選填欄位相容保留，使 `UnifiedSymbol.from_dict` 統一為 `Tuple[MemberInfo, ...]` 時 100% 向下相容 | 已補齊並通過全量測試 |

