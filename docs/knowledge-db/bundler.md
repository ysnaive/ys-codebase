# knowledge-db 語意打包引擎指南 (Semantic Bundler Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.bundler`  
> 產物格式：自包含 JSON 發布包 (`.bundle.json`)  

---

## 📌 1. 概述與設計定位

`SemanticBundler` 是 `knowledge-db` 模組的核心打包與導出引擎。它協同 `SpaceManager`、`FingerprintScanner` 與 `ParserRegistry`，將空間內的原始碼與文檔編譯提取為自包含的語意封裝包 **`SemanticBundle`**。

---

## 📦 2. Bundle 資料格式規範 (`.bundle.json`)

```json
{
  "version": "1.0.0",
  "space_name": "project_main",
  "created_at": "2026-08-28T05:40:00.000000+00:00",
  "symbol_count": 128,
  "symbols": [
    {
      "id": "e5c7a4b8f...",
      "name": "KnowledgeEngine",
      "kind": "class",
      "file_path": "source/knowledge-db/knowledge_db/engine.py",
      "line_number": 45,
      "language": "python",
      "docstring": "知識庫統一門面引擎",
      "signature": "class KnowledgeEngine",
      "members": [
        {
          "name": "search",
          "kind": "method",
          "signature": "def search(self, query: str) -> List[SearchResult]",
          "docstring": "執行語意搜尋",
          "visibility": "public",
          "line_number": 60
        }
      ],
      "tags": [],
      "metadata": {
        "end_line": 150,
        "bases": ["BaseEngine"]
      }
    }
  ],
  "thesaurus": [
    ["搜尋", "search", "query"],
    ["空間", "space", "scope"]
  ],
  "metadata": {
    "source_count": 2,
    "file_count": 15,
    "origin": "project"
  }
}
```

---

## 🛠️ 3. CLI 打包指令

```powershell
# 1. 為特定空間進行打包與導出
python yscb.py knowledge-db bundle project_main

# 2. 為全空間聯集執行批次打包
python yscb.py knowledge-db bundle --all

# 3. 指定自訂輸出檔案路徑
python yscb.py knowledge-db bundle project_main --output=exports/main_release.bundle.json
```

---

## 💻 4. Python SDK 打包與導出/導入

```python
from knowledge_db.bundler import SemanticBundler
from knowledge_db.space import SpaceManager

space_mgr = SpaceManager()
bundler = SemanticBundler(space_mgr)

# 1. 空間打包
space_cfg = space_mgr.get_space("project_main")
bundle = bundler.bundle_space(space_cfg)
print(f"打包完成，共提取 {len(bundle.symbols)} 個符號")

# 2. 原子導出
export_path = bundler.export_bundle(bundle)
print(f"Bundle 已安全導出至: {export_path}")

# 3. 離線載入還原
imported_bundle = bundler.import_bundle(export_path)
print(f"成功載入 Bundle: {imported_bundle.space_name}")
```

---

## 🔒 5. 原子寫入與安全性保證

- **暫存檔原子替換 (Atomic Replace)**：`export_bundle` 寫入時先建立同目錄臨時檔案，序列化確認無誤後透過作業系統底層 `os.replace` 進行不可分割之原子替換，徹底防止因寫入中斷或磁碟滿載導致 Bundle 檔案殘缺毀損。
