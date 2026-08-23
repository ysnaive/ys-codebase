# 語意化需求書 (Semantic Requirements)

> 功能名稱：語意化 Codebase 知識庫模組開發 (`knowledge-db`)  
> 建立日期：2026-08-23  
> 計畫類型：Feature  
> 所屬主計畫：無  
> 狀態：Discussing  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Feature] 語意化需求

### 使用情境 (User / Developer Scenarios)

**情境 1：AI Agent / 開發者透過語意或自然語言快速精準定位專案符號與文檔**
在龐大的 Codebase 中，開發者或 AI Agent 想查找「狀態機更新機制」、「底盤 PID 控制」、「遙測通訊協議」或「某巨集註冊之 Opcode」時，無需手動全文搜尋 (grep) 大量無關檔案。透過語意知識庫 CLI 或 API，能夠直接獲得高相關度的符號模型（包含類別名稱、命名空間、檔案行號、繼承鏈、公開方法成員、Docstring 與命中依據）。採用複合加權評分（Hybrid Scoring），精確類別名稱 100% 置頂，自然語言句子享受高品質 BM25 多欄位排序。

**情境 2：毫秒級增量索引維護與 100% 離線純標準庫運作**
在開發過程中，程式碼頻繁變更。知識庫模組透過檔案 SHA1 與 mtime 增量比對，在幾毫秒內僅重新解析受影響檔案並更新快取索引（`cache.json`），且整體引擎維持 Zero External Dependency（純 Python 3 標準庫），無需安裝重量級外部向量庫或依賴聯網 LLM Embedding API。

**情境 3：動態可插拔解析器 (Pluggable Parsers) 與雙層領域同義詞 (Thesaurus)**
模組內建 C++、C、C#、Python 與 Markdown 五大語言解析器，支援專案宣告特定巨集正則（如 `REGISTER_.*`）。同時提供動態解析器擴充接口（允許下游模組透過 `contributes.knowledge-db.parsers` 註冊新語言解析器）。同義詞庫採用雙層架構：模組內建通用軟體工程詞庫，並與專案特化 `thesaurus.json` 深度增量合併。

**情境 4：與 YS-Codebase 工具庫體系無縫整合與全面連動 (Dogfooding & Interlock)**
作為官方一等模組 (`knowledge-db`)，遵循 2×2 設定矩陣 (`config.project.json` / `config.local.json`)、統一 CLI 調度 (`python yscb_cli.py knowledge-db search/index/status/export`)。在安裝期透過生命週期 Hook (`_on_modules_changed.py`) 自動感應專案更新並執行增量索引，並透過 `contributes.agents-workflow` 向 `ContextInit` 與 `Research` 等 SOP 自動注入知識庫查詢指引。

---

### API 使用者心智 (Developer Mental Model)

```python
# 1. 透過 Core SDK / CLI 調度語意檢索
from yscb_core import ProjectContext
from knowledge_db import KnowledgeEngine

engine = KnowledgeEngine(project_root=ProjectContext.get_project_root())
results = engine.search("狀態機的更新頻率", top_k=5, kind="class", lang="cpp")

for r in results:
    print(f"[{r.score:.2f}] {r.symbol.name} ({r.symbol.file_path}:{r.symbol.line_number})")
    print(f"  • 命中原因: {r.match_reason}")
    print(f"  • 公開成員: {[m.name for m in r.symbol.public_members]}")

# 2. 終端 CLI 使用方式
# python yscb_cli.py knowledge-db search -q "遙測封包" --format human
# python yscb_cli.py knowledge-db index --update
# python yscb_cli.py knowledge-db status
# python yscb_cli.py knowledge-db export-docs
```

---

### 明確的非目標 (Explicit Out of Scope)

- **不引入外部深度學習 / 神經網路向量模型**：維持 100% 免安裝環境依賴，不依賴 `pytorch`, `onnx`, `chromadb` 等重型函式庫。
- **不取代完整編譯器 Language Server Protocol (LSP)**：定位為跨語言輕量級語意代碼圖譜與 BM25 檢索，不做即時語法診斷或類型推斷。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | 模組命名定名？ | ✅ 已解決 | 開發者明確指示定名為 **`knowledge-db`**。 |
| 2 | 語言解析器架構與擴充性？ | ✅ 已解決 | 採動態外掛解析器介面 (Pluggable Parser Interface)，內建 C/C++/C#/Python/Markdown，支援 `contributes.knowledge-db.parsers` 擴充與專案自訂巨集正則。 |
| 3 | 同義詞詞庫 (Thesaurus) 架構？ | ✅ 已解決 | 雙層同義詞架構：模組內建通用中英詞庫 + 專案 `config.project.json`/`thesaurus.json` 深度增量合併。 |
| 4 | 檢索評分與排序策略？ | ✅ 已解決 | 複合加權評分 (Hybrid Scoring)：BM25 多欄位評分 + Exact Name 精確匹配置頂 Boost。 |
| 5 | 與 `agents-workflow` 安裝期連動？ | ✅ 已解決 | 全面連動：`sop_patches` 注入 `ContextInit` & `Research`、`sop_extensions` 提供擴充、Hook 自動觸發增量索引更新。 |
| 6 | 快取檔案儲存位置？ | 🔄 延伸議題 (保留) | 預設為專案根目錄 `.yscb_cache/knowledge_db_cache.json`，並支援在 `config.project.json` 中配置自訂路徑。 |

---

## 討論結束確認 (Discussion Close Gate)

- [ ] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。

---

## 三大分流層級判定 (Three-Tier Phasing Matrix)

| 分流層級 | 判定結果 | 適用場景與判定理由 |
| :--- | :---: | :--- |
| **Level 0：Fast Track** | ☐ | 修改檔案 ≤ 2、不變更 Public API、無跨模組依賴 |
| **Level 1：Full Track** | ☐ | 單一功能語意、單一模組的新增或重構（推薦：全新一等模組開發） |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☐ | 多個功能語意/情境、跨模組大型架構重構 |
