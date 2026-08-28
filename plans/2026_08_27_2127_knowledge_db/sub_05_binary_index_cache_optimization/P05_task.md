# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Completed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (InvertedIndex 與 Posting 重構)**：重構 `source/knowledge-db/knowledge_db/retrieval.py`，抽離 `symbols` 符號池，實作 `save_binary` 與 `load_binary`，適配 `BM25Engine.search`。
- [x] **TASK-02 (KnowledgeEngine 快取升級與舊檔清理)**：修改 `source/knowledge-db/knowledge_db/engine.py` 與 `scripts/cli.py`，將索引快取路徑更新為 `.index.bin.gz`，升級 `status` 與 `clean`，並清除磁碟上舊的 55 MB `.index.json`。
- [x] **TASK-03 (單元與效能測試套件更新)**：更新 `test_retrieval.py` 與 `test_engine.py`，驗證 FT-01~06、ET-01 與 RT-01 全數通過。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依循 P04 拓撲實作完成 |
