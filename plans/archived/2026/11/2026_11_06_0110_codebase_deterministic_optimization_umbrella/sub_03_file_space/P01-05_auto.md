# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_03_file_space 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `FileSpaceManager` 與 `FileSpaceConfig` 路徑、Symlink 與邊界正規化 (`OPT-01~10, 21~24, 38`) | 單例加 `_SINGLETON_LOCK`、修正單檔案 `include` 相對路徑、攔截 `follow_symlinks=False` 中繼 symlink、`st_ino==0` 無限遞迴防禦與頂層 `ack(space_generations=...)` 對齊。 | P0 | [P00:DR-01] |
| **FR-02** | `FingerprintScanner` 可重入跨進程鎖、墓碑同步與四集合互斥 Diff (`OPT-11~20, 39, 41`) | 實作 `_snapshot_lock` 可重入鎖、`refresh(None)` 舊空間刪除墓碑、`_diff_all_spaces` 四集合互斥、`CursorStore.list_consumers` 加鎖與非法雜湊策略轉拋 `InvalidFileSpaceConfigError`。 | P0 | [P00:DR-01] |
| **FR-03** | `FileSpaceWatcherServiceWorker` 批次異常回滾、Unified 同步與 CLI/Hook 強化 (`OPT-25~37, 40`) | `_rollback_space_batch` 異常回滾、`_sync_unified_snapshot_if_exists` 記憶體合併更新、目錄 `created` 事件觸發重掃、`hook.server.py` 防重入預熱鎖與 `scripts/cli.py` 頂層 `0 ast.Assign`。 | P0 | [P00:DR-02] |
| **FR-04** | `tests/test_*.py` 測試套件六維度純化與 0 `ResourceWarning` (`AUD-01~10`) | 消除全部 `time.sleep` 與工單編號前綴，補齊多執行緒游標 RMW 競爭、192KB 稀疏抽樣邊界、异常回滾與 `.yfp2` 損毀自癒測試。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 唯一單檔案 `include`（`multi_root=False`）時計算相對路徑 | `_compute_rel_path` 回傳檔案名稱而非 `"."`，確保迭代、歸屬檢查與增量修補一致。 |
| **EC-02** | `flush_dirty_spaces` 於 `_refresh_or_patch_space` 中途拋出例外 | `_rollback_space_batch` 將未完成空間與檔案路徑退回髒集合並保持 `.watcher_dirty` 標記。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('file-space')` 達成 `0 FAIL, 0 WARN`，腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 測試純淨度與執行效能 | 25 項單元測試於 `python3 -W error::ResourceWarning` 下 100% 通過（耗時 `0.85s`，`0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `file-space` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/file-space/file_space/__init__.py` | Modify | 落實 `OPT-01, OPT-02, OPT-38`（`_SINGLETON_LOCK` 與 `ack` 參數轉發） |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 落實 `OPT-03 ~ OPT-08`（單檔案相對路徑、Symlink 攔截與 `st_ino==0` 防禦） |
| `ys_codebase/source/file-space/file_space/providers.py` | Modify | 落實 `OPT-09, OPT-10`（提取 `_collect_space_weights` 與 Markdown 表格跳脫） |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | 落實 `OPT-11 ~ OPT-20, OPT-28, OPT-39, OPT-41`（可重入 `_snapshot_lock` 與 Diff 互斥） |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 落實 `OPT-21 ~ OPT-24`（提取 `_matches_exclude` 與邊界正規化） |
| `ys_codebase/source/file-space/file_space/service.py` | Modify | 落實 `OPT-25 ~ OPT-32, OPT-40`（異常回滾、Unified 同步與 Watchdog 目錄事件） |
| `ys_codebase/source/file-space/scripts/cli.py` | Modify | 落實 `OPT-33 ~ OPT-35`（CLI 輸出/異常收斂與 `clean` 同步清理） |
| `ys_codebase/source/file-space/scripts/hook.server.py` | Modify | 落實 `OPT-36`（`_PREWARM_LOCK` 防重複啟動預熱執行緒） |
| `ys_codebase/source/file-space/scripts/migrations/1.0.1.x.py` | Modify | 落實 `OPT-37`（`OSError` 容錯與斷裂 symlink 清理） |
| `ys_codebase/source/file-space/tests/test_file_space_manager.py` | Modify | 落實 `AUD-06, AUD-09, AUD-10`（7 項管理與過濾測試純化） |
| `ys_codebase/source/file-space/tests/test_fingerprint_scanner.py` | Modify | 落實 `AUD-02, AUD-05, AUD-07, AUD-09`（8 項指紋與併發測試純化） |
| `ys_codebase/source/file-space/tests/test_scanner_and_cursors.py` | Modify | 落實 `AUD-04, AUD-08, AUD-09, AUD-10`（5 項雜湊、Racy-Clean 與自癒測試） |
| `ys_codebase/source/file-space/tests/test_service_and_cli.py` | Modify | 落實 `AUD-01, AUD-03, AUD-09, AUD-10`（5 項服務防抖、CLI 與 Hook 測試） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 13 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `file-space` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_03_file_space` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/file-space/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/file-space/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-41` 與 `AUD-01 ~ AUD-10`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 13 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
