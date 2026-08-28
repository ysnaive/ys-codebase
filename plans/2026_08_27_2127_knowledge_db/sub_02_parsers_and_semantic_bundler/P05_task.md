# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge-db 子計畫 02: 多語言解析與語意打包 (Parsers & Semantic Bundler)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：In Progress  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (解析器基礎抽象)**：實作 `source/knowledge-db/knowledge_db/parsers/base.py`，定義 `BaseParser` 抽象類別。
- [x] **TASK-02 (四大多元解析器實作)**：
  - 實作 `source/knowledge-db/knowledge_db/parsers/python_parser.py` (AST 語法樹解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/markdown_parser.py` (文檔狀態機解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/cpp_parser.py` (C/C++ 類別/巨集狀態機解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/csharp_parser.py` (C# 類別/XML Doc 狀態機解析)
- [x] **TASK-03 (解析器註冊中心)**：實作 `source/knowledge-db/knowledge_db/parsers/registry.py` 與 `parsers/__init__.py`，提供動態註冊與分發調度。
- [x] **TASK-04 (語意打包引擎)**：實作 `source/knowledge-db/knowledge_db/bundler.py`，包含 `SemanticBundle` 資料模型與 `SemanticBundler` 打包/導出/導入引擎。
- [x] **TASK-05 (入口與元數據更新)**：更新 `source/knowledge-db/scripts/cli.py`（擴充 `bundle` 指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [x] **TASK-06 (單元測試套件)**：實作 `tests/test_parsers.py` 與 `tests/test_bundler.py`，覆蓋 FT-01~08、ET-01 與 RT-01。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
