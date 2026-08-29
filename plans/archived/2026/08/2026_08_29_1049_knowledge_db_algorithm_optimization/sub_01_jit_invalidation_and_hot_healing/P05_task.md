# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_jit_invalidation_and_hot_healing  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1049_knowledge_db_algorithm_optimization`  
> 狀態：In Progress  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：在 `scanner.py` 實作 `BinarySnapshotManager`（`YFP1` 原生二進位快照讀寫）與全域聯集 `mtime` 極速變更嗅探方法 `check_invalidation()`。
- [x] **TASK-02**：在 `schema.py` 與 `retrieval.py` 擴充 `UnifiedSymbol` 與 `Posting` 支援多空間標籤清單 (`spaces: List[str]`)。
- [x] **TASK-03**：在 `bundler.py` 實作 `bundle_union()`，對全專案空間聯集進行實體檔案去重掃描，並注入符號空間標籤。
- [x] **TASK-04**：在 `retrieval.py` 實作 `InvertedIndex.build_unified()` 與 `BM25Engine.search()` 空間標籤過濾。
- [x] **TASK-05**：在 `engine.py` 重構 `search()`，串聯 JIT 快篩、背景熱自愈、`sys.stderr` 提示與單一 `unified.index.bin.gz` 載入流水線。
- [x] **TASK-06**：在 `cli.py` 增加 `--no-auto-rebuild` / `-n` 參數控制。
- [x] **TASK-07**：撰寫全新測試套件 `tests/test_jit_hot_healing.py` 並執行全生態系回歸測試。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
