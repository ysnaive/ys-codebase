# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_05_gdrive_deep_hardening  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

> 本子計畫之 P01 需求規格已於 [`P01_requirements_spec.md`](./P01_requirements_spec.md) 獨立確認定案；以下對齊摘要供跨階段追溯：

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 增量快取 `deepcopy` 隔離與 `page_token` 延遲提交 | `_try_incremental_remote_cache` 必須在獨立副本上運算，若中途回退 `None` 絕不污染 `state["remote_repo_cache"]`；`changes.list` 取得之 `new_token` 僅在 Stage 3 所有推送、拉取與刪除皆無錯完成且未發生 `yielded` 時，才提交至 `state["remote_repo_cache"]["page_token"]`。 | P0 | [P00:DR-01] |
| **FR-02** | 頂層 `README.md` 同步狀態感知 `repo_sync_root` 變更 | `reconcile_root_readme_state` 同時追蹤 `enable` 與 `repo_sync_root`，當根目錄名稱變更時自動更新頂層 `README.md` 受管區塊，並向下相容既有布林值狀態快取。 | P1 | [P00:DR-01] |
| **FR-03** | 沙盒執行緒安全、目錄搬移完整性與 Shortcut 覆寫清理 | `LocalSandboxTransport.list_files` 全程持鎖；`move_file` 支援目錄連同子項目 `rel_path` 完整遷移且不誤嵌目標子層；`upload_file` 覆寫同路徑實體檔時清理殘留之舊 Shortcut 項目。 | P0 | [P00:DR-02] |
| **FR-04** | 雲端 `in_place_file_id` 404 自動自癒、HTTP 指數退避與連線池釋放 | `GoogleDriveApiTransport.upload_file` 遭遇 `in_place_file_id` HTTP 404（`GDriveFileNotFoundError`）時自動清除快取並退回 `POST` 新建；`_request_json` 網路異常重試執行指數退避並提供 `close()` 清理執行緒本地連線；`SyncCoordinator` 平行傳輸池將 `except BaseException:` 收緊為 `except Exception:` 並於首錯時取消 pending futures。 | P0 | [P00:DR-02] |
| **FR-05** | 符合 `CodeQualityStandards.md` (`D1`~`D5`, `S1`~`S6`) 無損結構重構與多輪盲審收斂 | 封裝 `_PushTask`、`_PullTask`、`_RemoteStageSnapshot`、`_IncrementalPatchContext` (`S5`)；拆解 `run_sync`、`_try_incremental_remote_cache`、`reconcile_three_way` 為扁平階段函式 (`S1`, `S4`)；移除 1 行轉發殼並提煉模組級純函式 (`S2`)；收斂 `cli.py` 重複樣板 (`S3`)；對齊 `manifest.json`、`SKILL.md` 與 `contributes/_manifest.md` (`D5`)，達成全新盲眼審查 `MAJOR_ISSUES_COUNT: 0`。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Stage 1 Level 1 增量快取中途遇到目錄重新命名或未知父目錄而回退 Level 2 | 因在 `deepcopy` 副本上操作，原始 `state["remote_repo_cache"]` 保持 100% 未修改狀態，安全回退至 Level 2 全量掃描。 |
| **EC-02** | Stage 3 執行平行推送或拉取時中途拋出 `GDriveTransportError` 或發生 `yielded=True` | `finally` 區塊拒絕將 `pending_page_token` 寫入 `cache["page_token"]`，保留舊 `page_token` 確保下次同步不會漏失未完成之雲端變更。 |
| **EC-03** | 雲端既有檔案被外部手動永久刪除後，本地執行 `PUSH_UPDATE` 傳入舊 `in_place_file_id` | `GoogleDriveApiTransport.upload_file` 捕獲 `GDriveFileNotFoundError` (HTTP 404)，清除路徑快取並自動退回 `POST` 新建上傳，不中斷同步。 |
| **EC-04** | 舊版 `readme_sync_state.json` 儲存布林值 `true` 且當前 `repo_sync_root == "repo"` | `_extract_cached_readme_state` 自動將舊版布林值映射為 `(True, "repo")`，判定 `noop_cached` 不觸發冗餘雲端讀寫。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 程式碼品質與潔癖 | 100% 符合 `CodeQualityStandards.md`（生產與測試代碼 0 工單編號殘留、核心函式業務階段垂直對齊、縮排 $\le 3$ 層、零無狀態 1 行轉發殼）。 |
| **NFR-02** | 盲眼審查收斂門檻 | 全新盲眼審查子代理回報 `MAJOR_ISSUES_COUNT: 0` 與 `REVIEW_STATUS: PASSED`，且 `dev check gdrive-support` 與 `dev test gdrive-support -q --sync` 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開匯出相容性（`REPO_SYNC_ROOT_PREFIX`）**：`gdrive_support/__init__.py` 於 `__all__` 公開匯出 `REPO_SYNC_ROOT_PREFIX`，因此在 `coordinator.py` 必須保留 `REPO_SYNC_ROOT_PREFIX = DEFAULT_REPO_SYNC_ROOT` 作為向後相容公開常數。
- **`[!CAUTION]` 零工單與審計編號殘留（`D2`）**：生產代碼與測試註解嚴禁留下 `FR-XX`、`EC-XX`、`R1-XX`、`FT-XX` 等單次開發編號，所有註解必須轉化為自包含的領域不變量說明。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[gdrive-support Deep Hardening Architecture]
  gdrive_support/reconciler.py
    └── reconcile_three_way()
          ├── _reconcile_both_present()
          ├── _reconcile_local_only()
          └── _reconcile_remote_only()
  gdrive_support/transport.py
    ├── _parse_rfc3339_ns() (模組級純函式)
    ├── LocalSandboxTransport
    │     ├── list_files() (全程受 self._lock 保護)
    │     ├── move_file() (支援資料夾子樹 rel_path 重寫與目標安全替換)
    │     └── upload_file() (覆寫同路徑時自動移除舊 Shortcut 條目)
    └── GoogleDriveApiTransport
          ├── close() / _clear_cached_token()
          ├── _request_json() (網路異常與 5xx 統一指數退避)
          └── upload_file() (in_place_file_id HTTP 404 自動退回 POST 新建)
  gdrive_support/coordinator.py
    ├── _PushTask / _PullTask / _RemoteStageSnapshot / _IncrementalPatchContext (@dataclass)
    ├── reconcile_root_readme_state() / _extract_cached_readme_state() (追蹤 enable + repo_sync_root)
    ├── run_sync()
    │     ├── _collect_remote_stage_snapshot()
    │     └── _execute_stage3_reconciliation()
    │           ├── _partition_and_run_immediate_actions()
    │           ├── _execute_push_batch() -> _upload_single_push_task()
    │           ├── _execute_pull_batch() -> _download_single_pull_task()
    │           └── finally: 僅當無錯誤且未 yielded 時提交 pending_page_token
    └── _try_incremental_remote_cache()
          ├── _build_incremental_patch_context() (基於 copy.deepcopy 隔離)
          ├── _classify_incremental_changes()
          ├── _apply_incremental_folder_changes()
          ├── _validate_incremental_file_changes()
          └── _apply_incremental_file_ops()
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/gdrive_support/reconciler.py` | Modify | 拆解 `reconcile_three_way` 為 `_reconcile_both_present`、`_reconcile_local_only`、`_reconcile_remote_only` 三個扁平階段函式（`S1`/`S4`） |
| `ys_codebase/source/gdrive-support/gdrive_support/transport.py` | Modify | 補齊 `LocalSandboxTransport.list_files` 執行緒鎖、目錄 `move_file` 子樹遷移、Shortcut 覆寫清理；新增 `GoogleDriveApiTransport.close()`、`_request_json` 網路異常指數退避、`upload_file` 404 自動退回 `POST`，並將 `_parse_rfc3339_ns` 提煉為模組級純函式（`S2`） |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 封裝 `_PushTask`、`_PullTask`、`_RemoteStageSnapshot`、`_IncrementalPatchContext`（`S5`）；實作 `_try_incremental_remote_cache` `deepcopy` 隔離與 `pending_page_token` 延遲提交；拆解 `run_sync` 與 `_try_incremental_remote_cache`（`S1`/`S4`）；移除 1 行轉發殼（`S2`）；收緊 `ThreadPoolExecutor` 例外捕獲並取消 pending futures（`D4`）；擴充 `reconcile_root_readme_state` 追蹤 `repo_sync_root` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 移除未使用之 `PurePosixPath` 匯入與工單編號註解（`D1`/`D2`） |
| `ys_codebase/source/gdrive-support/gdrive_support/service.py` | Modify | 清除歷史工單編號註解（`D2`） |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | 提煉 `_emit_error`、`_prepare_atomic_transport`、`_run_coordinator_action` 與 `_resolve_cfg_uri` 收斂 CLI 重複樣板（`S3`） |
| `ys_codebase/source/gdrive-support/scripts/migrations/1.0.1.x.py` | Modify | 收緊例外處理型別並清除工單編號註解（`D2`/`D4`） |
| `ys_codebase/source/gdrive-support/manifest.json` | Modify | 修正 `release.summary` 對齊實作架構（`D5`） |
| `ys_codebase/source/gdrive-support/contributes/_manifest.md` | Modify | 修正隨包外部雲端 AI 技能資產路徑說明（`D5`） |
| `ys_codebase/source/gdrive-support/assets/skills/gdrive-local-ops/SKILL.md` | Modify | 對齊雲端原生 30 天垃圾桶（`trashed=true`）與本地沙盒 `.trash/` 雙軌語意說明（`D5`） |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | 擴充 `upload_file` `in_place_file_id` 404 自動退回 `POST`、`close()` 與 `LocalSandboxTransport.move_file` 目錄搬移測試 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 擴充 `_try_incremental_remote_cache` 回退時零原地污染、Stage 3 失敗不提前推進 `page_token`、`reconcile_root_readme` 感知 `repo_sync_root` 變更測試，並清理測試註解中之歷史編號 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] Level 1 增量快取 Copy-on-Write 與 `page_token` 兩階段提交**：`_try_incremental_remote_cache` 先透過 `_build_incremental_patch_context` 建立 `cache_branches`、`folder_meta` 與 `known_folder_ids` 的深拷貝工作區，並以 `pending_page_token` 傳遞新游標，僅在 `_execute_stage3_reconciliation` 正常完成（`not report.yielded and first_push_err is None and first_pull_err is None`）時才將 `pending_page_token` 寫入 `state["remote_repo_cache"]["page_token"]`。
- **[P02:DR-02] 遵循 `CodeQualityStandards.md` 階段垂直拆解與資料結構封裝**：以 `@dataclass(frozen=True)` `_PushTask` 與 `_PullTask` 取代原先 8 元組與 4 元組裸 Tuple，消除索引解包脆弱性；並將長函式按業務階段垂直拆解為同層私有輔助方法。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/gdrive-support/gdrive_support/transport.py
def _parse_rfc3339_ns(ts_str: str) -> int: ...

class GoogleDriveApiTransport(AbstractSyncTransport):
    def close(self) -> None: ...
    def _clear_cached_token(self) -> None: ...

# ys_codebase/source/gdrive-support/gdrive_support/coordinator.py
def _create_conflict_backup(local_path: Path) -> Path: ...
def _extract_cached_readme_state(raw_entry: Any) -> Tuple[Optional[bool], Optional[str]]: ...

@dataclass(frozen=True)
class _PushTask: ...

@dataclass(frozen=True)
class _PullTask: ...

@dataclass
class _RemoteStageSnapshot: ...

@dataclass
class _IncrementalPatchContext: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `GoogleDriveApiTransport.upload_file(..., in_place_file_id=...)`：當遠端目標檔案因外部刪除回傳 HTTP 404（`GDriveFileNotFoundError`）時，自動清除快取並退回 `POST` multipart 建立新檔案。
  - `SyncCoordinator._execute_push_batch` / `_execute_pull_batch`：僅捕獲 `Exception`（絕不吞沒 `KeyboardInterrupt` / `SystemExit`），並在首個錯誤發生時立即呼叫 `fut.cancel()` 取消未啟動任務。
- **階段決策紀錄**：`[P03:DR-01]` 保留 `REPO_SYNC_ROOT_PREFIX = DEFAULT_REPO_SYNC_ROOT` 公開匯出常數，確保外部模組匯入契約 100% 不變。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束與 `CodeQualityStandards.md`
- **靈魂拷問與防護解法**：
  1. *若 Stage 1 命中 Level 1 快取修補寫入了 `state["remote_repo_cache"]["branches"]`，但 Stage 3 中途拋出網路錯誤，下次重跑 `run_sync` 時會發生什麼？*
     - 防護解法：因為 `page_token` 延遲至 Stage 3 成功後才提交，若 Stage 3 拋錯，`cache["page_token"]` 仍維持舊 token，下次 `run_sync` 會重新從舊 `page_token` 拉取變更並冪等重放修補，不會遺漏任何未完成拉取之遠端變更。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | N/A | 內部快取交易化與代碼品質重構，不影響頂層概覽 |
| **專題手冊** | `docs/gdrive-support/[topic].md` | N/A | 無新增獨立專題手冊 |
| **設計決策** | `docs/gdrive-support/DESIGN_NOTES.md` | N/A | 無新增反直覺工程妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 全面清理單次工單編號並補齊自包含領域說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於根目錄 `CHANGELOG.md` 同步記錄 `sub_05` 深度加固成果 |

- **決策定稿**：**[P04:DR-01]** 確認 Round 1 與 Round 2 盲眼審查回饋皆已收斂完畢。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Round 1 盲眼審查 11 項 `[CRITICAL / MAJOR]` 與 5 項 `[MINOR / POLISH]` 返項驗證與源碼修復（`reconciler.py`、`transport.py`、`coordinator.py`、`config.py`、`service.py`、`scripts/cli.py`、`scripts/migrations/1.0.1.x.py`、`manifest.json`、`SKILL.md`）
- [x] **TASK-02**：於 `tests/test_atomic_api_and_config.py` 與 `tests/test_branch_and_sync_engine.py` 擴充回歸測試並通過 `dev check` 與 `dev test`（33/33 Pass）
- [x] **TASK-03**：派送 Round 2 全新盲眼審查子代理（`65ed919e-b89c-4086-b3a2-ead45da3cb4f`），確認 `MAJOR_ISSUES_COUNT: 0`、`REVIEW_STATUS: PASSED`，並收斂 Round 2 提出之 3 項細微打磨（`contributes/_manifest.md`、`transport.py` Shortcut 覆寫清理、`coordinator.py`、`cli.py`、`tests/test_branch_and_sync_engine.py`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

