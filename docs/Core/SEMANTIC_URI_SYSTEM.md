---
target: "Core/SemanticURI"
doc_type: "topic_manual"
status: "active"
source_paths:
  - "source/core/scripts/uri.py"
  - "source/core/scripts/context.py"
related_docs:
  - "./README.md"
  - "../Installer/README.md"
last_updated: "2026-08-23"
---

# Codebase 語意 URI 系統與統一路徑轉換器架構 (Semantic URI Protocol & Unified Converter)

本手冊定義 `ys-codebase` 工具庫的五層語意 URI 協議體系、沙盒圍欄安全防護（Chroot Guard）、最長前綴匹配（LPM）演算法與全套高階 I/O API。

---

## 1. 五層協議體系架構 (Five-Tier Architecture)

```
層級 1: 專案空間協議 (Spatial Schemes) ──> project:// (專案根目錄), yscb:// (工具庫根目錄)
層級 2: 模組命名空間協議 (Scoped Schemes) ─> cache://<module>/ (快取), storage://<module>/ (持久儲存)
層級 3: 領域專題協議 (Domain Schemes) ───> plans://, archive://, docs://, sop_ext://
層級 4: 系統隔離暫存 (Temporary Scheme) ──> temp:// (.yscb_cache/tmp)
層級 5: 動態外掛協議 (Dynamic Schemes) ────> 由第三方模組 manifest.json contributes 聲明注入
```

### 標準協議語意與空間映射表

| URI 協議 | 核心語意 | 實體解析基準 (Base Path) | 沙盒圍欄邊界 |
| :--- | :--- | :--- | :--- |
| **`project://<path>`** | 專案根目錄 | `paths.project_root` (例：`d:/repos/my_project/`) | `ProjectContext.get_project_root()` |
| **`yscb://<path>`** | 工具庫核心目錄 | `paths.yscb_root` (例：`d:/repos/my_project/yscb/`) | `ProjectContext.get_yscb_root()` |
| **`cache://<mod>/<p>`** | 模組專屬快取 | `yscb://.yscb_cache/modules/<module>/` | 限制於該模組專屬快取子目錄 |
| **`storage://<mod>/<p>`**| 模組持久儲存 | `project://.yscb_storage/<module>/` | 限制於該模組持久儲存子目錄 |
| **`temp://<path>`** | 系統隔離暫存 | `yscb://.yscb_cache/tmp/` | 限制於暫存目錄 |
| **`plans://<path>`** | 活躍計畫目錄 | 依模組設定 `paths.plans_dir` | 限制於 plans 實體目錄 |
| **`archive://<path>`** | 歷史歸檔目錄 | 依模組設定 `paths.archive_dir` | 限制於 archive 實體目錄 |
| **`docs://<path>`** | 專案知識庫 | 依模組設定 `paths.docs_dir` (預設 `docs/`) | 限制於 docs 實體目錄 |
| **`sop_ext://<path>`** | SOP 擴充清單 | 依模組設定 `paths.extensions_dir` | 限制於 extensions 實體目錄 |

---

## 2. 核心 API 簽名與使用範例

### 2.1 語意解析與校驗 (`ProjectURI.resolve` / `ProjectURI.validate`)

```python
from yscb_core import ProjectURI

# 1. 基礎解析 (返回絕對 Path，若未啟用或失敗返回 '!undefined')
abs_path = ProjectURI.resolve("docs://topic/architecture.md")

# 2. 嚴格模式解析 (遇到越界或無效協議時拋出 PermissionError / ValueError)
try:
    path = ProjectURI.resolve("docs://../../secret.json", strict=True)
except PermissionError as e:
    print(f"安全性攔截: {e}")

# 3. 完備度校驗門面
is_valid, err_msg = ProjectURI.validate("cache://knowledge-db/index.json")
if not is_valid:
    print(f"URI 校驗失敗: {err_msg}")
```

### 2.2 反向轉換與最長前綴匹配 (`ProjectURI.to_uri`)

依據 **最長前綴貪婪匹配 (LPM)** 演算法與優先級排序（`Domain > Scoped > Spatial`），自動將本機實體路徑轉換為最精確的最短語意 URI：

```python
# 傳入 d:/repos/my_project/docs/guides/setup.md
uri = ProjectURI.to_uri("docs/guides/setup.md")
# 回傳: "docs://guides/setup.md" (而非 project://docs/guides/setup.md)

# 傳入 d:/repos/my_project/yscb/.yscb_cache/modules/knowledge-db/index.json
cache_uri = ProjectURI.to_uri(cache_file_path)
# 回傳: "cache://knowledge-db/index.json"
```

### 2.3 高階 Direct I/O 門面 API

```python
# 直寫 (自動 mkdir -p 父目錄)
ProjectURI.write_text("cache://knowledge-db/manifest.json", '{"status": "ok"}')

# 直讀
content = ProjectURI.read_text("cache://knowledge-db/manifest.json")

# 狀態判斷
if ProjectURI.exists("storage://knowledge-db/records.db"):
    print("Database exists!")
```

---

## 3. 沙盒圍欄防護機制 (Chroot Guard)

為防範路徑遍歷攻擊與意外逃逸：
1. **正規化防護**：自動將多重連續斜線（如 `docs:///sub//topic`）及 Windows 反斜線正規化為單一標準正斜線。
2. **越界阻斷**：當解析結果的路徑試圖透過 `..` 越界逃逸超出該 Scheme 所屬的 Base Path 邊界時，觸發安全攔截：
   - 預設模式：印出 `[SECURITY-WARN]` 並返回 `"!undefined"`。
   - 嚴格模式 (`strict=True`)：拋出 `PermissionError` 阻斷執行。
3. **快速通道 (Fast-Path)**：若路徑不含 `..` 逃逸字元，直接於記憶體以 Pure-Python 完成路徑拼接，避開高頻 Windows 內核系統呼叫，達成單次解析 **3.8 µs** 的極致效能。

---

## 4. 終端 CLI 診斷工具鏈

```bash
# 解析語意 URI 為實體絕對路徑
python yscb_cli.py uri resolve docs://_project/STANDARDS.md

# 診斷全專案語意 URI 協議健康狀態與沙盒圍欄
python yscb_cli.py uri check

# 列出所有已註冊協議與當前狀態矩陣
python yscb_cli.py uri list

# 將本機實體路徑轉為語意 URI
python yscb_cli.py uri to-uri docs/_project/STANDARDS.md

# 檢視模組專屬快取佔用統計
python yscb_cli.py cache status

# 清理指定模組或全部快取
python yscb_cli.py cache clean agents-workflow
python yscb_cli.py cache clean --all
```
