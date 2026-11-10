# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_05_agents_workflow_and_gdrive_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `gdrive-support` 空間掃描與敏感憑證守門之 Symlink 真實路徑防禦及輕量組態委派 (`WF-AUD-01`, `WF-AUD-11`, `ARCH-GD-05`, `ARCH-GD-10`) | [`gdrive-support/gdrive_support/config.py`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) 於 `collect_space_local_files_with_stat` 拒絕將符號連結納入上傳清單，於 `is_local_abs_allowed` 與 `is_sensitive_credential_path` 對字面路徑及 `os.path.realpath()` 執行雙重檢核；提供 `load_lightweight_repo_sync_settings` 供 `scripts/hook.core.py` 直接委派並同時支援 `repo_sync.sync_spaces` 與頂層 `sync_spaces`。 | P0 | [P00:DR-01] |
| **FR-02** | `agents-workflow` 圍欄代碼塊 `//` 保護、單行錨點完整展開、單次雙雜湊快取與發布器 `agent_rules` 對齊 (`WF-AUD-02` ~ `WF-AUD-04`, `ARCH-AW-01`, `ARCH-AW-04`, `ARCH-AW-07`) | 1. [`compiler.py`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) `make_standalone_tag_regex` 加入 `(?:^|(?<=\x00))[ \t]*...$` 多行錨點，移除 `count=1` 限制，並允許同 Token 同時展開獨立行與行內標籤。<br>2. `_substitute_stage2_tags_in_segment` 僅在 URI 展開接合邊界（`_clean_expanded_uri_boundary`）清理重複斜線，並於 `MD_LINK_BACKTICK_CLEAN_REGEX` 前遮罩圍欄代碼塊，保護程式碼區塊與行內代碼塊內之 `//`。<br>3. `_read_and_cache_physical_file` 單次讀取並快取 `SHA-1`/`SHA-256`，`compile_stage1` 附帶預計算 `sha256`；[`publisher.py`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) 對齊 `agent_rules` 之物化、孤兒清理、`.gitignore` 收集與驗證邏輯。 | P0 | [P00:DR-03] |
| **FR-03** | `GDriveCoordinator` Stage 1 `meta_dirty`、Pull 快取一致性、服務動態分支重新整理與 `GoogleDriveApiTransport` 連線池/CQS 收口 (`WF-AUD-05`, `WF-AUD-06`, `ARCH-GD-03`, `ARCH-GD-04`, `ARCH-GD-08`, `ARCH-GD-12`) | 1. [`coordinator.py`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) 追蹤 `stage1_meta_dirty` 並合入 Stage 3 `meta_dirty`；`_execute_pull_batch` 同步更新 `remote_repo_cache` (`raw_entries`) 與 `fingerprint_cache` 並寫入 WAL 日誌。<br>2. [`service.py`](https://drive.google.com/file/d/1-s1zWxlX2uqcMC8C5N5_py_uRqFxEffC/view?usp=drivesdk) `GDriveSyncServiceWorker` 於每次 `run_once()` 動態重新整理 `active_branch` 並於 `stop()` 關閉自建 `transport`。<br>3. [`transport.py`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk) 實作跨執行緒連線池回收與 `close()` 全量釋放，並支援 `list_files(..., deduplicate=False)` 供 `cli.ls` 執行純唯讀列舉。 | P1 | [P00:DR-02] |
| **FR-04** | `PlanVerifier` 交易式自癒與共用表格解析、統一計畫完成度狀態機與同步加速 (`WF-AUD-07` ~ `WF-AUD-13`, `ARCH-AW-02`, `ARCH-AW-03`, `ARCH-AW-08`, `ARCH-AW-11`) | 1. [`plans/_common.py`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk) 集中提供 `parse_changelog_table`（支援 `\|` 轉義直線）、`is_revision_root_dir`、`evaluate_plan_completion` 與 `DEFAULT_URI_FALLBACKS` (`workflow.roadmap://`, `workflow.docs://`)。<br>2. [`plans/verifier.py`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) 與 [`_verifier_healer.py`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk) 實作 `pending_writes` 交易式自癒（驗證失敗時回滾不污染磁碟）、攔截空白標頭值並維持 `_extract_non_code_lines` 1:1 物理行號。<br>3. `status.py`、`scanner.py` 與 `archiver.py` 統一處理附掛 `revision_log.md` 與 Umbrella 子計畫完成度校驗及 `sub_XX/handoff.md` 清理；`checkout_branch` 傳遞 `entry_hint`。 | P2 | [P00:DR-01], [P00:DR-02], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 同步空間內存在指向空間外部或敏感憑證之 Symlink `docs/sym_cred.md` | `collect_space_local_files_with_stat`、`is_local_abs_allowed` 與 `is_sensitive_credential_path` 拒絕納入掃描清單並阻斷上傳。 |
| **EC-02** | 技能或計畫模板之 Fenced Code Block 內含 Python `x = a // b`、C++ `// comment` 與 `__#{...}__` 標籤 | 僅替換 URI 標籤與其緊鄰斜線邊界，程式碼區塊內的 `x = a // b` 與 `// comment` 100% 原樣保留；同一檔案出現多個相同獨立行與行內標籤時全數展開。 |
| **EC-03** | 雲端新增或更新檔案後執行 `pull`（無本地新增或刪除），或前景執行 `checkout_branch` 後背景 Worker 觸發同步 | `GDriveCoordinator` 將 Stage 1 重建之 `branch_files` 持久化寫回遠端 `.yscb_gdrive.json`，同時更新本地 `remote_repo_cache` 與 `fingerprint_cache`；`GDriveSyncServiceWorker` 自動切換至最新 `active_branch`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零資源洩漏與編譯效能優化 | 執行平行 `pull`/`push` 與 `transport.close()` 後 `0 ResourceWarning`；Stage 1 編譯與雜湊計算延遲顯著降低（實測 20 輪平均由 `194.207 ms` 降至 `182.041 ms`）。 |
| **NFR-02** | 靜態守門與回歸測試 | `python3 yscb.py dev check` 9/9 模組 0 違規，且 `agents-workflow` (147/147) 與 `gdrive-support` (36/36) 單元測試 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 修改 `make_standalone_tag_regex` 時，因 `_preprocess_directives` 在 `strip_literal_markers=False` 下會將 `<!-- yscb:literal:end -->\n` 連同換行符收入 `\x00YSCB_LITERAL_BLOCK_{idx}\x00` 佔位符，緊接在 literal 區塊後方的獨立行標籤在 `resolved_text` 中前綴為 `\x00`，故正則行首錨點須採用 `(?:^|(?<=\x00))[ \t]*` 以相容 literal 區塊後的獨立行 Token 展開。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

- **Symlink 與敏感憑證雙重守門 (`gdrive_support.config`)**：`collect_space_local_files_with_stat` 跳過所有 `os.path.islink` 項目；`is_local_abs_allowed` 與 `is_sensitive_credential_path` 以 `_realpath_no_stat` 同時校驗字面路徑與真實目標路徑，避免觸發冗餘 `Path.stat()`。
- **執行緒安全連線池 (`GoogleDriveApiTransport`)**：在 `GoogleDriveApiTransport` 維護實例級 `_conn_pool` 與 `_tls_conn_dicts`，平行任務結束時透過 `_release_thread_conns_to_pool()` 將執行緒連線歸還池中供後續執行緒複用，`close()` 時關閉所有連線。
- **統一計畫狀態機與交易式自癒 (`agents_workflow.plans`)**：透過 `_common.py` 之 `parse_changelog_table`、`is_revision_root_dir` 與 `evaluate_plan_completion` 統一 `status.py`、`scanner.py`、`archiver.py`、`verifier.py` 與 `session_trace.py` 的判定基準；`verifier.py` 以 `pending_writes` 緩衝自癒結果，僅當驗證通過時才寫入磁碟。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 圍欄代碼塊感知之 Stage 2 展開與邊界斜線清理、獨立行+行內雙重展開、`_resolve_workflow_uri_fallback`、單次讀檔與 SHA-1/SHA-256 快取 (`ARCH-AW-01`, `ARCH-AW-04`, `ARCH-AW-07`, `WF-AUD-02`, `WF-AUD-03`, `WF-AUD-10`) |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 對齊 `agent_rules` 注入/複製模式之物化、孤兒清理、`.gitignore` 收集與驗證邏輯，並複用 `compiler._source_file_cache` (`ARCH-AW-04`, `WF-AUD-04`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py` | Modify | 新增共用 `parse_changelog_table`、`is_revision_root_dir`、`evaluate_plan_completion` 並補齊 `DEFAULT_URI_FALLBACKS` (`ARCH-AW-02`, `ARCH-AW-08`, `ARCH-AW-11`, `WF-AUD-10`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_verifier_specs.py` | Modify | 統一 `VALID_STATUSES` 納入 `implementing` 與 `phase 0` (`ARCH-AW-02`, `ARCH-AW-08`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | 支援已結案計畫附掛活躍 `revision_log.md` 之導航解析 (`ARCH-AW-02`, `ARCH-AW-08`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Modify | Umbrella 含未完成 `sub_XX` 時回報 `In Progress`，且 `resolve_target_plan_dir` 識別附掛活躍 `revision_log.md` 之計畫 (`ARCH-AW-02`, `WF-AUD-09`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` | Modify | 委派 `evaluate_plan_completion` 驗證主計畫、全部 `sub_XX` 與 `revision_log.md` 皆已完成，並清理 `sub_XX/handoff.md` (`ARCH-AW-02`, `WF-AUD-09`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_verifier_healer.py` | Modify | 支援 `pending_writes` 交易式自癒緩衝、共用 `parse_changelog_table` 與非空標頭檢核 (`ARCH-AW-03`, `ARCH-AW-11`, `WF-AUD-07`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 實作交易式自癒提交/回滾、非空標頭檢核與 `_extract_non_code_lines` 1:1 物理行號保留 (`ARCH-AW-03`, `ARCH-AW-11`, `WF-AUD-07`, `WF-AUD-08`) |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | 委派共用 `parse_changelog_table` 解析回寫紀錄 (`ARCH-AW-11`) |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 實作 Symlink 拒絕與 `_realpath_no_stat` 雙重守門、支援頂層與 `repo_sync` 雙層 `sync_spaces`、新增 `load_lightweight_repo_sync_settings` (`WF-AUD-01`, `WF-AUD-11`, `ARCH-GD-05`, `ARCH-GD-10`) |
| `ys_codebase/source/gdrive-support/scripts/hook.core.py` | Modify | 委派 `gdrive_support.config.load_lightweight_repo_sync_settings` 消除重複組態解析 (`ARCH-GD-05`) |
| `ys_codebase/source/gdrive-support/gdrive_support/transport.py` | Modify | 新增 `list_files(..., deduplicate=True)` CQS 控制、實例級 `_conn_pool` 跨執行緒連線複用與 `close()` 完整清理 (`WF-AUD-06`, `ARCH-GD-08`, `ARCH-GD-12`) |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | `ls` 與 `get` 傳遞 `reconcile_readme=False`，且 `ls` 預設傳遞 `deduplicate=False` (`ARCH-GD-08`) |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 追蹤 `stage1_meta_dirty`、Pull 更新 `remote_repo_cache` 與 `fingerprint_cache`、`checkout_branch` 傳遞 `entry_hint` 並記錄 `active_branch` (`WF-AUD-05`, `WF-AUD-12`, `WF-AUD-13`, `ARCH-GD-04`) |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | `GDriveSyncServiceWorker.run_once()` 動態重新整理 `active_branch`，且 `stop()` 關閉 `_owned_transport` (`WF-AUD-11`, `ARCH-GD-03`) |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 新增圍欄代碼塊 `//` 保留、獨立行與行內同 Token 展開及 Stage 1 `sha256` 測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增交易式自癒回滾、`\|` 轉義直線解析、圍欄代碼塊後 1:1 行號、附掛修訂導航與 Umbrella 未完成子計畫歸檔阻斷測試 |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | 新增 Symlink 越界/憑證守門、`load_lightweight_repo_sync_settings`、`list_files(deduplicate=False)` 與連線池回收關閉測試 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 新增 Pull 快取與 `fingerprint_cache` 同步、Stage 1 `branch_files` 持久化與 `GDriveSyncServiceWorker` 動態分支切換測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] Stage 2 URI 標籤局部斜線正規化與圍欄代碼塊遮罩 (`ARCH-AW-01`, `WF-AUD-03`)**：僅在替換 `__#{...}__` / `__${...}__` 產生之結果字串與緊鄰前綴/後綴之間消除雙斜線（`_clean_expanded_uri_boundary`），並在執行 `MD_LINK_BACKTICK_CLEAN_REGEX` 前先遮罩圍欄代碼塊，確保程式碼內 `//` 100% 不受影響。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py
def parse_changelog_table(content: str) -> Tuple[List[str], List[List[str]]]: ...
def is_revision_root_dir(plan_dir: Path) -> bool: ...
def evaluate_plan_completion(plan_dir: Path) -> Tuple[bool, List[str]]: ...

# ys_codebase/source/gdrive-support/gdrive_support/config.py
def load_lightweight_repo_sync_settings(registry: Optional[Any] = None) -> Tuple[bool, bool, List[str]]: ...
def is_sensitive_credential_path(abs_path: Path, proj_root: Path) -> bool: ...

# ys_codebase/source/gdrive-support/gdrive_support/transport.py
class AbstractSyncTransport:
    def list_files(self, remote_rel_path: str = "", recursive: bool = False, *, deduplicate: bool = True) -> List[RemoteEntry]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SyncSpaceSpec.is_local_abs_allowed` 對指向 `include_roots` 外部的 Symlink 一律回傳 `False`。
  - `PlanArchiver.archive_plan` 當主計畫、任一 `sub_XX` 子計畫或任一 `revision_log.md` 未達 `Completed` 時拋出 `PlanIncompleteError` 阻斷歸檔。
- **階段決策紀錄**：[P03:DR-01] 保持所有公開 CLI 與方法簽名 100% 向下相容（Mode B Public Compatibility）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-04 完整覆蓋 `WF-AUD-01` ~ `WF-AUD-13`、`ARCH-AW-01~12`、`ARCH-GD-01~14` 與 Surgery `S6`。
- **邊界防護**：EC-01 ~ EC-03 涵蓋 Symlink 越界、Fenced Code Block `//` 語法、雲端 CoW File ID 更新與前景/背景分支切換。
- **依賴純淨**：100% 符合 NFR-01 與 NFR-02。
- **靈魂拷問與防護解法**：若 `ThreadPoolExecutor` 內某條工作執行緒在執行 HTTP 請求中途發生網路異常，`_discard_https_conn(host)` 會直接關閉該損壞連線而不放回 `_conn_pool`，確保連線池內僅留存健康連線。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | Modify | 補充本地掃描預設忽略 Symlink、CQS 唯讀 `ls` 與真實路徑邊界校驗說明 |
| **專題手冊** | `docs/agents-workflow/README.md` | Modify | 補充模板編譯器 Fenced Code Block 保護與交易式 `PlanVerifier` 規範 |
| **設計決策** | `docs/gdrive-support/DESIGN_NOTES.md` | Modify | 記錄實例級 Keep-Alive 連線池、Pull 快取同步與 Stage 1 `meta_dirty` 對帳機制 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `config.py`、`coordinator.py`、`transport.py`、`compiler.py`、`verifier.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫結案時記錄 `sub_05` 與全倉修補摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_05` 規格定稿並完成實作與驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `FR-01`（`gdrive_support/config.py` 於 `collect_space_local_files_with_stat`、`is_local_abs_allowed` 與 `is_sensitive_credential_path` 加入 Symlink 與 `_realpath_no_stat` 雙重守門，並新增 `load_lightweight_repo_sync_settings` 供 `scripts/hook.core.py` 委派呼叫，`WF-AUD-01`, `WF-AUD-11`, `ARCH-GD-05`, `ARCH-GD-10`）
- [x] **TASK-02**：實作 `FR-02`（`agents_workflow/compiler.py` `make_standalone_tag_regex` 多行錨點與獨立/行內雙重替換、保護 Fenced Code Block `//`、單次讀檔與 SHA-1/SHA-256 快取，以及 `publisher.py` `agent_rules` 完整對齊，`WF-AUD-02` ~ `WF-AUD-04`, `ARCH-AW-01`, `ARCH-AW-04`, `ARCH-AW-07`）
- [x] **TASK-03**：實作 `FR-03`（`gdrive_support/coordinator.py` Stage 1 `stage1_meta_dirty` 持久化、Pull 更新 `remote_repo_cache` 與 `fingerprint_cache`，`service.py` 動態重新整理 `active_branch` 與 `stop()` 關閉自建 `transport`，以及 `transport.py` 跨執行緒連線池回收與 `list_files(deduplicate=False)` CQS 唯讀分離，`WF-AUD-05`, `WF-AUD-06`, `WF-AUD-11`, `ARCH-GD-03`, `ARCH-GD-04`, `ARCH-GD-08`, `ARCH-GD-12`）
- [x] **TASK-04**：實作 `FR-04`（`plans/_common.py` 共用 `parse_changelog_table` / `evaluate_plan_completion` / `is_revision_root_dir`、`verifier.py` 交易式自癒與空白標頭/1:1 行號對齊、`status.py` / `scanner.py` / `archiver.py` 狀態機統一與 `sub_XX/handoff.md` 清理、以及 `checkout_branch` 傳遞 `entry_hint`，`WF-AUD-07` ~ `WF-AUD-13`, `ARCH-AW-02`, `ARCH-AW-03`, `ARCH-AW-08`, `ARCH-AW-11`）
- [x] **TASK-05**：補齊 `agents-workflow` 與 `gdrive-support` 單元測試，重新建置模組歸檔並同步至 `/tmp/aw_pkg`，執行 `python3 yscb.py dev check`、`python3 yscb.py dev test --m agents-workflow` 與 `python3 yscb.py dev test --m gdrive-support` 驗證 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-02** | `Minor` | `LOCAL_MANIFEST_CACHE_URI` 在既有單元測試 (`test_publisher.py`) 中斷言儲存本機實體絕對路徑（與 `PROJECT_MANIFEST_CACHE_URI` 儲存 `project://` 相對 URI 區隔），故保留 `LOCAL_MANIFEST_CACHE_URI` 的實體絕對路徑格式，並完整對齊 `agent_rules` 之注入、清理、`.gitignore` 與檢核邏輯 | 已同步更新 §1.1 與 §2.2 規格說明，確保 100% 測試相容 |
