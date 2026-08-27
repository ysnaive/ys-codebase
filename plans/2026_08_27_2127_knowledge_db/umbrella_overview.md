# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：knowledge-db 模組開發 (Knowledge Database Module)  
> 建立日期：2026-08-27  
> 主計畫目錄：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：`Planning`  
> 模板版本：v1.1  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：為 YS-Codebase 工具庫體系構建全新的知識庫模組 `knowledge-db`，提供資料庫空間管理、多來源語意打包與高效語意化檢索能力。
- **架構邊界**：模組源碼位於 `source/knowledge-db/`，遵循 YSCB 模組工程規範、2x2 組態矩陣與虛擬沙盒跑測流水線。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_space_management_and_schema` | Full Track | `In Progress` | **空間管理與資料架構**：模組骨架、UnifiedSymbol Schema、SpaceManager 多空間定義、2x2 組態矩陣、SHA1+mtime 增量指紋比對與 VFS 空間存儲。 |
| **sub_02** | `sub_02_parsers_and_semantic_bundler` | Full Track | `Pending` | **多語言解析與語意打包**：ParserRegistry 動態外掛介面、Python/Markdown/Cpp/CSharp 多語言解析器、SemanticBundler 打包與解包引擎。 |
| **sub_03** | `sub_03_tokenizer_thesaurus_and_bm25_retrieval` | Full Track | `Pending` | **分詞同義詞與檢索引擎**：CodeTokenizer 混合分詞、雙層 Thesaurus 同義詞合併、倒排索引構建、多欄位加權 BM25 評分與 QueryFilter 過濾。 |
| **sub_04** | `sub_04_cli_sdk_and_workflow_interlock` | Full Track | `Pending` | **CLI 工具鏈與生態整合**：KnowledgeEngine 門面 API、yscb.py knowledge-db 完整 CLI 命令、agents-workflow 注入與安裝 Hook 連動。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (Phase 0 / R01)**：完成 R01 專題架構調研、四大維度拆分與子計畫矩陣規劃。
- [ ] **里程碑 2 (sub_01)**：完成空間管理、Schema 模型、2x2 組態與增量指紋比對。
- [ ] **里程碑 3 (sub_02)**：完成多語言解析器外掛體系與 SemanticBundler 打包解包引擎。
- [ ] **里程碑 4 (sub_03)**：完成分詞、雙層同義詞擴展與多欄位加權 BM25 語意檢索引擎。
- [ ] **里程碑 5 (sub_04)**：完成 CLI 路由器、SDK 統一門面、agents-workflow 連動與全庫沙盒測試。

---

## 4. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 開立分類型主計畫**：開立 Umbrella 主計畫 `plans://2026_08_27_2127_knowledge_db/`，統籌空間定義、語意打包與語意搜尋系列子計畫。
- **[UMBRELLA:DR-02] 產出 R01 深度調研與四大維度拆分**：確立全系統四大維度（空間管理、解析打包、檢索引擎、CLI/生態），並規劃 sub_01 ~ sub_04 四大 Full Track 循序推進路線。
