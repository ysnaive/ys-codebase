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
  - "../core/README.md"
  - "./DESIGN_NOTES.md"
  - "../knowledge-db/README.md"
  - "../server/hot_reload_and_services.md"
last_updated: "2026-11-07"
---

# File-Space 向下相容轉發殼層與遷移手冊 (File-Space Deprecation & Forwarding Shell)

> 模組名稱：`file-space` (`[Deprecated]`)  
> 職責定位：自 `core >= 1.2.8.0` 起，YS-Codebase 之通用邏輯檔案空間、`YFP2` 單調世代二進位指紋快照、多消費者交易游標與背景監聽協調已全面內聚為微內核 [`core.space`](../core/README.md) 子系統。`module:file-space` 現作為純標準庫輕量向下相容轉發殼層（Forwarding Shell），將舊版 `import file_space` 與 `yscb file-space` 呼叫無縫轉發至 `core.space`。

> [!WARNING]
> **升級與移除指引 (Migration & Removal Guide)**：
> 1. 請先將 `core` 更新至 `>= 1.2.8.0`（含自動遷移腳本 `1.2.7.x.py` / `1.2.8.x.py`，會自動將舊版 `config/file-space/contribute.json` 轉換合併至 `config/core/contribute.json`）。
> 2. 更新完成後，請直接執行 `python yscb.py remove file-space` 移除本過渡模組。
> 3. 所有 CLI 操作請改用微內核原生指令：`python yscb.py fs <subcmd>`（或 `python yscb.py core file-space <subcmd>`）。
> 4. 所有 Python SDK 開發請直接引用：`import core.space`（或 `from core import space`）。

---

## 1. 轉發殼層架構與相容映射 (Forwarding Shell Mapping)

為確保尚未移除 `file-space` 之外部環境平滑過渡，`file-space` (`1.0.1.0`) 移除了所有獨立 `watchdog` 依賴與 `contributes/server.json` 背景服務宣告（徹底杜絕雙 Watcher 雙重掃描競爭），並將 API 100% 轉發至 `core.space`：

| 舊版 `file_space` 介面 | 轉發目標 (`core.space`) | 說明 |
| :--- | :--- | :--- |
| **`file_space.consume_diff(space, consumer_id=...)`** | `core.space.consume_diff` | 交易式多消費者游標差量消費 Context Manager |
| **`file_space.merkle_root(space)`** | `core.space.merkle_root` | O(1) 讀取空間快照之 16-byte Blake2b Merkle Root |
| **`file_space.scan / status / diff / clean / files`** | `core.space.scan / status / diff / clean / files` | 空間掃描、狀態查詢、游標差量與快照清理門面函式 |
| **`file_space.FileSpaceManager`** | `core.space.SpaceRegistry` 薄轉發適配器 | 相容舊版 `define_ephemeral_space(include=..., file_patterns=...)` 欄位自動轉譯為 `entries` / `include` |
| **`file_space.service.subscribe(...)`** | `core.space.subscribe(...)` | 轉發至微內核 `core.space.watcher` 進程內訂閱註冊表 |

---

## 2. 新版空間宣告 Schema (`contributes/core.json` & `config/core/contribute.json`)

空間宣告已統一收斂至 `core` 擴充點（注意欄位名稱由舊版 `include` 根目錄 + `file_patterns` Glob 升級為標準 `entries` 根目錄 + `include` Glob）：

```json
{
  "spaces": {
    "source": {
      "description": "專案核心原始碼空間",
      "entries": ["project://ys_codebase/source"],
      "presets": ["@gitignore"],
      "include": ["*.py", "*.json", "*.scm", "*.md"],
      "exclude": ["**/__pycache__/**", "**/.pytest_cache/**"],
      "hash_policy": "adaptive",
      "large_file_threshold_mb": 10,
      "follow_symlinks": false,
      "watch": true,
      "weight": 1.0
    }
  }
}
```

---

## 3. CLI 對照與快速上手 (`yscb fs`)

```bash
# 1. 檢視所有已註冊空間、世代水位 (head_generation)、Merkle Root 與各消費者同步狀態
python yscb.py fs status
python yscb.py fs status source --json

# 2. 觸發雙階段增量指紋掃描並更新 YFP2 二進位快照 (--force 強制重算內容雜湊)
python yscb.py fs scan
python yscb.py fs scan source --force --json

# 3. 列出空間內受納管之有效檔案清單
python yscb.py fs ls source --pattern="*.py" --json

# 4. 檢視特定消費者相對於最新快照之增量差異 (加 --ack 可同步推進游標水位)
python yscb.py fs diff --consumer=knowledge-db --json
python yscb.py fs diff source --consumer=backup --ack --json

# 5. 清除空間二進位快照或重置特定消費者游標
python yscb.py fs clean --consumer=knowledge-db --json
python yscb.py fs clean source --json
```

---

## 4. 相關技術文件指針

- 🏛️ **Core 微內核與 `core.space` 完整手冊**：[../core/README.md](../core/README.md)
- 🛡️ **設計決策與工程妥協手冊**：[DESIGN_NOTES.md](./DESIGN_NOTES.md)
- 🔍 **Knowledge-DB 模組手冊**：[../knowledge-db/README.md](../knowledge-db/README.md)


