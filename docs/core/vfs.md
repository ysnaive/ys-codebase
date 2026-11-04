---
target: "Core"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/core/core/vfs/__init__.py"
  - "yscb://source/core/core/vfs/os_backend.py"
  - "yscb://source/core/core/vfs/path.py"
related_docs:
  - "./README.md"
  - "./uri_protocols.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-11-04"
---

# 統一虛擬檔案系統手冊 (Unified Virtual File System - VFS)

本手冊說明 YS-Codebase 核心虛擬檔案系統 (`core.vfs`) 之分層架構、後端插槽化、原子寫入保證與 API 使用範例。

---

## 🏛️ 1. 架構定位與單向相依原則

```text
+-------------------------------------------------------------------------+
|                        Ecosystem Consumers                              |
|           core, dev, agents-workflow, knowledge-db, server              |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                     core.vfs (微內核統一檔案存取)                         |
|  - Facade API: read_text, write_text, read_json, write_json             |
|  - VirtualPath: 物件導向鏈式操作與 `/` 路徑拼接運算子                      |
|  - atomic_write: 同目錄原子覆蓋上下文管理器                              |
|  - assert_safe_path: 沙盒防逃逸邊界檢核                                 |
+-------------------------------------------------------------------------+
        |                                                 |
        | (單向依賴: 語意協議解算)                           | (委派實體存取)
        v                                                 v
+--------------------------------+       +--------------------------------+
|  core.uri (純字串協議 SSOT)    |       |  OSBackend (VFSBackend 具體實作) |
|  - resolve(uri) -> str         |       |  - 跨平台路徑規範化             |
|  - to_uri(abs_path) -> str     |       |  - 同目錄同分區原子寫入         |
|  - 舊 IO helpers 向下相容轉發  |       |  - (未來插槽: MemoryBackend)   |
+--------------------------------+       +--------------------------------+
```

### 核心原則
1. **單向依賴純淨性**：`core.uri` 作為最底層純字串定址協議，不依賴 `core.vfs`。`core.vfs` 單向依賴 `core.uri.resolve` 解析語意 URI。
2. **微內核唯一性**：VFS 完整封裝於 `core` 模組內部，維持 `core` 為唯一微內核。
3. **向下相容性**：`core.uri` 既有的 IO helpers（`read_text`, `write_text`, `exists` 等）已平滑委派至 `core.vfs`，既有程式碼無痛運作。

---

## ⚡ 2. 快速上手範例 (Quick Start)

### 2.1 高階便捷函式

```python
from core import vfs

# 1. 支援語意 URI 直接讀寫 (預設啟用原子寫入防護)
vfs.write_text("project://docs/example.md", "# Hello VFS\n", atomic=True)
content = vfs.read_text("project://docs/example.md")

# 2. 結構化 JSON 讀寫
config_data = {"version": "1.1.0", "enabled": True}
vfs.write_json("cache://my_module/state.json", config_data)
loaded = vfs.read_json("cache://my_module/state.json")

# 3. 狀態檢查與目錄操作
if vfs.exists("project://docs"):
    items = vfs.listdir("project://docs")
    print("Files:", items)
```

### 2.2 物件導向 `VirtualPath`

```python
from core.vfs import VirtualPath

# 使用 / 運算子優雅拼接
base = VirtualPath("project://docs")
spec_file = base / "specs" / "vfs.md"

if spec_file.exists():
    text = spec_file.read_text()

# 鏈式建立目錄與寫入
new_doc = base / "notes" / "draft.txt"
new_doc.write_text("Draft Content", atomic=True)
print(new_doc.name)    # "draft.txt"
print(new_doc.suffix)  # ".txt"
```

### 2.3 原子寫入與跨平台 LF 換行保證 (Atomic Write & LF Line-Ending Guarantee)

```python
from core import vfs

# 在目標同級目錄下生成暫存檔，完成後原子替換，防止寫入中斷損毀；
# 文字模式 (write_text / atomic_write mode="w") 固定以 newline="\n" 開檔，
# 確保 Windows 與 POSIX 寫出一致之 LF 換行（顯式傳入之 "\r\n" 原樣保留）
with vfs.atomic_write("project://config.json", mode="w") as f:
    f.write('{"status": "ready"}\n')
```

---

## 🛡️ 3. 安全邊界防護與跨平台防腐原語 (`robust_rmtree` / `robust_replace`)

`OSBackend` 內建授權邊界防護與跨平台防腐層：
- **成對 `realpath` 邊界校驗**：`assert_safe_path` 與 `core.uri` 對根目錄與目標路徑成對執行 `os.path.realpath()`，消除 macOS `/var -> /private/var` 系統符號連結誤報並攔截 `../` 逃逸。
- **`robust_rmtree(path, ignore_errors=False, max_retries=5)`**：針對 Windows `.git` 唯讀物件（`WinError 5`）自動於 `onexc`/`onerror` 剝離唯讀位元（`os.chmod(..., stat.S_IWRITE | stat.S_IREAD)`），並對短暫句柄佔用（`WinError 32` / `EACCES`）執行退避重試。
- **`robust_replace(src, dst, max_retries=10)`**：針對 Windows `PermissionError` 執行退避重試並於目標唯讀時自動賦予寫入權限；遭遇跨掛載點 `errno.EXDEV` 時自動於目標同目錄建立 `.tmp` 暫存完成原子替換。
