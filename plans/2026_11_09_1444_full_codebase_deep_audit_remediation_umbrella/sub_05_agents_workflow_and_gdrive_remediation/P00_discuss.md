# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_agents_workflow_and_gdrive_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將全倉深度審計報告（[`R01_full_codebase_deep_audit_report.md`](../R01_full_codebase_deep_audit_report.md)）中針對 `Unit 09`（`module:agents-workflow` 編譯器、發布器、計畫檢核與歸檔工具鏈）與 `Unit 10`（`module:gdrive-support` 同步協調器、`GoogleDriveApiTransport`、三方對帳器、常駐服務）檢出之全部 **13 項問題（`WF-AUD-01` ~ `WF-AUD-13`：1 P0, 5 P1, 5 P2, 2 P3）**，以及架構與演進債審計報告（[`R02_architecture_and_evolutionary_debt_audit.md`](../R02_architecture_and_evolutionary_debt_audit.md)）中之 **`ARCH-AW-01~12`、`ARCH-GD-01~14` 與 Mode A Surgery `S6`** 全量轉化為 `sub_05` 實作、基準評測、測試與 `P07` 結案閉環。
- **核心目標**：
  1. **根除 1 項 P0 本地空間掃描與敏感憑證守門未解析符號連結（Symlink）導致機密外洩與越界上傳漏洞（`WF-AUD-01`, `ARCH-GD-10`）**：
     - 加固 [`gdrive-support/gdrive_support/config.py:L334-L392, L680-L742`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) 之 `collect_space_local_files_with_stat`、`SyncSpaceSpec.is_local_abs_allowed` 與 `is_sensitive_credential_path`：跳過符號連結（`os.path.islink()`）並透過不觸發 `Path.stat()` 之 `os.path.realpath` 同步執行邊界與敏感憑證黑名單雙重檢查。
  2. **完成 `module:agents-workflow` 編譯器、發布器與計畫生命週期狀態機重構（`WF-AUD-02~04`, `WF-AUD-07~10`, `ARCH-AW-01~12`, Surgery `S6`）**：
     - **`ARCH-AW-01` & `WF-AUD-02` & `WF-AUD-03`**：於 `agents_workflow/compiler.py` 實作圍欄代碼塊感知（Code-Fence-Aware）之 Stage 2 展開與局部邊界斜線清理（`_clean_expanded_uri_boundary`），確保圍欄代碼塊與行內代碼塊中之 `//` 註解或 Python `//` 整數除法永不被誤刪；為 `make_standalone_tag_regex` 補上多行行首/行尾錨點並移除 `count=1` 限制。
     - **`ARCH-AW-02` & `ARCH-AW-08` & `WF-AUD-09`**：於 `agents_workflow/plans/_common.py`、`_verifier_specs.py`、`status.py`、`scanner.py` 與 `archiver.py` 收斂統一的計畫軌道與完成度狀態機（`evaluate_plan_completion`、`is_revision_root_dir`、`_has_active_attached_revision`、`VALID_STATUSES`），確保 Umbrella 子計畫未完成時狀態回報 `In Progress` 並阻斷歸檔、附掛於已結案計畫之進行中 `revision_log.md` 能被正確導航與攔截。
     - **`ARCH-AW-03` & `ARCH-AW-11` & `WF-AUD-07` & `WF-AUD-08`**：於 `verifier.py`、`_verifier_healer.py` 與 `session_trace.py` 統一 `changelog.md` 表格解析器（`parse_changelog_table` 支援 `\|` 轉義直線與 3/4 欄格式），實作交易式自癒緩衝（`pending_writes` 僅於 `not report.has_fails` 時原子落盤），檢核非空標頭值，並於 `_extract_non_code_lines` 保留 1:1 物理行號。
     - **`ARCH-AW-04`**：於 `compiler.py` 與 `publisher.py` 實作單次實體檔案讀取與雙雜湊快取（`_read_and_cache_physical_file` 同步計算並快取 `SHA-1` 與 `SHA-256`），並在 `compile_stage1` 直接附帶已展開內容之 `sha256` 摘要，消除重複雜湊計算。
  3. **完成 `module:gdrive-support` 同步協調器、連線池、輕量組態載入與 CQS 唯讀隔離（`WF-AUD-05~06`, `WF-AUD-11~13`, `ARCH-GD-01~14`, Surgery `S6`）**：
     - **`ARCH-GD-03` & `WF-AUD-11`**：於 `gdrive_support/service.py` 實作 `GDriveSyncServiceWorker._refresh_active_branch()`，每次同步週期動態重新整理當前 `active_branch`（支援前景 `gdrive checkout` 後無縫切換），並於 `stop()` 關閉自建 `_owned_transport`。
     - **`ARCH-GD-04` & `WF-AUD-05` & `WF-AUD-12` & `WF-AUD-13`**：於 `gdrive_support/coordinator.py` 追蹤 `stage1_meta_dirty` 確保 Stage 1 `branch_files` 重建結果寫回遠端 `.yscb_gdrive.json`；於 `_execute_pull_batch` 同步更新 `remote_repo_cache` 之 `raw_entries` 與 `fingerprint_cache`（並寫入/重播 WAL 日誌）；於 `checkout_branch` 傳遞 `entry_hint` 並持久化 `state["active_branch"]`。
     - **`ARCH-GD-05` & `WF-AUD-11`**：於 `gdrive_support/config.py` 新增 `load_lightweight_repo_sync_settings` 並支援 `repo_sync.sync_spaces` 與頂層 `sync_spaces`，使 `scripts/hook.core.py` 直接委派呼叫、消除重複 JSON 解析邏輯。
     - **`ARCH-GD-08`**：於 `transport.py` 為 `list_files` 新增 `deduplicate: bool = True` 參數，並更新 `scripts/cli.py` 使 `ls` 與 `get` 傳遞 `reconcile_readme=False` 且 `ls` 預設 `deduplicate=False`，落實命令查詢分離（CQS）。
     - **`ARCH-GD-12` & `WF-AUD-06`**：於 `transport.py` 實作跨執行緒安全之實例級 `HTTPSConnection` 連線池（`_conn_pool`、`_release_thread_conns_to_pool`）及 `urllib.request.urlopen` / `HTTPError` 確定性關閉，徹底根除 `ResourceWarning`。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `agents_workflow.plans._common`、`core.uri`、`core.vfs` 與 Python 標準庫，不引入第三方套件。
- **邊界排除 (Explicitly Excluded)**：不修改 `.yscb_gdrive.json` 遠端帳本 Schema 與既有公開 CLI 契約（Mode B 100% 向下相容）。
- **架構影響範圍**：`ys_codebase/source/agents-workflow/agents_workflow/{compiler,publisher}.py`、`agents_workflow/plans/{_common,_verifier_specs,_verifier_healer,verifier,status,scanner,archiver,session_trace}.py`、`gdrive-support/gdrive_support/{config,coordinator,transport,service}.py`、`gdrive-support/scripts/{cli,hook.core}.py` 及兩模組測試套件。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `gdrive-support` 本地空間掃描預設忽略 Symlink 並對 `realpath` 雙重守門 (`WF-AUD-01`, `ARCH-GD-10`)**：在 `collect_space_local_files_with_stat` 中遇到 `os.path.islink()` 時預設跳過不納入雲端上傳；在 `is_local_abs_allowed` 與 `is_sensitive_credential_path` 中使用 `os.path.realpath`（不觸發額外 `Path.stat()`）同時檢查字面路徑與真實目標路徑。
- **[P00:DR-02] `GoogleDriveApiTransport` 實例級執行緒安全 Keep-Alive 連線池與 CQS 唯讀 `ls` (`WF-AUD-06`, `ARCH-GD-08`, `ARCH-GD-12`)**：在 `GoogleDriveApiTransport` 維護實例級 `_conn_pool` 與 `_tls_conn_dicts`，平行任務結束時將工作執行緒連線歸還池中，並於 `close()` 關閉所有連線；`cli.ls` 預設以 `deduplicate=False`、`reconcile_readme=False` 執行純唯讀列舉。
- **[P00:DR-03] `agents-workflow` 圍欄代碼塊感知編譯、單次雙雜湊快取與交易式 `PlanVerifier` 自癒 (`ARCH-AW-01~04`, `ARCH-AW-08`, `ARCH-AW-11`)**：保護圍欄代碼塊與行內代碼塊內的 `//` 不受路徑斜線正規化影響；整合 `parse_changelog_table` 與 `evaluate_plan_completion` 至 `plans/_common.py`；`PlanVerifier.verify_plan` 透過 `pending_writes` 緩衝自癒變更，僅在驗證無 `FAIL` 時原子落盤。

---

## 3. 開放議題與確認紀錄

- 全部 `WF-AUD-01` ~ `WF-AUD-13`、`ARCH-AW-01~12`、`ARCH-GD-01~14` 與 Surgery `S6` 規格均已確認定案並完成實作驗證。
