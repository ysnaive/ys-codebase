# Knowledge Database 模組手冊 (Knowledge-DB Overview)

> 模組名稱：`knowledge-db`  
> 模組版本：`0.1.0.0`  
> 職責定位：YS-Codebase 專案代碼與文檔語意知識庫基礎設施，提供多來源空間宣告、雙軌聚合、雙階增量指紋比對與語意搜尋服務。

---

## 1. 模組定位與願景 (Vision & Goals)

`knowledge-db` 模組旨在為 YS-Codebase 生態體系建立高效、零外部相依、高強韌度的知識庫核心設施。主要能力包括：
- **多空間治理 (Space Management)**：支援多模組聯動注入 (`module://<donor>/contributes.knowledge-db.json`) 與專案 2x2 組態矩陣宣告。
- **全空間聯集處理 (Union Scope)**：無單一 `default_space` 強制約定，全系統以所有有效空間之聯集作為全域處理範圍。
- **雙階增量指紋比對 (Fingerprint Engine)**：以 `mtime`+`size` 快速初篩 (Stage 1) 與 `SHA1` 精確校驗 (Stage 2) 大幅縮短掃描與索引時間。
- **多語言解析與語意檢索**：支援 Python、Markdown、C++、C# 等語言符號提取與 BM25 語意檢索 (留待後續子計畫逐步擴充)。

---

## 2. 子計畫演進與里程碑架構 (Sub-Plans Roadmap)

| 子計畫編號 | 標題 | 狀態 | 核心範疇 |
| :---: | :--- | :---: | :--- |
| **sub_01** | **空間管理與資料架構** | **Completed** | 模組骨架、UnifiedSymbol Schema、SpaceManager 雙軌聚合、雙階增量指紋比對與原子持久化。 |
| **sub_02** | **多語言解析與語意打包** | **Completed** | ParserRegistry 動態外掛、Python/Markdown/Cpp/CSharp 解析器、SemanticBundler 打包引擎。 |
| **sub_03** | **分詞同義詞與檢索引擎** | *Planning* | CodeTokenizer 混合分詞、雙層 Thesaurus 同義詞擴展、倒排索引與 BM25 評分。 |
| **sub_04** | **CLI 工具鏈與生態整合** | *Pending* | KnowledgeEngine 門面 API、完整 CLI 指令集與 agents-workflow 生態連動。 |

---

## 3. CLI 快速上手 (Quick Start)

```bash
# 查看所有已註冊空間與快取狀態
python yscb.py knowledge-db status

# 執行全空間聯集增量指紋掃描
python yscb.py knowledge-db scan --all

# 執行特定空間強制全量掃描
python yscb.py knowledge-db scan project_main --force

# 執行空間語意符號打包與 Bundle 導出
python yscb.py knowledge-db bundle project_main
```

---

## 4. 相關技術文件指針

- 📐 **架構設計**：[architecture.md](./architecture.md)
- 🔌 **擴充點注入指南**：[contributes_guide.md](./contributes_guide.md)
- 🧩 **多語言解析器指南**：[parsers.md](./parsers.md)
- 📦 **語意打包引擎指南**：[bundler.md](./bundler.md)
