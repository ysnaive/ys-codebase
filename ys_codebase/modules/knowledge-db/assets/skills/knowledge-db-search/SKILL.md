---
name: knowledge-db-search
description: 知識庫語意檢索與代碼探索指南。當需要搜尋代碼或文檔、理解業務邏輯、查閱符號簽名、追蹤調用關係 (callers/callees)、評估重構影響半徑 (impact) 或進行技術調研時觸發。🚨 絕對禁止對目錄調用 grep_search/search 等原生工具進行跨檔文字廣搜；全庫探索、調用排查與測試搜尋強制以 knowledge-db 指令為唯一第一反射。
---

# 知識庫語意檢索與代碼探索指南 (Knowledge-DB Search & Exploration Guild)

本手冊定義 YSCB 專案中代碼閱讀、架構探索、調用圖譜與重構影響面分析之工具分流矩陣與檢索紀律。Agent 執行檢索時一律使用 `--json`（閱讀切片加帶 `-s`）。

---

## 🎯 1. 目標導向工具分流矩陣 (Outcome-Driven Tool Routing)

| 行為目標 | 唯一指定指令 (Agent 一律 `--json`) | 授權邊界與守門規範 |
| :--- | :--- | :--- |
| **閱讀代碼 / 探索邏輯 / 查簽名** | `python __${project://yscb.py}__ knowledge-db search <query> --json -s` | • 直接取得 AST 代碼切片與 Docstrings。<br/>• 🚨 嚴禁文字搜尋後逐檔翻讀（原生文字搜尋 $\rightarrow$ 原生逐檔翻讀）。<br/>• 💡 切片缺行定點補讀限原範圍 + 最多 30 行（嚴禁整檔翻讀）。 |
| **快速確認符號/檔案存在** | `python __${project://yscb.py}__ knowledge-db search <query> --json` | 預設 Simple 大綱模式，輸出命中檔案、行號與簽名。 |
| **排查誰調用了我 (上游)** | `python __${project://yscb.py}__ knowledge-db callers <symbol> --json -s` | 輸出目標符號、調用點行號與上下 5 行調用代碼切片。 |
| **排查我調用了誰 (下游)** | `python __${project://yscb.py}__ knowledge-db callees <symbol> --json -s` | 輸出子組件依賴清單與調用點代碼切片。 |
| **重構影響半徑評估 (多階拓撲)** | `python __${project://yscb.py}__ knowledge-db impact <symbol> --depth=N --json` | 輸出多階層擴散拓撲 (Layers 1~N)。 |
| **代碼精確替換 / 單檔定位行號** | 各環境之原生文字搜尋工具 (如 Grep/Search 系列) | 🚨 **僅限 SearchPath 為單一具體檔案路徑** (Single File Path) 且已知替換目標時使用；**絕對禁止以目錄或全專案為 SearchPath 進行跨檔廣搜**！ |

### 🚨 常見探索意圖與反模式對照 (Anti-Patterns vs Correct Patterns)

| 業務意圖 | 🚨 絕對禁止之直覺誤用 (Anti-Pattern) | ✅ 唯一正確指令 (Correct Pattern) |
| :--- | :--- | :--- |
| **查符號/函式被誰調用 (Who calls me)** | `grep_search(Query="func", SearchPath="...")` | `python __${project://yscb.py}__ knowledge-db callers <symbol> --json -s` |
| **查函式內部調用了誰 (Whom do I call)** | 翻讀整個檔案原始碼或模糊文字搜尋 | `python __${project://yscb.py}__ knowledge-db callees <symbol> --json -s` |
| **找特定模組、測試或檔案** | `grep_search(Query="file.py", SearchPath="...")` | `python __${project://yscb.py}__ knowledge-db search '<topic/file> test' --json -s` |
| **探索架構、業務邏輯或概念** | `grep_search` 廣搜關鍵字 + 逐檔 `view_file` | `python __${project://yscb.py}__ knowledge-db search '<領域詞 業務詞>' --json -s` |

---

## 📁 2. 已註冊之知識庫空間清單 (Registered Knowledge Spaces)

透過 `--space=<name>` 可將檢索與調用排查精確限制於特定領域空間：

<!-- YSCB_KNOWLEDGE_DB_SPACE_BEGIN -->
`__@{KNOWLEDGE_DB_SPACE}__`
<!-- YSCB_KNOWLEDGE_DB_SPACE_END -->

---

## 🔍 3. 構詞公式與兩階段分流 (Query Formulation & Routing)

- **三維語意構詞**：$\text{Query} = \text{[領域概念/簽名]} + \text{[架構機制/情境]} + \text{[核心動詞]}$$  
  通用函式名（如 `resolve`、`update`）必須附加業務詞（例：`search 'resolve 佔位符 拓撲' --json -s`）以過濾同名簽名。
- **兩階段 `--ftype` 分流**：
  - **Phase A (宏觀文檔脈絡)**：`python __${project://yscb.py}__ knowledge-db search '<情境詞組>' --ftype=md --json -s`
  - **Phase B (微觀程式碼實作)**：`python __${project://yscb.py}__ knowledge-db search '<簽名詞 業務詞>' --ftype=c,cpp,py --json -s`

---

## 🛡️ 4. 檢索防呆阻斷鐵律 (Guardrails)

1. **第一反射與鏈式翻讀阻斷**：探索閱讀強制以 `search --json -s` 為第一反射；排查調用與影響面強制以 `callers --json -s` / `impact --json` 為第一反射；嚴禁未定位行號即盲目調用原生工具讀檔或以原生搜尋工具模糊廣搜。
2. **阻斷同義詞抖動重搜**：同一目標連續重搜不得超過 2 次；切片缺行定點補讀限原範圍 + 最多 30 行，嚴禁將 Search 當捲軸。
3. **新概念主動補足**：遭遇未知協議或名詞即刻檢索，嚴禁憑字面臆測。
4. **Docstring 註解保護**：重構或新增 Public API 時，嚴禁刪減或破壞標準介面註解結構。

---

## ⚡ 5. 常用 CLI 速查 (Cheatsheet)

```bash
# 1. 內文瀏覽檢索 (帶 AST 切片)
python __${project://yscb.py}__ knowledge-db search '編譯 佔位符 resolve' --json -s

# 2. 符號大綱檢索 (無切片)
python __${project://yscb.py}__ knowledge-db search 'ThesaurusEngine' --json

# 3. 查上游調用者 (Who calls me)
python __${project://yscb.py}__ knowledge-db callers resolve_stage2_uri --json -s

# 4. 查下游被調用者 (Whom do I call)
python __${project://yscb.py}__ knowledge-db callees compile_stage1 --json -s

# 5. 評估多階重構影響面
python __${project://yscb.py}__ knowledge-db impact ReleasePublisher --depth=2 --json

# 6. 檢視空間與索引狀態
python __${project://yscb.py}__ knowledge-db status
```
