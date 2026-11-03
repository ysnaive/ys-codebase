---
target: "File-Space"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/file-space/file_space/__init__.py"
  - "yscb://source/file-space/file_space/manager.py"
  - "yscb://source/file-space/file_space/scanner.py"
  - "yscb://source/file-space/file_space/service.py"
  - "yscb://source/file-space/scripts/cli.py"
related_docs:
  - "./DESIGN_NOTES.md"
  - "../knowledge-db/README.md"
  - "../server/hot_reload_and_services.md"
last_updated: "2026-11-03"
---

# File-Space 通用檔案空間、分級指紋快取與背景監聽底座模組手冊 (File-Space Overview)

> 模組名稱：`file-space`  
> 職責定位：YS-Codebase 生態系跨模組工作空間基礎設施底座，統一管理命名檔案空間（Named File Spaces）之雙軌配置聚合、語意 URI 解算、雙階段單調世代指紋掃描（`YFP2` 二進位快照）、多消費者獨立游標（Multi-Consumer Watermark Cursors）與背景 `watchdog` 增量監聽服務（`FileSpaceWatcherServiceWorker`）。

---

## 1. 模組定位與核心能力 (Vision & Capabilities)

`file-space` 模組作為跨模組共用之檔案空間基礎設施，將「目錄範圍界定」、「指紋快照計算」、「消費者增量水位管理」與「作業系統檔案事件監聽」自下游業務模組（如 `knowledge-db`）中解耦收斂：

- **雙軌空間宣告與聚合 (`FileSpaceManager`)**：
  - 透過 `core.contributes` 依據 `contributes/_format.json`（`include`/`exclude`/`file_patterns` 宣告 `| extend`、`spaces.*` 宣告 `$FileSpaceDef | merge`）自動聚合各已安裝模組 `module://<donor>/contributes/file-space.json` 與宿主專案 `config://file-space/contribute.json` 之 `spaces` 定義，並根據累積之 `"__providers__"` 清單精確判定空間來源 `origin`（單一來源顯示為 `origin(<provider>)`、多源合併顯示為 `merged(<provider_a>, <provider_b>, ...)`）。
  - **列表欄位附加去重**：同名空間的 `include`、`exclude`、`file_patterns` 依據 `| extend` 策略自動保序去重附加合併。
  - **純量欄位宿主覆寫**：`hash_policy`、`large_file_threshold_mb`、`follow_symlinks`、`watch`、`weight`、`description` 由後載入方或宿主專案優先覆寫（未顯式提供之選填欄位保留既有設定，不被預設值洗掉）。
  - **執行期臨時空間與快取優化**：支援透過 `define_ephemeral_space(name, config)` 動態掛載記憶體空間（如單元測試沙盒），不污染全域設定；`project_root` 屬性快取於實例 `_cached_project_root`，`load_spaces(force: bool = False)` 內建已載入守衛避免重複讀盤，且目錄走訪 `_walk_root` 於非符號連結且 `follow_symlinks=False` 時直接使用 `DirEntry.path` 免除逐檔冗餘 `Path.resolve()` 系統呼叫。
- **雙階段門檻與四模分級雜湊 (`FingerprintScanner`)**：
  - **Stage 1 (`os.scandir` + 10ms Racy-Clean 防護)**：高速比對 `(mtime_ns, size)`，並針對 `abs(scan_start_ns - mtime_ns) < 10_000_000` 之極近修改檔案強制重算內容雜湊，消弭檔案系統時間戳精度競爭造成的同毫秒改檔漏檢。
  - **Stage 2 (四模 `HashPolicy`)**：支援 `adaptive`（預設，`< 10MB` 全量 `blake2b(digest_size=20)`，`>= 10MB` 頭/中/尾各 64KB 稀疏抽樣）、`full_hash`、`stat_only` 與 `lazy_stabilized`（背景監聽大檔 2.0 秒靜置收斂）。
- **YFP2 單調世代二進位快照與多消費者游標 (`BinarySnapshotManager` & Cursors)**：
  - 快照存放於 `file-space.storage://snapshots/<space_name>.yfp2.bin`（與跨空間統一視圖 `unified.yfp2.bin`），採用 Magic `b"YFP2"` 二進位結構搭配暫存檔 + `os.replace` 原子寫入，內嵌 `head_generation`、`merkle_root` 與每檔 `(created_gen, updated_gen, is_deleted)` 軟刪除墓碑。
  - 各下游模組（如 `consumer_id="knowledge-db"`）於 `file-space.storage://cursors/<consumer_id>.json` 維護獨立游標水位 (`acked_gen`，內建 `threading.RLock` 保護多執行緒併發更新)，互不干擾，並透過 `consume_diff()` Context Manager 保證 At-Least-Once 異常安全消費（全空間 `space_name=None` 模式下透過 `ScanDiffResult.space_generations` 精確推進各子空間當次讀取世代，且針對 `watch=False` 之空間自動維持 JIT `auto_refresh=True`）。
- **背景常駐監聽服務 (`FileSpaceWatcherServiceWorker`)**：
  - 透過 `contributes/server.json` 向 `server` 註冊 `file-space-watcher` 服務，基於 `watchdog>=4.0.0` 監聽所有 `watch=True` 的空間目錄，內建 500ms 防抖視窗與 `.yscb.lock` 全域交易鎖讓路機制，於增量快照更新後觸發程序內 `subscribe()` 回呼並透過 `core.event.emit("on_file_space_changed", ...)` 廣播事件。

---

## 2. 空間宣告 Schema (`contributes/file-space.json` & `config/file-space/contribute.json`)

```json
{
  "spaces": {
    "source": {
      "description": "專案核心原始碼空間",
      "include": ["project://ys_codebase/source"],
      "exclude": ["**/__pycache__/**", "**/.pytest_cache/**"],
      "file_patterns": ["*.py", "*.json", "*.scm", "*.md"],
      "hash_policy": "adaptive",
      "large_file_threshold_mb": 10,
      "follow_symlinks": false,
      "watch": true,
      "weight": 1.0
    }
  }
}
```

| 欄位名稱 | 型別 | 預設值 | 合併策略與說明 |
| :--- | :---: | :---: | :--- |
| **`include`** | `List[str]` | *(必填)* | 語意 URI 清單（如 `project://...`、`module://...`、`docs://`）；跨模組同名空間去重附加 |
| **`exclude`** | `List[str]` | `[]` | 排除之 Glob 模式清單；跨模組同名空間去重附加 |
| **`file_patterns`** | `List[str]` | `[]` | 允許納入之檔名 Glob 清單（空陣列代表全包含）；跨模組同名空間去重附加 |
| **`hash_policy`** | `str` | `"adaptive"` | 雜湊策略：`"adaptive"` \| `"full_hash"` \| `"stat_only"` \| `"lazy_stabilized"`；宿主覆寫 |
| **`large_file_threshold_mb`** | `int` | `10` | `adaptive` / `lazy_stabilized` 之大檔分界門檻（MB，`>= 1`）；宿主覆寫 |
| **`follow_symlinks`** | `bool` | `false` | 走訪目錄時是否跟隨符號連結；宿主覆寫 |
| **`watch`** | `bool` | `true` | 是否納入 `file-space-watcher` 常駐監聽；宿主覆寫 |
| **`weight`** | `float` | `1.0` | 空間預設權重（供下游檢索模組作為預設回退值）；宿主覆寫 |

---

## 3. CLI 快速上手 (Quick Start)

`file-space` 模組提供 5 個正交標準 CLI 指令：`status`, `scan`, `files`, `diff`, `clean`。

```bash
# 1. 檢視所有已註冊空間、世代水位 (head_generation)、Merkle Root 與各消費者同步狀態
python yscb.py file-space status
python yscb.py file-space status --space source --json

# 2. 觸發雙階段增量指紋掃描並更新 YFP2 二進位快照 (--force 強制重算內容雜湊)
python yscb.py file-space scan
python yscb.py file-space scan --space source --force --json

# 3. 列出空間內受納管之有效檔案清單與指紋摘要
python yscb.py file-space files --space source --pattern "*.py" --json

# 4. 檢視特定消費者相對於最新快照之增量差異 (加 --ack 可同步推進游標水位)
python yscb.py file-space diff --consumer knowledge-db --json
python yscb.py file-space diff --space source --consumer backup --ack --json

# 5. 清除空間二進位快照或重置特定消費者游標
python yscb.py file-space clean --consumer knowledge-db --json
python yscb.py file-space clean --space source --json
```

---

## 4. Python SDK 與事件訂閱範例 (Python SDK & Event Hook)

### 4.1 門面 SDK (`consume_diff` & `merkle_root`)

```python
import file_space

# 1. O(1) 讀取空間 Merkle Root (若尚未掃描會自動觸發首次快照建立)
root_hash = file_space.merkle_root("source")

# 2. 異常安全之多消費者游標增量消費 (At-Least-Once 語意)
with file_space.consume_diff("source", consumer_id="knowledge-db") as result:
    if result.detail.has_changes:
        for rel_path in result.detail.dirty_files:
            # 處理新增 (added) 與修改 (modified) 檔案
            pass
        for del_path in result.detail.deleted:
            # 清理已刪除檔案
            pass
# 正常離開 with 區塊時自動 ack(to_generation=result.to_generation)；
# 若區塊內拋出任何例外，游標保持原位，下次呼叫將再次收到相同變更集。
```

### 4.2 訂閱 `on_file_space_changed` 跨模組事件 (`scripts/hook.file-space.py`)

下游模組可於 `scripts/hook.file-space.py` 實作 `on_file_space_changed`，當 `file-space-watcher` 偵測到磁碟變更並更新 `YFP2` 快照後將自動觸發：

```python
def on_file_space_changed(context, spaces=None, diff_summary=None, **kwargs):
    # FileSpaceWatcherServiceWorker 已於廣播前完成 YFP2 快照更新，
    # 下游直接以 auto_refresh=False 消費自身 consumer_id 之游標差量即可
    pass
```

---

## 5. 相關技術文件指針

- 🛡️ **設計決策與工程妥協手冊**：[DESIGN_NOTES.md](./DESIGN_NOTES.md)
- 🔍 **Knowledge-DB 模組手冊**：[../knowledge-db/README.md](../knowledge-db/README.md)
- ⚡ **細粒度增量熱重載專題**：[../knowledge-db/incremental_hot_reload.md](../knowledge-db/incremental_hot_reload.md)

