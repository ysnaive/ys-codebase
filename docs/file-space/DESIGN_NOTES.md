---
target: "File-Space"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/file-space/file_space/scanner.py"
  - "yscb://source/file-space/file_space/service.py"
  - "yscb://source/file-space/file_space/manager.py"
related_docs:
  - "./README.md"
  - "../knowledge-db/DESIGN_NOTES.md"
last_updated: "2026-11-02"
---

# file-space 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`file-space`  
> 職責定位：記錄 `file-space` 模組中屬於「維度 ⑤ 工程妥協與防坑」之非直覺設計、Racy-Clean 時間窗防護、二進位格式自癒與多消費者游標隔離不變量。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :---: | :--- | :--- | :---: |
| **DN-SP-01** | 10ms Racy-Clean 時間窗穿透防護與 `adaptive` 192KB 稀疏抽樣邊界 | `scanner.py` | 🚨 CRITICAL |
| **DN-SP-02** | `YFP2` 單調世代墓碑保留與多消費者游標 At-Least-Once 異常安全契約 | `scanner.py` | 🚨 CRITICAL |
| **DN-SP-03** | `FileSpaceWatcherServiceWorker` 對 `.yscb.lock` 全域交易鎖讓路與 `.watcher_active` 零冗餘掃描協調 | `service.py`, `scanner.py` | ⚠️ WARNING |

---

## 詳細設計決策與防坑邊界

### [DN-SP-01] 10ms Racy-Clean 時間窗穿透防護與 `adaptive` 192KB 稀疏抽樣邊界

- **背景與根因**：
  1. 在自動化測試或高速程式碼生成器連續寫入同一檔案且檔案大小 (`size`) 未改變時，若檔案寫入時間與前次快照掃描時間落在作業系統檔案系統時間戳粒度內（或極近之 `< 10ms` 視窗），單純依賴 `(mtime_ns, size)` 比對會誤判為未修改（Racy-Clean 漏檢）。
  2. 若對空間內偶發出現之數十 MB 大型資產檔執行全量雜湊，會阻塞前台 CLI 與背景 Watcher 執行緒。
- **工程妥協與解法**：
  1. **10ms Racy-Clean 強制穿透**：於 `FingerprintScanner` Stage 1 比對時，即使 `mtime_ns == prev.mtime_ns` 且 `size == prev.size`，只要 `abs(scan_start_ns - mtime_ns) < 10_000_000`（10 毫秒），強制穿透進入 Stage 2 重算內容雜湊。
  2. **`adaptive` 頭中尾 64KB 稀疏抽樣**：對 `>= large_file_threshold_mb`（預設 10MB）之大檔，讀取頭 `64KB`、正中 `64KB`、尾 `64KB` 共 `192KB` 連同 `size` 計算 `blake2b(digest_size=20)` 並冠上 `"sample2b:"` 前綴。

> [!CAUTION]
> **嚴禁移除 Stage 1 中的 `RACY_CLEAN_WINDOW_NS` (`10_000_000`) 判斷條件！** 移除後將導致同毫秒/毫秒級連續等長覆寫在自動化測試與熱修補中機率性漏檢。

---

### [DN-SP-02] `YFP2` 單調世代墓碑保留與多消費者游標 At-Least-Once 異常安全契約

- **背景與根因**：
  當多個下游消費者（如 `knowledge-db` 與其他分析工具）共用同一份空間指紋快照時，若採傳統「掃描即覆蓋舊狀態、直接物理移除已刪除檔案紀錄」的做法，較晚執行的消費者將永遠無法得知哪些檔案在中間世代被刪除，也無法得知某檔案自上次消費後是否曾發生修改。
- **工程妥協與解法**：
  1. **單調遞增世代 (`head_generation`) 與軟刪除墓碑 (`is_deleted`)**：`YFP2` 快照為每筆 `FileFingerprint` 記錄 `created_gen`、`updated_gen` 與 `is_deleted`。當檔案被刪除時，將其標記為 `is_deleted=True` 並更新 `updated_gen = new_gen`，使任意處於 `acked_gen < head_generation` 的消費者皆能精確推導出 `(added, modified, deleted)`。
  2. **配置雜湊 (`config_hash`) 變更自動失效**：當空間之 `include`/`exclude`/`file_patterns`/`hash_policy` 變更導致 `config_hash` 不一致，或 `acked_gen > head_generation` 時，游標自動視為無效並回退全量差異 (`baseline_missing=True`)。
  3. **`consume_diff` 異常不推進游標**：`consume_diff()` 僅在 `with` 區塊無例外正常退出時呼叫 `ack()` 寫入 `cursors/<consumer_id>.json`。

> [!CAUTION]
> **嚴禁在 `FingerprintScanner.refresh()` 發現檔案消失時直接從 `YFP2` 字典中 `del` 移除該筆記錄（除非執行 `clean` 全清）！** 直接刪除將導致尚未消費該世代的下游模組丟失 `deleted` 事件而殘留幽靈索引。

---

### [DN-SP-03] `FileSpaceWatcherServiceWorker` 對 `.yscb.lock` 全域交易鎖讓路與 `.watcher_active` 零冗餘掃描協調

- **背景與根因**：
  1. 當宿主正在執行 `yscb.py install / update / remove` 批次原子交易時，目錄正處於密集搬移與重載狀態；若 `file-space-watcher` 在此期間立即觸發掃描與 `on_file_space_changed` 廣播，會讀到半成品狀態並與安裝器爭搶磁碟 I/O。
  2. 當 `file-space-watcher` 常駐運行時，它已在背景將 `YFP2` 快照維持在最新世代；若前台 `consume_diff()` 每次仍無條件執行 `os.scandir` 重掃，將產生冗餘系統呼叫。
- **工程妥協與解法**：
  1. **`.yscb.lock` 交易鎖延遲讓路**：`FileSpaceWatcherServiceWorker` 防抖計時器觸發時，若偵測到 `.yscb.lock` 被持有，自動重設防抖計時器延後執行，待安裝交易鎖釋放後才單次收斂更新。
  2. **`.watcher_active` 自動感知**：`FileSpaceWatcherServiceWorker` 啟動時寫入 `.watcher_active`（含活體 PID 校驗，停止時於 `finally` 清除）；`consume_diff()` 之 `auto_refresh=None` 預設為 `not is_watcher_active() or is_watcher_dirty()`，在背景監聽穩定就緒時直接零掃描讀取 `YFP2` 計算游標差量。

> [!WARNING]
> **修改 `FileSpaceWatcherServiceWorker.start/stop` 時，務必保證 `finally` 區塊清理 `.watcher_active` 與 `.watcher_dirty` 信標！**

