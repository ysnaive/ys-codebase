# 測試與驗證計畫 (Test & Verification Plan)

> 功能名稱：sub_02_composite_capabilities  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 測試基準：[P01-05_auto.md](./P01-05_auto.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

### 1.1 功能測試 (Functional Tests - 對齊 FR)

| 測試編號 | 測試目標 / 情境描述 | 對應 FR | 測試類型 (Unit/Integration/E2E) | 驗證方式 / 測試指令 |
| :--- | :--- | :---: | :---: | :--- |
| **FT-01** | 驗證 `SpaceDef.entries` 選填與 `compose` 擴充及 `bool(entries) or bool(compose)` 聯合校驗 | FR-01 | Unit | `python yscb.py dev test core -k test_compose_algebra_secondary_filtering_and_cycle_detection` |
| **FT-02** | 驗證 `compose` 組合代數、保留子空間 `entry_path` 之父空間二次過濾（`exclude` 全體剔除 + 顯式 `include` 交集）與 `match_path` 溯源 | FR-02 | Unit | `python yscb.py dev test core -k test_compose_algebra_secondary_filtering_and_cycle_detection` |
| **FT-03** | 驗證 `resolve_file_path` 導航反解與 `define_ephemeral_space` 執行期動態空間掛載及記憶體隔離 | FR-03 | Unit | `python yscb.py dev test core -k test_resolve_file_path_and_ephemeral_space_memory_isolation` |
| **FT-04** | 驗證 `YFP2` 單調世代二進位快照 (`BinarySnapshotManager`)、雙階段增量掃描 (`SpaceScanner.scan`/`refresh`)、`patch_files` 局部刷新與 `merkle_root` 確定性 | FR-04 | Unit / Integration | `python yscb.py dev test core -k test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors` |
| **FT-05** | 驗證 `CursorStore` 多消費者獨立水位游標與 `consume_diff` At-Least-Once 交易推進 | FR-05 | Unit / Integration | `python yscb.py dev test core -k test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors` |
| **FT-06** | 驗證 `core file-space` 與 `fs` 之 `status`、`scan`、`diff [--consumer] [--ack]`、`clean [--consumer]` 及 `ls --pattern` CLI 子命令 | FR-06 | Integration | `python yscb.py dev test core -k test_composite_cli_status_scan_diff_clean` |

### 1.2 邊界與異常測試 (Edge Cases & Failure Mode Tests - 對齊 EC)

| 測試編號 | 邊界 / 異常情境描述 | 對應 EC | 預期攔截行為 / 錯誤碼 | 驗證方式 / 測試指令 |
| :--- | :--- | :---: | :--- | :--- |
| **ET-01** | `compose` 拓撲存在自我引用 (`A -> A`) 或間接循環 (`A -> B -> A`) | EC-01 | 立即拋出 `SpaceCycleError`（繼承自 `SpaceError`），拒絕遞迴展開 | `python yscb.py dev test core -k test_compose_algebra_secondary_filtering_and_cycle_detection` |
| **ET-02** | 空間定義同時缺少 `entries` 與 `compose`（兩者皆為空） | EC-02 | 拋出 `SpaceError` 拒絕無效空殼空間定義 | `python yscb.py dev test core -k test_compose_algebra_secondary_filtering_and_cycle_detection` |
| **ET-03** | `is_ephemeral=True` 動態空間執行 `scan`/`diff`/`ack` 時之持久化隔離 | EC-03 | 快照與游標完全隔離於記憶體字典，磁碟 `snapshots/` 與 `cursors/` 零殘留 | `python yscb.py dev test core -k test_resolve_file_path_and_ephemeral_space_memory_isolation` |
| **ET-04** | 快照二進位檔損毀或 Magic Header 非 `b"YFP2"` | EC-04 | `BinarySnapshotManager.load_state` 安全捕獲並回退為空 `SnapshotState(head_generation=0)` 自動重建 | `python yscb.py dev test core -k test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors` |
| **ET-05** | 空間規則、參與聯集之空間清單或 `compose` 展開子空間之 `config_hash` 變更 | EC-05 | 自動失效舊指紋快取、強制全量重算並推進 `head_generation` | `python yscb.py dev test core -k test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors` |
| **ET-06** | `consume_diff` 區塊內拋出例外，或消費者游標世代大於快照世代 (`acked_gen > head_gen`) | EC-06 | 例外時不執行 `ack` 保留原游標；游標超前時自動將基準重置為 `0` 觸發全量補償 | `python yscb.py dev test core -k test_yfp2_snapshot_scanner_patch_files_and_transactional_cursors` |

### 1.3 回歸與效能測試 (Regression & NFR Tests)

| 測試編號 | 驗證範圍 / 影響模組 | 預期標準 | 驗證方式 / 測試指令 |
| :--- | :--- | :--- | :--- |
| **RT-01** | `core` 模組全量單元與整合測試套件 + 合規檢查（涵蓋 NFR-01、NFR-02、NFR-03） | 滿足 NFR-01（零第三方依賴，僅用標準庫與 `core.vfs`/`core.space.hasher`）、NFR-02（`YFP2` + `RLock` + `InterProcessLock` 跨進程原子持久化）與 NFR-03（統一 `BLAKE2B_DIGEST_SIZE = 16` / 32-char hex）；`dev check core` 0 error / 0 warning；`dev test core` 100% 通過（266 Passed, 0 Failed） | `python yscb.py dev check core` 與 `python yscb.py dev test core -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 測試結果 (Passed/Failed) | 執行日期 | 備註 / 失敗原因與修復紀錄 |
| :--- | :---: | :---: | :--- |
| **FT-01** | Passed | 2026-11-07 | 通過 `SpaceDef` 選填 `entries` 與 `compose` Schema 校驗測試 |
| **FT-02** | Passed | 2026-11-07 | 通過 `compose` 聯集、二次過濾 `entry_path` 繼承與 `match_path` 溯源測試 |
| **FT-03** | Passed | 2026-11-07 | 通過 `resolve_file_path` 導航與 `define_ephemeral_space` 動態空間測試 |
| **FT-04** | Passed | 2026-11-07 | 通過 `YFP2` 快照、雙階段掃描、`patch_files`（含多空間刪除定址）與 `merkle_root` 測試 |
| **FT-05** | Passed | 2026-11-07 | 通過多消費者獨立水位游標與 `consume_diff` 交易推進測試 |
| **FT-06** | Passed | 2026-11-07 | 通過 `fs status/scan/diff/clean` 與複合空間 `ls --pattern` CLI 整合測試及實機 Smoke Test |
| **ET-01** | Passed | 2026-11-07 | 通過 `SpaceCycleError` 直接與間接循環引用攔截測試 |
| **ET-02** | Passed | 2026-11-07 | 通過 `entries` 與 `compose` 皆空時拋出 `SpaceError` 測試 |
| **ET-03** | Passed | 2026-11-07 | 通過 `is_ephemeral=True` 記憶體隔離與零磁碟殘留驗證 |
| **ET-04** | Passed | 2026-11-07 | 通過損毀 `YFP2` 快照安全降級回退 `SnapshotState(head_generation=0)` 測試 |
| **ET-05** | Passed | 2026-11-07 | 通過 `config_hash` 變更觸發全量重算與世代遞增測試 |
| **ET-06** | Passed | 2026-11-07 | 通過 `consume_diff` 例外中斷不推進游標及超前游標重置補償測試 |
| **RT-01** | Passed | 2026-11-07 | `dev check core` PASSED；`dev test core -q` 266 Passed, 0 Failed, 1 Skipped |

---

## 3. 人工 / UX 驗證 Checkpoint (Manual / UX Verification)

| 驗證編號 | 驗證項目與體驗焦點 | 建議手動操作步驟 / 指令 | 驗收狀態 (待驗收 / 已通過) |
| :--- | :--- | :--- | :---: |
| **UX-01** | 驗證 `fs scan`、`fs status`、`fs diff` 與 `fs clean` 實機 CLI 輸出與游標推進體驗 | 執行 `python yscb.py fs scan core/source`、`python yscb.py fs status core/source`、`python yscb.py fs diff core/source --consumer=dev --ack` 與 `python yscb.py fs clean core/source` | 已通過 |

---

## 4. 驗收簽核 (Sign-off)

- [x] 所有自動化測試（FT / ET / RT）均為 **Passed**
- [x] 所有人工 / UX 驗證項目經開發者確認通過（無則免勾）
- **最終狀態判定**：將文件頂部 `> 狀態：` 更新為 `Passed`（若有未解決阻塞則標為 `Blocked` 並退回 P05 修復）
