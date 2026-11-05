# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_05_0104_codebase_deep_audit_remediation  
> 建立日期：2026-11-05  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：基於《全倉八維度單點序列深度審計與盲眼反向查驗報告》（`R01_codebase_deep_audit.md`），以零回歸副作用、100% 行為等價與正交分區原則，扣除本地前置計畫（`2026_11_04_1739_sys_path_and_five_semantic_spaces` 與 `2026_11_05_0528_gdrive_changes_api_and_lock_preemption`）已修畢之 6 項（`U1-P1-03`、`U1-P2-03`、`U2-P1-02`/`[TODO-22]`、`U3-P2-03`、`DEV-02`、`AW-03`）後，分批完成剩餘 61 項有效問題之結構加固與問題修復，重點確保新模組 `gdrive-support` 與 `vscode-support` 達到生產級高可靠標準。
- **架構邊界**：
  1. 嚴格按模組實體目錄切分為 4 個互不重疊的正交子計畫（`sub_01` ～ `sub_04`），支援最多 4 路 Agent 平行或序列推進，杜絕跨子計畫爭搶同一模組檔案。
  2. 強制遵守 `R01_codebase_deep_audit.md` §2 所確立的 **8 大防回歸修復紅線（Anti-Regression Guardrails）**，且所有修改僅在 `ys_codebase/source/` 與 `yscb.py` 進行（嚴禁直接手改 `.modules/`、`.yscb_gdrive.json` 或 `.history/`）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_gdrive_and_vscode_support` | Full Track | `Completed` | **重點關注新模組修復（扣除 `U1-P1-03`、`U1-P2-03`、`U2-P1-02`/`[TODO-22]` 已修畢項後，剩餘 `gdrive-support` 11 項 + `vscode-support` 4 項）**：收斂 `U1-P0-01`（單向 `pull`/`push` 略過對向修改時保護 `sync_state.json` 基準線）、`U1-P0-02`（`sync_spaces` 為空阻斷保護與 `contribute.json`）、`U1-P0-03`（`coordinator.py:L1700, L2058, L2136` 之 `SYSTEM_NAMES` 誤濾分支根目錄 `README.md`）、`U1-P1-04`（CLI `--sandbox-dir` 狀態與組態隔離）、`U1-P1-01`（`_folder_cache` 執行緒鎖與 `_precreate_remote_dirs` 依深度 BFS 平行化 `[TODO-23]`）、`U1-P1-02`/`U1-P2-02`/`U1-P2-04`（遠端空父目錄清理）/`U1-P1-05`/`U1-P3-01`~`02`，以及 `U2-P1-01`（`on_remove` Fail-Closed 守衛）、`U2-P2-01`~`02`/`U2-P3-01`。 |
| **sub_02** | `sub_02_host_and_core_microkernel` | Full Track | `Completed` | **宿主與微內核底座加固（扣除 `U3-P2-03` 已修畢後，剩餘 `yscb.py` + `module:core` 13 項 + `DEV-01` 根源 TLS 化）**：將 `core/uri.py` 全域 `_active_host_dir`/`_active_yscb_dir`/`_active_module_context`/`_reconciling_tokens` 遷移至 `threading.local()`（從根源消除 `DEV-01` 多執行緒沙盒競態）；修復 `U3-P0-01`（子路徑 `rel` 逃逸與 Windows 磁碟機重置攔截、`VFS.open` 安全守衛與 `newline`）、`U3-P0-02`（Localhost IPC `ProxyHandler({})` 與 `URLError` 重置判定）、`U3-P1-02`（對齊 `yscb.host://yscb.config.json` `[DN-03]`）、`U3-P1-03`（`act_snapshot` 清理舊快照與 `cmd_rollback` 時間排序）及 `U3-P1-01`/`U3-P1-04`~`06`/`U3-P2-01`~`02`/`U3-P2-04`/`U3-P3-01`~`02`。 |
| **sub_03** | `sub_03_server_dev_and_workflow` | Full Track | `Completed` | **常駐服務、開發工具鏈與工作流引擎修復（扣除 `DEV-02` 與 `AW-03` 已修畢後，剩餘 `server` 6 項 + `dev` 3 項 + `agents-workflow` 5 項）**：修復 `SRV-01`（`_read_handshake` 非 JSON 雜訊行容錯防死鎖）、`SRV-02`（`with streamer:` 結束前寫入異常並傳遞 `error=`）、`SRV-03`（Windows Worker `PYTHONIOENCODING=utf-8`）、`SRV-04`~`06`；`DEV-01`（沙盒建置配合 `core.uri` TLS）、`DEV-03`~`05`（環境變數差集還原、接線 `run_subprocess_with_tree_timeout`、`_check_custom_rules` 正規化）；`AW-02`（補回 `workflow -> skill` 轉譯對齊 `[DN-AW-05]`）、`AW-04`（`promote_todos` 寫入順序與 `verifier.py` `resolve_phase_file`）及 `AW-01`/`AW-05`/`AW-06`（嚴守 `dev.checker` 禁止非 `core` 模組變動 `sys.path` 之新 AST 守門）。 |
| **sub_04** | `sub_04_knowledge_pipeline` | Full Track | `Completed` | **三階知識檢索管線修復（`file-space` 6 項 + `ast` 6 項 + `knowledge-db` 6 項）**：修復 `FS-01`（`.watcher_dirty` 與 `_diff_all_spaces` 世代聚合）、`FS-02`（`follow_symlinks` 邏輯路徑與 `st_ino != 0`）、`FS-03`（帶沙盒隔離守衛之專案空間覆寫）、`FS-04`~`06`；`AST-01`（兼顧 `[DN-06]` 之根目錄單檔絕對路徑匹配與 `_resolve_dirty_files_only` `best_mtime_ns` 消歧）、`AST-02`（修正 `use_parallel` 恆 `False` 恢復 `ProcessPoolExecutor`）、`AST-03`（冷啟動全空間 `build_index(spaces=None)` 與 `_cursor_already_consumed=True`）、`AST-04`~`06`；`KDB-01`（`KnowledgeDBServiceWorker` 冷啟動先呼叫 `_ensure_indices_loaded` 恢復 `[DN-30]` 水位線自癒）、`KDB-02`（補齊 `_kdb_index_file_lock`）、`KDB-03`（統一 `Path.suffix` 且保留 RRF 分數尺度）及 `KDB-04`~`06`。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0（全倉八維度深潛與盲眼反向查驗定錨）**：完成 `Unit 01` ～ `Unit 09` 雙輪審計與爆炸半徑校準，固化 `R01_codebase_deep_audit.md` 與 `P00_discuss.md`。
- [x] **里程碑 1（`sub_01` 新模組 `gdrive-support` & `vscode-support` 收斂）**：完成 `U1-P0-01`、`U1-P1-04`、`U2-P1-02` (`[TODO-22]`)、`U1-P1-01` (`[TODO-23]`) 等 15 項修復並通過沙盒單元測試。
- [x] **里程碑 2（`sub_02` 宿主 `yscb.py` & 微內核 `core` 加固）**：完成 `core.uri` 執行緒本地化（根治 `DEV-01`）、`U3-P0-01`、`U3-P0-02`、`U3-P1-02`、`U3-P1-03` 等 14 項修復並通過沙盒單元測試。
- [x] **里程碑 3（`sub_03` 常駐服務 `server`、工具鏈 `dev` 與 `agents-workflow` 修復）**：完成 `SRV-01`～`03`、`DEV-02`～`05`、`AW-02`～`04` 等 16 項修復並通過沙盒單元測試。
- [x] **里程碑 4（`sub_04` 三階知識檢索管線 `file-space`、`ast`、`knowledge-db` 修復）**：完成 `AST-01`～`03`、`KDB-01`～`02`、`FS-01`～`03` 等 18 項修復並通過全倉 `dev check --all` 與 `dev test --all` 驗收。
