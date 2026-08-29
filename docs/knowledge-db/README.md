# Knowledge Database 模組手冊 (Knowledge-DB Overview)

> 模組名稱：`knowledge-db`  
> 模組版本：`1.0.0.0`  
> 職責定位：YS-Codebase 專案代碼與文檔語意知識庫基礎設施，提供多來源空間宣告、雙軌聚合、雙階增量指紋比對、多語言 AST/狀態機解析、雙層同義詞擴展與多欄位加權 BM25 語意搜尋服務。

---

## 1. 模組定位與願景 (Vision & Goals)

`knowledge-db` 模組旨在為 YS-Codebase 生態體系建立高效、零外部相依、高強韌度的知識庫核心設施。主要能力包括：
- **多空間治理 (Space Management)**：支援多模組聯動注入 (`module://<donor>/contributes.knowledge-db.json`) 與專案 2x2 組態矩陣宣告。
- **全空間聯集處理 (Union Scope)**：無單一 `default_space` 強制約定，全系統以所有有效空間之聯集作為全域處理範圍。
- **雙階增量指紋比對 (Fingerprint Engine)**：以 `mtime`+`size` 快速初篩 (Stage 1) 與 `SHA1` 精確校驗 (Stage 2) 大幅縮短掃描與索引時間。
- **多語言語意解析 (Multi-Language Parsers)**：支援 Python (原生 AST)、Markdown、C++ (巨集正則)、C# (XML Docs) 等多語言符號提取與 SemanticBundle 打包。
- **混合分詞與語意檢索 (BM25 Retrieval)**：代碼標識符拆解、CJK 2-gram 滑動窗口、18 組軟工同義詞擴展與多欄位加權 BM25 評分（支援 Exact Match 2.0x 置頂加權與自動懶索引）。
- **零外部相依 (Zero External Dependency)**：100% 基於 Python 3.9+ 原生標準庫，跨平台即裝即用。

---

## 2. 子計畫演進與里程碑架構 (Sub-Plans Roadmap)

| 子計畫編號 | 標題 | 狀態 | 核心範疇 |
| :--- : | :--- | :---: | :--- |
| **sub_01** | **空間管理與資料架構** | **Completed** | 模組骨架、UnifiedSymbol Schema、SpaceManager 雙軌聚合、雙階增量指紋比對與原子持久化。 |
| **sub_02** | **多語言解析與語意打包** | **Completed** | ParserRegistry 動態外掛、Python/Markdown/Cpp/CSharp 解析器、SemanticBundler 打包引擎。 |
| **sub_03** | **分詞同義詞與檢索引擎** | **Completed** | CodeTokenizer 混合分詞、雙層 Thesaurus 同義詞擴展、倒排索引與 BM25 評分。 |
| **sub_04** | **CLI 工具鏈與生態整合** | **Completed** | KnowledgeEngine 統一門面 SDK、完整 6 大 CLI 指令集與 agents-workflow 生態連動。 |
| **sub_05** | **倒排索引二進位快取優化** | **Completed** | 符號池抽離去重、原生 Pickle Protocol 5 + Gzip 二進位快取 (`.index.bin.gz`)，體積縮減 99.53% 與讀取提速 40x。 |
| **sub_06** | **雙向 Contributes 聯動與 Space 解耦** | **Completed** | 清空模組預設硬編碼空間、由 `agents-workflow` 宣告貢獻 `docs` 空間、專案特化宣告 `source` 空間，並向工作流注入檢索優先紀律與 JIT 指引。 |
| **sub_07** | **搜尋結果輸出格式優化** | **Completed** | 預設極輕量單行排版 (`#01 path:line`)、詳細模式 (`--detail`, `-d`, `--verbose`) 與結構化模式 (`--json`) 支援。 |
| **sub_09** | **JIT 智能變更感知與全域聯集單一索引** | **Completed** | 全專案空間聯集實體去重 AST 解析、單一全域倒排索引 (`unified.index.bin.gz`)、原生二進位快照 (`unified.meta.bin` Magic `YFP1`) 與 JIT 查詢時智能變更感知熱自愈。 |
| **sub_10** | **Agents-Workflow 注入內容與決策樹優化** | **Completed** | 注入剛性檢索決策樹（簽章/複合詞/語意敘述分流）、確立「定位 ➔ 定向閱讀」非暴力廣蒐哲學，並更新 Phase 0 / Research / Phase 7 JIT 引導資產。 |

---

## 3. CLI 快速上手 (Quick Start)

```bash
# 1. 查看所有已註冊空間、快取與索引狀態
python yscb.py knowledge-db status

# 2. 執行全空間聯集或指定空間增量指紋掃描
python yscb.py knowledge-db scan --all
python yscb.py knowledge-db scan project_main --force

# 3. 執行空間語意符號打包與 Bundle 導出
python yscb.py knowledge-db bundle project_main

# 4. 預先建置並快取空間倒排索引
python yscb.py knowledge-db index --all

# 5. 執行多欄位加權 BM25 語意檢索 (預設為簡易單行排版，支援自動懶建置索引)
python yscb.py knowledge-db search PIDController
python yscb.py knowledge-db search "狀態機更新" --kind=class --limit=5

# 6. 代碼/文檔分流檢索 (--ftype 與 --snippet 預覽代碼區塊與 Docstring 摘要)
python yscb.py knowledge-db search "PIDController" --ftype=c,cpp,py -s
python yscb.py knowledge-db search "開發規範" --ftype=md -s

# 7. 詳細模式 (輸出評分、符號類型、簽名、摘要與命中關鍵詞)
python yscb.py knowledge-db search PIDController --detail
python yscb.py knowledge-db search PIDController -d

# 8. 結構化 JSON 輸出 (供自動化工具鏈解析，包含 snippet 與 code_snippet 欄位)
python yscb.py knowledge-db search PIDController --json
python yscb.py knowledge-db search PIDController -s --json

# 9. 清理特定或全空間之指紋、Bundle 與倒排索引快取
python yscb.py knowledge-db clean --all
```

---

## 4. Python SDK 快速上手 (`KnowledgeEngine`)

```python
from knowledge_db import KnowledgeEngine

# 初始化統一門面 SDK
engine = KnowledgeEngine()

# 1. 檢視系統狀態
status = engine.status()
print("Total spaces:", status["total_spaces"])

# 2. 執行多欄位加權語意搜尋 (未建索引時自動觸發懶索引)
results = engine.search("PID 控制器速度輸出", limit=5)
for res in results:
    sym = res.symbol
    print(f"[{res.score:.2f}] {sym.kind.upper()}: {sym.name} ({sym.file_path}:{sym.line_number})")
    print(f"  簽名: {sym.signature}")
    print(f"  命中: {', '.join(res.matched_terms)}")

# 3. 手動打包或建置索引
engine.bundle(space="project_main")
engine.build_index(space="project_main", force=True)

# 4. 清理快取
engine.clean(space="project_main")
```

---

## 5. 相關技術文件指針

- 📐 **系統架構設計**：[architecture.md](./architecture.md)
- 🔌 **擴充點注入指南**：[contributes_guide.md](./contributes_guide.md)
- 🧩 **多語言解析器指南**：[parsers.md](./parsers.md)
- 📦 **語意打包引擎指南**：[bundler.md](./bundler.md)
- 🔤 **分詞與同義詞指南**：[tokenizer.md](./tokenizer.md)
- 🔍 **語意檢索引擎指南**：[retrieval.md](./retrieval.md)
