# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_gdrive_deep_hardening  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：對 `gdrive-support` 進行詳細排查，特例授權開啟 `sub_05` 允許多次返工並執行優化閉環步驟：（1）派送全新盲眼審查子代理對 `gdrive-support` 進行審查（除了查問題，還要查 `ys_codebase/source/agents-workflow/assets/standards/CodeQualityStandards.md`）；（2）針對子代理提出之問題返項驗證真實性後進行修復；（3）回到步驟（1）直到盲眼審查子代理回報之問題無重大發現僅剩細微優化，或是完成第三輪閉環時熔斷。
- **核心目標**：消除 `ys_codebase/source/gdrive-support/` 所有潛藏之快取一致性、執行緒與沙盒競態、錯誤退避與狀態機缺陷，並全面對齊 `CodeQualityStandards.md` 之五大衛生診斷維度（`D1`~`D5`）與六大結構潔癖重構原則（`S1`~`S6`）。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `gdrive-support` 既有三方對帳引擎（`reconciler.py`）、雙傳輸層（`LocalSandboxTransport` / `GoogleDriveApiTransport`）、`SyncCoordinator` 與 `YSCBTestCase` 測試沙盒。
- **邊界排除 (Explicitly Excluded)**：寫入範圍嚴格鎖定於 `ys_codebase/source/gdrive-support/` 與本計畫目錄，不觸碰其他模組源碼，且嚴禁直接修改 `.modules/` 運行空間。
- **架構影響範圍**：`ys_codebase/source/gdrive-support/`（`gdrive_support/`、`scripts/`、`contributes/`、`manifest.json`、`assets/`、`tests/`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `gdrive-support` 增量快取原子交易、`page_token` 延遲提交与頂層 `README.md` 狀態追蹤**：
  1. `_try_incremental_remote_cache` 內部一律在 `copy.deepcopy` 副本（`_IncrementalPatchContext`）上運算，若遇不支援之目錄結構變更回退 `None` 至 Level 2，確保原始 `state["remote_repo_cache"]` 100% 不受半套修改污染。
  2. 將 `changes.list` 取得之 `pending_page_token` 延遲至 Stage 3（`_execute_stage3_reconciliation` 之 `finally` 區塊）所有推送、拉取與刪除皆無錯完成且未發生 `yielded` 讓位時才提交至 `remote_repo_cache["page_token"]`。
  3. `reconcile_root_readme_state` 擴充追蹤 `{"enable": curr_enabled, "repo_sync_root": curr_root}`，當 `repo_sync_root` 變更時自動刷新頂層 `README.md` 受管區塊，並向下相容舊版 `bool` 狀態紀錄。
- **[P00:DR-02] 傳輸層執行緒安全、沙盒目錄搬移對稱性與雲端 `in_place_file_id` 404 自癒**：
  1. `LocalSandboxTransport.list_files` 全程置於 `with self._lock:` 保護下；`move_file` 搬移目錄時同步重寫所有子項目之 `rel_path` 前綴並安全替換已存在之目標路徑；`upload_file` 覆寫同路徑時自動清理殘留之舊 Shortcut 項目。
  2. `GoogleDriveApiTransport.upload_file` 指定 `in_place_file_id` 遭遇 HTTP 404（`GDriveFileNotFoundError`）時，自動清除快取並退回 `POST` multipart 新建；`_request_json` 網路異常重試補齊指數退避 `time.sleep(backoff)`，並新增 `close()` 釋放執行緒本地 `HTTPSConnection`。
  3. `SyncCoordinator` 平行傳輸池迴圈將 `except BaseException:` 收緊為 `except Exception:`，遇錯時立即取消未執行之 `pending` futures。
- **[P00:DR-03] 對齊 `CodeQualityStandards.md`（`D1`~`D5`, `S1`~`S6`）結構重構與多輪盲眼審查收斂**：
  1. 依 `S1`/`S4` 將 `reconcile_three_way`、`run_sync` 與 `_try_incremental_remote_cache` 拆解為職責單一、縮排 $\le 3$ 層之階段函式。
  2. 依 `S2` 移除 1 行轉發殼 `_trash_repo_item` 與 `_collect_remote_branch_snapshot`，將 `_create_conflict_backup` 與 `_parse_rfc3339_ns` 提煉為模組級純函式。
  3. 依 `S3`/`S5` 封裝 `_PushTask`、`_PullTask`、`_RemoteStageSnapshot`、`_IncrementalPatchContext` 資料類別，收斂 `scripts/cli.py` 重複樣板，並確保全模組生產與測試代碼 0 工單編號註解殘留。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：開發者已特例授權開啟 `sub_05` 進行多輪盲眼審查與修復閉環；Round 1 盲眼審查（`1b0b81c1-dead-407c-b84f-bdac0c1bebe1`）檢出之 11 項重大問題與 5 項細微打磨已全數驗證修復，Round 2 全新盲眼審查子代理（`65ed919e-b89c-4086-b3a2-ead45da3cb4f`）已確認 `MAJOR_ISSUES_COUNT: 0`、`REVIEW_STATUS: PASSED`（僅剩 3 項細微打磨亦已全數收斂）。

