# `file-space` — 多工作空間幾何路由、雙階段指紋快照與變更游標引擎

`file-space` 為 YS-Codebase 生態系的跨模組工作空間基礎設施底座，負責統一管理命名檔案空間（Named File Spaces）之目錄幾何映射、雙階段單調世代指紋掃描（`YFP2` 二進位快照）、多消費者獨立游標（Multi-Consumer Watermark Cursors）以及背景檔案變動監聽服務（`FileSpaceWatcherServiceWorker`）。

---

## 1. 核心架構與職責

1. **雙軌空間宣告與聚合 (`FileSpaceManager`)**：
   - 自動探索並聚合各已安裝模組 `contributes/file-space.json`（Module Contributed）與宿主專案 `ys_codebase/config/file-space/contribute.json`（Project Override）之 `spaces` 定義。
   - **集合欄位附加合併**：同名空間的 `include`、`exclude`、`file_patterns` 自動去重附加合併。
   - **純量欄位宿主覆寫**：`hash_policy`、`large_file_threshold_mb`、`follow_symlinks`、`watch`、`weight`、`description` 由宿主專案優先覆寫。
   - **執行期臨時空間**：支援透過 `define_ephemeral_space(name, config)` 動態掛載記憶體空間（如沙盒測試目錄），不污染全域設定。

2. **雙階段門檻與四模分級雜湊 (`FingerprintScanner`)**：
   - **Stage 1 (`os.scandir` + 10ms Racy-Clean 防護)**：高速比對 `(mtime_ns, size)`，並針對 `abs(scan_start_ns - mtime_ns) < 10_000_000` 之極近修改檔案強制重算內容雜湊，消弭檔案系統時間戳精度競爭造成的漏檢。
   - **Stage 2 (四模 `HashPolicy`)**：
     - `adaptive`（預設）：小於 `large_file_threshold_mb`（預設 10MB）計算全量 `blake2b(digest_size=20)`；大於等於門檻採頭 64KB + 中 64KB + 尾 64KB + 檔案大小稀疏抽樣雜湊（帶 `"sample2b:"` 前綴）。
     - `full_hash`：忽略大小門檻，一律執行全量 `blake2b(digest_size=20)`。
     - `stat_only`：僅以 `"stat:{size}:{mtime_ns}"` 作為指紋，不讀取檔案內容。
     - `lazy_stabilized`：背景監聽模式下，大檔若距最後修改未滿 2.0 秒，暫標記 `pending_stabilization=True` 並使用 `"pending:{size}:{mtime_ns}"`，待靜置滿 2 秒後收斂為 `adaptive` 雜湊。

3. **YFP2 單調世代二進位快照與多消費者游標 (`BinarySnapshotManager` & `CursorStore`)**：
   - 快照採用 Magic `b"YFP2"` 二進位格式搭配 `tempfile` + `os.replace` 原子寫入，記錄 `head_generation`、`merkle_root` 與每檔 `(created_gen, updated_gen, is_deleted)` 軟刪除墓碑。
   - 不同下游模組（如 `consumer_id="knowledge-db"` 或 `"backup"`）各自維護獨立游標水位 `cursors/<consumer_id>.json`，支援透過 `consume_diff(space_name, consumer_id)` Context Manager 實現異常安全（Exception-Safe）的增量消費。

4. **背景常駐監聽服務 (`FileSpaceWatcherServiceWorker`)**：
   - 整合 `watchdog` 監聽所有 `watch=True` 的空間目錄，內建 500ms 防抖合併與 `.yscb.lock` 全域交易鎖讓路機制，於增量快照更新後觸發程序內 `subscribe()` 回呼並廣播 `on_file_space_changed` 事件。

---

## 2. CLI 指令速查

```bash
# 檢視所有工作空間狀態、世代水位與 Merkle Root
python yscb.py file-space status [--space <name>] [--json]

# 觸發雙階段增量指紋掃描並更新 YFP2 快照
python yscb.py file-space scan [--space <name>] [--force] [--json]

# 列出空間內受納管之有效檔案清單
python yscb.py file-space files [--space <name>] [--pattern <glob>] [--json]

# 檢視特定消費者相對於最新快照之增量差異 (加 --ack 可同步推進游標)
python yscb.py file-space diff [--space <name>] [--consumer <id>] [--ack] [--json]

# 清除空間二進位快照或重置消費者游標
python yscb.py file-space clean [--space <name>] [--consumer <id>] [--json]
```

---

## 3. Python SDK 範例

```python
import file_space

# 1. 觸發增量掃描並取得空間整體 Merkle Root
file_space.refresh("source")
root_hash = file_space.merkle_root("source")

# 2. 使用異常安全之多消費者游標處理增量變更
with file_space.consume_diff("source", consumer_id="knowledge-db") as diff_result:
    if diff_result.detail.has_changes:
        for rel_path in diff_result.detail.dirty_files:
            pass  # 執行下游增量處理
        for del_path in diff_result.detail.deleted:
            pass  # 清除已刪除檔案索引
# 正常離開 with 區塊時自動執行 ack(to_generation)；若拋出例外則保留原游標水位
```
