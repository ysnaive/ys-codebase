# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_09_gdrive_support 同步刪除邊界防護、空目錄清理條件收斂與 WAL 狀態持久化優化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 單向 `--delete` 基線保護 (`[TODO-24]`) | 於 `reconciler.py` 之 `_reconcile_remote_only` 與 `_reconcile_local_only` 中，當 `base is None` 時，單向 `push --delete`（含 `push_delete_default=True`）與 `pull --delete`（含 `pull_delete_default=True`）預設回傳 `SKIP`（`remote_new_untracked_on_push` / `local_new_untracked_on_pull`），唯有同時顯式傳入 `force=True` 時方才執行未追蹤檔案刪除；而當 `base is not None`（已知追蹤檔案於單側被刪）時維持 `delete=True` 正常刪除。 | P0 | [P00:DR-01] |
| **FR-02** | 空目錄清理收斂與還原目錄子樹掃描 (`[TODO-25]`) | 於 `coordinator.py` 之 `_prune_empty_remote_branch_dirs` 移除將全量 `rel_to_dir_fids` 加入 `candidate_dirs` 之無差別邏輯，僅針對當輪 `deleted_remote_paths` 之各級父目錄檢查並清理空目錄，且 `run_sync` 僅於 `bool(report.deleted_remote)` 為真時呼叫；於 `_apply_incremental_folder_changes` 當分支內出現原先不在 `dir_fid_to_rel` 之新建或垃圾桶還原目錄時，回傳 `None` 降級至 Level 2 分支樹掃描，確保其既有子檔案完整入列。 | P0 | [P00:DR-02] |
| **FR-03** | `sync_state.json` + `sync_state.journal.jsonl` WAL 狀態持久化 | 於 `RepoSyncCoordinator` 新增 `self.state_journal_path`（`sync_state.journal.jsonl`）：在 Stage 3 單檔同步與批次傳輸迴圈中，以 `_checkpoint_local_state(state)` 將單檔變更追加寫入 `sync_state.journal.jsonl`（O(1) 行追加），於 `_execute_stage3_reconciliation` 的 `finally` 區塊統一呼叫 `_save_local_state(state)` 原子落盤並清除 journal；`_load_local_state()` 若偵測到未結算之 `sync_state.journal.jsonl` 則自動按序 Replay 合併並收斂。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 同步批次進行至中途時進程異常終止（`SIGKILL` / 斷電），殘留未結算之 `sync_state.journal.jsonl`（最後一行可能因斷電而截斷損毀） | 下次 `_load_local_state()` 自動逐行解析 `sync_state.journal.jsonl`，安全忽略末尾截斷之非法 JSON 行，將所有完整之單檔基線與快取變更 Replay 合併至 `state` 並立即收斂寫回 `sync_state.json`。 |
| **EC-02** | 雲端將整個含有子目錄與子檔案之資料夾自垃圾桶還原（Google Drive `changes.list` 僅發出該資料夾本身 `trashed=false` 變更） | `_apply_incremental_folder_changes` 偵測到該資料夾先前不在快取之 `dir_fid_to_rel` 中，立即回傳 `None` 觸發 Level 2 分支掃描，完整找回資料夾下所有子檔案。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與原子性 | N 個檔案之 `pull`/`push` 批次期間，全量 `sync_state.json` 重寫次數由 $O(N)$ 降至 $1$ 次（Stage 3 `finally` 收斂），同時保持 100% 逐檔 Crash Recovery 原子性。 |
| **NFR-02** | 向下相容性 | 對外 CLI 與 `sync_state.json` 結構維持 100% 相容，全模組單元與合約測試 100% 通過且 `0 ResourceWarning`。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `_save_local_state(state)` 一旦完成完整 `sync_state.json` 原子覆寫，必須立即 `unlink(missing_ok=True)` 移除 `sync_state.journal.jsonl`，防止舊 journal 在後續啟動時覆蓋更新後的狀態。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Stage 1/2 Load] _load_local_state()
   ├── Read sync_state.json
   └── If sync_state.journal.jsonl exists -> Replay records into state -> _save_local_state() & unlink journal

[Stage 3 Execution] _execute_stage3_reconciliation()
   ├── Immediate actions / _execute_push_batch / _execute_pull_batch
   │     └── Per file completed -> _append_state_journal(...) [Append 1 JSONL line + flush]
   ├── If report.deleted_remote -> _prune_empty_remote_branch_dirs(deleted_remote_paths)
   └── finally: _save_local_state(state) [Single atomic write + unlink journal]
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/gdrive_support/reconciler.py` | Modify | 修正 `_reconcile_local_only` 與 `_reconcile_remote_only` 在 `base is None` 時單向 `--delete` 需同時具備 `force=True` 才刪除未追蹤新檔 |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 修正 `_prune_empty_remote_branch_dirs` 僅掃描 `deleted_remote` 父目錄鏈、修正 `_apply_incremental_folder_changes` 對新/還原目錄觸發 Level 2 掃描，並實作 `sync_state.journal.jsonl` WAL 追加與 Replay |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 更新並新增 `base is None` 單向 `--delete` 保護、新建空目錄不誤刪、還原目錄子檔案掃描與 WAL Journal Crash Replay 單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] WAL Journal 記錄粒度**：Journal 每行記錄單一檔案在 `branches[branch][rel_path]` 與 `remote_repo_cache` 內之增量更新或刪除（`op="upsert_file" | "delete_file"`），兼顧極小單行體積（~300B）與無損 Replay。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
class RepoSyncCoordinator:
    state_journal_path: Path

    def _append_state_journal(self, record: Dict[str, Any]) -> None: ...
    def _replay_state_journal(self, state: Dict[str, Any]) -> bool: ...
    def _record_branch_file_upsert(
        self,
        state: Dict[str, Any],
        branch: str,
        rel_path: str,
        base_entry_dict: Dict[str, Any],
        cache_entry: Optional[RemoteEntry] = None,
    ) -> None: ...
    def _record_branch_file_delete(
        self,
        state: Dict[str, Any],
        branch: str,
        rel_path: str,
        remove_from_cache: bool = False,
    ) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：Journal 讀寫遭遇單行截斷損毀時安全略過該損毀行，不拋出未捕獲例外中斷啟動。
- **階段決策紀錄**：`[P03:DR-01]` `_save_local_state(state)` 寫入 `sync_state.json` 後統一清理 `self.state_journal_path`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-03 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-02 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若外部測試或舊程式碼在 Stage 3 中透過 `unittest.mock.patch.object(coord, "_save_local_state")` 驗證單檔寫盤行為或模擬中斷異常，改用 Journal 後是否相容？*
  - *答*：我們保留 `_save_local_state` 為最終快照入口，並檢查既有測試對 `_save_local_state` 的調用預期，確保既有測試與新增 WAL Replay 測試 100% 協同通過。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | N/A | CLI 語法無變更 |
| **專題手冊** | `docs/gdrive-support/[topic].md` | N/A | 內部狀態持久化與對帳邊界修正 |
| **設計決策** | `docs/gdrive-support/DESIGN_NOTES.md` | N/A | 無新增反直覺妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `reconciler.py` 與 `coordinator.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 結案時記錄發布摘要 |

- **決策定稿**：**[P04:DR-01]** 規格通過 `Pre-Code Analyze Gate` 內聯核驗，進入實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `reconciler.py` 實作 `FR-01`（`base is None` 時單向 `push/pull --delete` 保護未追蹤新檔，僅 `force=True` 時強制刪除）
- [x] **TASK-02**：於 `coordinator.py` 實作 `FR-02`（`_prune_empty_remote_branch_dirs` 僅掃描 `deleted_remote` 父目錄鏈 + `_apply_incremental_folder_changes` 對新建/還原目錄觸發 Level 2 分支樹掃描）
- [x] **TASK-03**：於 `coordinator.py` 實作 `FR-03`（`sync_state.journal.jsonl` WAL 逐檔追加、啟動自動 Replay 與 Stage 3 `finally` 單次原子收斂）
- [x] **TASK-04**：更新並新增 `tests/test_branch_and_sync_engine.py` 單元測試，通過 `dev check` 與 `dev test` 100% 驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
