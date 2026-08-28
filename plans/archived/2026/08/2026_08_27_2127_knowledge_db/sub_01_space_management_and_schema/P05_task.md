# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：In Progress  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (基礎例外定義)**：實作 `source/knowledge-db/knowledge_db/exceptions.py`，定義 `KnowledgeDBError` 及其子類。
- [x] **TASK-02 (核心資料模型)**：實作 `source/knowledge-db/knowledge_db/schema.py`，包含 `SymbolKind`、`LanguageType`、`SpaceOrigin`、`MemberInfo`、`UnifiedSymbol`（SHA1 ID 計算）、`SpaceConfig`（預設 include all 邏輯）、`ThesaurusConfig`。
- [x] **TASK-03 (空間管理與聚合)**：實作 `source/knowledge-db/knowledge_db/space.py`，提供 `SpaceManager` 雙軌聚合、優先權覆蓋 (`Local` > `Project` > `Contributed`)、全空間聯集 (`get_union_spaces`)、語意 URI 解算與 VFS 目錄定位。
- [x] **TASK-04 (雙階增量比對引擎)**：實作 `source/knowledge-db/knowledge_db/scanner.py`，包含 `FileFingerprint`、`ScanDiffResult`、`FingerprintScanner`（Stage 1 mtime+size 初篩 + Stage 2 SHA1 校驗、全空間聯集掃描、快取損毀自癒與原子寫入）。
- [x] **TASK-05 (模組骨架與元數據)**：建立 `source/knowledge-db/manifest.json`、`config.project.json`、`contributes.format.md`、`scripts/__init__.py`、`scripts/cli.py` 與 `knowledge_db/__init__.py`。
- [x] **TASK-06 (單元測試套件)**：實作 `source/knowledge-db/tests/` 套件（`test_schema.py`, `test_space.py`, `test_scanner.py`），繼承 `YSCBTestCase` 覆蓋 FT-01~09、ET-01~03 與 RT-01。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
