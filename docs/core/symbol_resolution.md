---
target: "Core/Symbols"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/core/core/symbols.py"
related_docs:
  - "./API_REFERENCE.md"
  - "./README.md"
last_updated: "2026-08-26"
---

# 符號解析與動態模組載入機制 (Symbol Resolution & Loading)

> 所屬模組：`module:core`  
> 抽象維度：維度 3（中觀動態機制與多物件協同）  

---

## 1. 機制背景與設計目標

在 YSCB 微內核架構中，模組宣告（如 `contributes.insert` 中的 Computed Token 或未來的 Hook/CLI 擴充）需要精確指向特定 Python 函式。為了終結各模組私有解析方案，Core 提供標準的 **`code.func://` 符號定位協議** 與 **雙軌動態加載器**。

---

## 2. 協議語法規格

```text
code.func://<module_name>/<subpath>:<function_name>
```

- **`<module_name>`**：模組名稱（如 `agents-workflow`、`core`）。
- **`<subpath>`**：模組內相對腳本或套件路徑（如 `providers`、`testing/runner`）。支援忽略 `.py` 後綴。
- **`:`**：函式符號分隔標籤。
- **`<function_name>`**：目標 Callable 函式名稱。

---

## 3. 雙軌尋址與載入流向 (Dual-Track Resolution)

```text
┌────────────────────────────────────────────────────────┐
│   輸入: code.func://<module>/<subpath>:<func_name>     │
└───────────────────────────┬────────────────────────────┘
                            │
              [檢查 Callable 快取命中?]
              ├─ 是 ──► 直接返回快取 Callable
              └─ 否 ──► 進入雙軌尋址
                            │
                            ▼
    ┌──────────────────────────────────────────────────┐
    │ 軌道 1: Package Import (優先)                    │
    │ 嘗試 importlib.import_module("<pkg>.<subpath>")  │
    └───────────────────────┬──────────────────────────┘
                            │
              [Package 導入成功?]
              ├─ 是 ──► 取得 getattr(mod, func_name)
              └─ 否 ──► 切換至軌道 2
                            │
                            ▼
    ┌──────────────────────────────────────────────────┐
    │ 軌道 2: VFS Spec Import (檔案降級)               │
    │ 透過 uri.resolve 尋找 module.root:// / source/   │
    │ 實體 .py 檔案，使用 spec_from_file_location 載入 │
    └───────────────────────┬──────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────────┐
    │ 符號校驗與安全快取                               │
    │ 驗證 callable(fn) ➔ 寫入快取 ➔ 返回 Callable     │
    └──────────────────────────────────────────────────┘
```

---

## 4. 關鍵邊界防禦與不變量 (Invariants)

1. **命名空間隔離**：
   透過 VFS 載入實體檔案時，模組註冊於 `_yscb_code_<pkg>_<subpath>` 隔離空間，避免污染全域頂層模組。
2. **`sys.path` 自動補齊**：
   動態加載模組檔案時，自動確保其父目錄掛載於 `sys.path`，使模組內部的相對導入與子套件導入 100% 正常解析。
3. **無損轉型防護**：
   若 Provider 回傳 `None` 或非字串物件，解算器自動轉型為字串或空字串，保證工廠編譯流水線絕不崩潰。
