# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_gdrive_deep_hardening  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 增量快取 `deepcopy` 隔離與 `page_token` 延遲提交 | `_try_incremental_remote_cache` 必須在獨立副本上運算，若中途回退 `None` 絕不污染 `state["remote_repo_cache"]`；`changes.list` 取得之 `new_token` 僅在 Stage 3 所有推送、拉取與刪除皆無錯完成且未發生 `yielded` 時，才提交至 `state["remote_repo_cache"]["page_token"]`。 | P0 | [P00:DR-01] |
| **FR-02** | 頂層 `README.md` 同步狀態感知 `repo_sync_root` 變更 | `reconcile_root_readme_state` 同時追蹤 `enable` 與 `repo_sync_root`，當根目錄名稱變更時自動更新頂層 `README.md` 受管區塊，並向下相容既有布林值狀態快取。 | P1 | [P00:DR-01] |
| **FR-03** | 沙盒執行緒安全、目錄搬移完整性與 Shortcut 覆寫清理 | `LocalSandboxTransport.list_files` 全程持鎖；`move_file` 支援目錄連同子項目 `rel_path` 完整遷移且不誤嵌目標子層；`upload_file` 覆寫同路徑實體檔時清理殘留之舊 Shortcut 項目。 | P0 | [P00:DR-02] |
| **FR-04** | 雲端 `in_place_file_id` 404 自動自癒、HTTP 指數退避與連線池釋放 | `GoogleDriveApiTransport.upload_file` 遭遇 `in_place_file_id` HTTP 404（`GDriveFileNotFoundError`）時自動清除快取並退回 `POST` 新建；`_request_json` 網路異常重試執行指數退避並提供 `close()` 清理執行緒本地連線；`SyncCoordinator` 平行傳輸池將 `except BaseException:` 收緊為 `except Exception:` 並於首錯時取消 pending futures。 | P0 | [P00:DR-02] |
| **FR-05** | 符合 `CodeQualityStandards.md` (`D1`~`D5`, `S1`~`S6`) 無損結構重構与多輪盲審收斂 | 封裝 `_PushTask`、`_PullTask`、`_RemoteStageSnapshot`、`_IncrementalPatchContext` (`S5`)；拆解 `run_sync`、`_try_incremental_remote_cache`、`reconcile_three_way` 為扁平階段函式 (`S1`, `S4`)；移除 1 行轉發殼並提煉模組級純函式 (`S2`)；收斂 `cli.py` 重複樣板 (`S3`)；對齊 `manifest.json`、`SKILL.md` 與 `contributes/_manifest.md` (`D5`)，達成全新盲眼審查 `MAJOR_ISSUES_COUNT: 0`。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Stage 1 Level 1 增量快取中途遇到目錄重新命名或未知父目錄而回退 Level 2 | 因在 `deepcopy` 副本上操作，原始 `state["remote_repo_cache"]` 保持 100% 未修改狀態，安全回退至 Level 2 全量掃描。 |
| **EC-02** | Stage 3 執行平行推送或拉取時中途拋出 `GDriveTransportError` 或發生 `yielded=True` | `finally` 區塊拒絕將 `pending_page_token` 寫入 `cache["page_token"]`，保留舊 `page_token` 確保下次同步不會漏失未完成之雲端變更。 |
| **EC-03** | 雲端既有檔案被外部手動永久刪除後，本地執行 `PUSH_UPDATE` 傳入舊 `in_place_file_id` | `GoogleDriveApiTransport.upload_file` 捕獲 `GDriveFileNotFoundError` (HTTP 404)，清除路徑快取並自動退回 `POST` 新建上傳，不中斷同步。 |
| **EC-04** | 舊版 `readme_sync_state.json` 儲存布林值 `true` 且當前 `repo_sync_root == "repo"` | `_extract_cached_readme_state` 自動將舊版布林值映射為 `(True, "repo")`，判定 `noop_cached` 不觸發冗餘雲端讀寫。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 程式碼品質與潔癖 | 100% 符合 `CodeQualityStandards.md`（生產與測試代碼 0 工單編號殘留、核心函式業務階段垂直對齊、縮排 $\le 3$ 層、零無狀態 1 行轉發殼）。 |
| **NFR-02** | 盲眼審查收斂門檻 | 全新盲眼審查子代理回報 `MAJOR_ISSUES_COUNT: 0` 與 `REVIEW_STATUS: PASSED`，且 `dev check gdrive-support` 與 `dev test gdrive-support -q --sync` 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開匯出相容性（`REPO_SYNC_ROOT_PREFIX`）**：`gdrive_support/__init__.py` 於 `__all__` 公開匯出 `REPO_SYNC_ROOT_PREFIX`，因此在 `coordinator.py` 必須保留 `REPO_SYNC_ROOT_PREFIX = DEFAULT_REPO_SYNC_ROOT` 作為向後相容公開常數。
- **`[!CAUTION]` 零工單與審計編號殘留（`D2`）**：生產代碼與測試註解嚴禁留下 `FR-XX`、`EC-XX`、`R1-XX`、`FT-XX` 等單次開發編號，所有註解必須轉化為自包含的領域不變量說明。
