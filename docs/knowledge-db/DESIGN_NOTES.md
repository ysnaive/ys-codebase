# knowledge-db 設計決策與工程妥協手冊 (Design Notes)

> 模組名稱：`knowledge-db`  
> 建立日期：2026-08-28  
> 維護規範：凡涉及非直觀架構妥協、二進位協議選型、效能取捨或安全性限制，必須在此登錄 `DN-XX` 編號。  

---

## 登錄索引表

| 決策編號 | 決策主題 | 影響子系統 | 關鍵約束 / 取捨 |
| :---: | :--- | :--- | :--- |
| **DN-01** | **符號池分離去重與 Protocol 5 Gzip 快取** | `retrieval.py` | 倒排索引取消 Posting 內嵌 Symbol，改為頂層 `symbols` 符號池；本地快取使用 `pickle` Protocol 5 + `gzip` L6，達成 99.5% 體積縮減與 < 20ms 讀取。 |
| **DN-02** | **本地端快取物理隔離 (`cache://knowledge-db/`)** | `space.py`, `engine.py` | 所有指紋、倒排索引與 Bundle 產物 100% 留存於 `.cache/knowledge-db/`，利用 `.gitignore` 徹底防止 AST 符號與索引污染 Git。 |
| **DN-03** | **雙階增量指紋比對 (Two-Stage Fingerprint)** | `scanner.py` | 先比對 `mtime + size`，未命中或變更時才讀取計算 `SHA1`，避免全庫頻繁磁碟 I/O。 |
| **DN-04** | **JIT 變更嗅探與原生二進位快照 (`unified.meta.bin`)** | `scanner.py`, `engine.py` | 採用 Magic `YFP1` + `struct` 原生二進位封裝檔案清冊，反序列化耗時 < 0.1ms；檢索前執行 `os.scandir` stat 嗅探（2~3ms），Dirty 時無感背景熱自愈。 |

---

## 詳細設計決策說明

### DN-01: 符號池分離去重與 Protocol 5 Gzip 快取 (Symbol Pool Normalization)

- **背景與根因**：
  在早期設計中，`Posting` 倒排節點直接持有 `symbol: UnifiedSymbol` 物件。在多欄位分詞後，單一符號會出現在數十至數百個 Term 的 Posting 清單中，導致 JSON 序列化時產生巨大重複拷貝（94 KB 源碼文檔產生 55.35 MB 索引檔案，膨脹超過 500 倍）。
- **架構解法**：
  1. **符號池解耦**：`InvertedIndex` 頂層維護 `symbols: Dict[str, UnifiedSymbol]`，每個符號僅存 1 份；`Posting` 僅記錄 `doc_id`。
  2. **二進位 Gzip 序列化**：使用純 Python 3.9+ 原生標準庫 `pickle.HIGHEST_PROTOCOL` (Protocol 5) 配合 `gzip.compress` (Level 6)，儲存為 `.index.bin.gz`。
- **效益與驗證**：
  - 磁碟檔案體積由 55.35 MB 暴降至 253.89 KB（縮減 99.53%）。
  - 反序列化載入耗時由 ~850 ms 降低至 < 20 ms。
  - 檢索階段透過 `index.symbols[doc_id]` 以 $O(1)$ 複雜度還原完整符號。

---

### DN-02: 本地端快取物理隔離 (`cache://knowledge-db/`)

- **背景**：AST 與倒排索引屬於本機計算生成之衍生快取，不應提交至版本控制。
- **解法**：全面統一至 `cache://knowledge-db/`（對應專案根目錄 `.cache/knowledge-db/`）。
- **安全邊界**：`pickle` 二進位快取僅限定存取本地 `.cache/` 空間，嚴禁用於不可信網路傳輸；外部導出維持純 JSON 之 `SemanticBundle`。

---

### DN-04: JIT 變更嗅探與原生二進位快照 (Just-In-Time Smart Healing)

- **背景與根因**：
  跨開發者協作或 Git pull 後，若開發者忘記手動執行 `python yscb.py knowledge-db index`，檢索結果將嚴重失真或遺漏新符號。但若將索引存入 `storage://`（納入 Git 追蹤），每次修改均會造成二進位 Git Conflict 且快速膨脹 Repository 體積。
- **架構解法**：
  1. **維持 `cache://` 儲存**：索引與快照清冊 100% 維持在本地 `.cache/knowledge-db/`，受 `.gitignore` 隔離。
  2. **原生二進位快照 (`unified.meta.bin`)**：透過 Magic `YFP1` 與 Python 原生 `struct` 封裝 `{canonical_path: (mtime, size)}`，讀取耗時 $< 0.1\text{ ms}$。
  3. **JIT 查詢時智能感知**：在 `engine.search()` 入口呼叫 `os.scandir` 比對檔案系統 stat（耗時 $2\sim 3\text{ ms}$）。若發現 1+ 個檔案異動，自動於背景執行熱重建並向 `sys.stderr` 輸出簡明提示。
- **效益與驗證**：
  - 徹底根絕異地代碼過期問題，無論開發者如何切換分支或修改代碼，搜尋永遠 100% 最新。
  - 不污染 `--json` 結構化輸出，兼顧極致效能與開發體驗。

