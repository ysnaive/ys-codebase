# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01~FR-04 在 API 規格書（`scanner.py`、`bundler.py`、`retrieval.py`、`engine.py`、`cli.py`）中有 100% 嚴密對應。
- [x] **邊界防護**：EC-01 (快照缺失)、EC-02 (二進位損毀)、EC-03 (檔案刪除更名)、EC-04 (空專案) 均有完備自癒與防禦策略。
- [x] **依賴純淨**：100% 採用純 Python 原生標準庫（`struct`, `gzip`, `os`, `hashlib`），0 外部相依，符合 NFR-01~03 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 4** | `docs/knowledge-db/RETRIEVAL_ARCHITECTURE.md` | Modify | 補充「全域聯集單一索引架構」與「JIT 查詢時智能變更感知與熱自愈機制」架構章節 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當多行程（Multi-Process）或多終端同時發起 `search` 且同時檢測到代碼變更時，是否會發生二進位索引的並發寫入衝突 (Race Condition)？  
> 💡 **防護解法**：寫入二進位快照 (`unified.meta.bin`) 與二進位索引 (`unified.index.bin.gz`) 時，100% 透過 `tempfile` 在目標目錄建立暫存檔並使用 `os.replace` 原子替換。POSIX 與 Windows 檔案系統保證 `os.replace` 具有原子語意，讀取端永遠只會讀到完整落地之檔案，絕不讀取到寫入中途的半截資料。

> ❓ **尖銳問題 2**：若專案中包含數千個檔案，JIT 嗅探遍歷是否會拖慢搜尋響應？  
> 💡 **防護解法**：JIT 嗅探只呼叫 `os.scandir` 取得 `st_mtime` 與 `st_size`，**完全不開啟檔案、不讀取內容、不計算 SHA-1**。實測 2,000 檔案規模耗時僅 2~3ms。且在同一 Process 生命週期內，記憶體快照能進一步消除二次磁碟讀取，維持極致流暢度。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `scanner.py` 實作 `BinarySnapshotManager`（`YFP1` 原生二進位讀寫）與全域聯集 `mtime` 極速變更嗅探方法 `check_invalidation()`。
- [ ] **TASK-02**：在 `schema.py` 與 `retrieval.py` 擴充 `UnifiedSymbol` 與 `Posting` 支援多空間標籤清單 (`spaces: List[str]`)。
- [ ] **TASK-03**：在 `bundler.py` 實作 `bundle_union()`，對全專案空間聯集進行實體檔案去重掃描，並注入符號空間標籤。
- [ ] **TASK-04**：在 `retrieval.py` 實作 `InvertedIndex.build_unified()` 與 `BM25Engine.search()` 空間標籤過濾。
- [ ] **TASK-05**：在 `engine.py` 重構 `search()`，串聯 JIT 快篩、背景熱自愈、`sys.stderr` 提示與單一 `unified.index.bin.gz` 載入流水線。
- [ ] **TASK-06**：在 `cli.py` 增加 `--no-auto-rebuild` / `-n` 參數控制。
- [ ] **TASK-07**：撰寫全新測試套件 `tests/test_jit_hot_healing.py` 並執行全生態系回歸測試。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 TASK-01 ~ TASK-07 無環拓撲實作計畫與文檔交付規劃。
- **[P04:DR-02]** 同步定稿 [`P06_test_plan.md`](./P06_test_plan.md) 狀態為 `Confirmed`。
