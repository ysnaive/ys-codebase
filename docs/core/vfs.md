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

### 2.3 原子寫入保證 (Atomic Write Guarantee)

```python
from core import vfs

# 在目標同級目錄下生成暫存檔，完成後原子替換，防止寫入中斷損毀
with vfs.atomic_write("project://config.json", mode="w") as f:
    f.write('{"status": "ready"}')
```

---

## 🛡️ 3. 安全邊界防護與防逃逸 (Anti-Escape Sandbox)

`OSBackend` 內建授權邊界防護機制：
- 若指定授權邊界（如沙盒專屬目錄），任何帶有 `../../` 意圖逃逸出根目錄之路徑，`assert_safe_path` 將主動拋出 `PermissionError`。
- 跨平台消弭 Windows 反斜線與 POSIX 正斜線混用導致的逃逸偵測旁路。
