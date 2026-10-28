---
name: knowledge-db-search
description: 透過 knowledge-db CLI (search / callers / callees / impact) 檢索專案文檔與程式碼 AST 切片、查閱符號簽名、追蹤上下游調用圖譜並輸出重構影響半徑分析。觸發情境：探索未知程式碼或知識庫文檔路徑、理解業務邏輯、查詢函式被誰呼叫 (callers) 或呼叫了誰 (callees)、評估修改影響範圍 (impact) 或準備調用原生檔案讀取與搜尋工具前。排除情境：已知單一明確檔案路徑且僅需進行局部字串精確替換、修改或撰寫系統知識庫文檔（改用 documentation）。
---

# 知識庫語意檢索與代碼探索指南 (Knowledge-DB Search & Exploration Guide)

本手冊定義 YSCB 專案中代碼閱讀、架構探索、調用圖譜與重構影響面分析之「**二階段漏斗檢索模型（Two-Stage Funnel Retrieval）**」與防呆紀律。Agent 執行檢索時建議使用 `--json`，並依目標規模分流「無 `-s` 大綱定位」與「帶 `-s` 精準切片 / 原生行號區段讀取」。

---

## 1. 目標導向工具分流矩陣 (Outcome-Driven Tool Routing)

| 行為目標 | 唯一指定指令 (Agent 建議 `--json`) | 授權邊界與守門規範 |
| :--- | :--- | :--- |
| **Stage 1：探索定位 / 查簽名 / 查大類別** | `python __${project://yscb.py}__ knowledge-db search <query> --limit=10 --json` | • **預設第一反射（無 `-s` 輕量大綱模式）**：毫秒級取得精確 `file_path`、`line_number`~`end_line` 與 `signature`（單次輸出 `< 2 KB`，杜絕大類別 JSON 切片溢位）。<br/>• **Stage 2 定點精讀**：取得 `(file_path, line_number, end_line)` 後，直接以各環境之**原生檔案讀取工具（指定起訖行號區段，單次建議 $\le 150$ 行）**讀取乾淨程式碼。 |
| **讀取單一小型函式 / Markdown 段落切片** | `python __${project://yscb.py}__ knowledge-db search <query> --limit=5 --json -s` | • 僅於確定目標為單一小型方法（`< 40` 行）或 `--ftype=md` 文檔段落時加帶 `-s`（CLI 內建預設 `--max-snippet-lines=40` 自動截斷保護）。<br/>• [!] 嚴禁對大型類別或未知廣域關鍵字盲目連發 `-s`。 |
| **排查誰調用了我 (上游)** | `python __${project://yscb.py}__ knowledge-db callers <symbol> --json [-s]` | 輸出目標符號與所有跨空間調用點行號（加 `-s` 可附帶上下 5 行調用點切片）；修改公開 API 簽名前強制執行。 |
| **排查我調用了誰 (下游)** | `python __${project://yscb.py}__ knowledge-db callees <symbol> --json [-s]` | 輸出子組件依賴清單與調用點行號。 |
| **重構影響半徑評估 (多階拓撲)** | `python __${project://yscb.py}__ knowledge-db impact <symbol> --depth=N --json` | 輸出多階層擴散拓撲 (Layers 1~N)。 |
| **代碼精確替換 / 單檔定位行號** | 各環境之原生文字搜尋工具 (如 Grep/Search 系列) | [!] **僅限 SearchPath 為單一具體檔案路徑** (Single File Path) 且已知替換目標時使用；**絕對禁止以目錄或全專案為 SearchPath 進行跨檔廣搜**！ |

### [!] 常見探索意圖與反模式對照 (Anti-Patterns vs Correct Patterns)

| 業務意圖 | [!] 絕對禁止之直覺誤用 (Anti-Pattern) | [PASS] 唯一正確指令 (Correct Pattern) |
| :--- | :--- | :--- |
| **查符號/函式被誰調用 (Who calls me)** | 原生跨檔文字搜尋工具廣搜函式名 | `python __${project://yscb.py}__ knowledge-db callers <symbol> --json -s` |
| **查函式內部調用了誰 (Whom do I call)** | 原生讀取工具盲目翻讀整個檔案原始碼 | `python __${project://yscb.py}__ knowledge-db callees <symbol> --json` |
| **找特定模組、測試或大型類別** | 原生跨檔搜尋或對大類別執行 `search --json -s` 造成數萬字元溢位 | 先 `search '<topic/class>' --limit=10 --json` 拿行號 $\rightarrow$ 再用原生檔案讀取工具指定起訖行號精讀 |
| **探索架構、業務邏輯或概念** | 原生文字廣搜 + 逐檔全量翻讀 | 先 `search '<領域詞>' --ftype=md --json -s` 讀文檔切片 $\rightarrow$ 再 `search '<簽名詞>' --json` 定位代碼行號 |

---

## 2. 已註冊之知識庫空間清單 (Registered Knowledge Spaces)

透過 `--space=<name>` 可將檢索與調用排查精確限制於特定領域空間：

<!-- YSCB_KNOWLEDGE_DB_SPACE_BEGIN -->
`__@{KNOWLEDGE_DB_SPACE}__`
<!-- YSCB_KNOWLEDGE_DB_SPACE_END -->

---

## 3. 構詞公式與兩階段分流 (Query Formulation & Routing)

- **三維語意構詞**：$\text{Query} = \text{[領域概念/簽名]} + \text{[架構機制/情境]} + \text{[核心動詞]}$$  
  通用函式名（如 `resolve`、`update`）必須附加業務詞（例：`search 'resolve 佔位符 拓撲' --json -s`）以過濾同名簽名。
- **兩階段 `--ftype` 分流**：
  - **Phase A (宏觀文檔脈絡)**：`python __${project://yscb.py}__ knowledge-db search '<情境詞組>' --ftype=md --limit=5 --json -s`
  - **Phase B (微觀程式碼定位與精讀)**：先執行 `python __${project://yscb.py}__ knowledge-db search '<簽名詞 業務詞>' --ftype=c,cpp,py,cs --limit=10 --json` 取得精確檔案與起訖行號，再以各環境之原生檔案讀取工具（帶起訖行號參數）定點讀取目標區段。

---

## [GUARD] 4. 檢索防呆阻斷鐵律 (Guardrails)

1. **二階段漏斗第一反射與鏈式盲讀阻斷**：探索未知代碼強制以無 `-s` 之 `search --limit=10 --json` 為第一反射取得座標，隨後以原生檔案讀取工具依行號區段定點精讀；排查調用與影響面強制以 `callers --json` / `impact --json` 為第一反射；嚴禁未經檢索定位即盲目翻讀多份源碼檔案或以原生搜尋工具跨檔廣搜。
2. **禁止單行串接過多檢索指令與嚴禁讀取截斷暫存檔 (`JSON Snippet Overflow Guard`)**：
   - 單次終端命令執行最多僅允許以 `&&` / `;` 串接 **2~3 個無 `-s` 的輕量查詢**；若加帶 `-s` 檢視切片，**單次命令列僅限執行 1 個查詢且必須搭配 `--limit=5`**。
   - 若因查詢範圍過廣導致終端輸出被宿主環境截斷並轉存至超長輸出暫存檔（如 `output.txt` 等），**絕對禁止調用原生檔案讀取工具去讀取該截斷暫存檔**（避免數萬 Token 的原始 JSON 污染上下文快取）；應立即縮小查詢關鍵字、移除 `-s` 或加上 `--limit=5` 重新查詢。
3. **嚴禁憑命名空間或命名慣例盲猜路徑讀檔**：**絕對禁止憑模組／命名空間（Namespace / Package）階層或命名慣例（如 `_` 與 `.` 分隔符、`test_*` 檔名組合）臆測實體檔案路徑並直接調用原生檔案讀取工具**；凡當輪尚未確認確切路徑之程式碼或測試檔（包含預設排除於 `source` 索引外之 `tests/` 目錄），首次讀取前必須先透過 `knowledge-db search` 或單次目錄列舉確認真實路徑。
4. **非索引資源檔（Non-Code/MD Assets）定位防呆**：針對不屬於 `code`/`md` 索引範圍之測試資料、組態或靜態資源檔案，應先以 `knowledge-db search` 檢索引用該資源之程式碼符號，或對目標資料夾執行單次目錄列舉取得確切清單，**嚴禁以原生檔案讀取工具進行路徑排列組合盲猜窮舉**。
5. **阻斷同義詞抖動重搜**：同一目標連續重搜不得超過 2 次；切片缺行定點補讀限原範圍 + 最多 30 行，嚴禁將 Search 當捲軸。
6. **新概念主動補足**：遭遇未知協議或名詞即刻檢索，嚴禁憑字面臆測。
7. **Docstring 註解保護**：重構或新增 Public API 時，嚴禁刪減或破壞標準介面註解結構。

---

## 5. 常用 CLI 速查 (Cheatsheet)

```bash
# 1. 內文瀏覽檢索 (帶 AST 切片)
python __${project://yscb.py}__ knowledge-db search '編譯 佔位符 resolve' --json -s

# 2. 符號大綱檢索 (無切片)
python __${project://yscb.py}__ knowledge-db search 'HybridSearchEngine' --json

# 3. 查上游調用者 (Who calls me)
python __${project://yscb.py}__ knowledge-db callers resolve_stage2_uri --json -s

# 4. 查下游被調用者 (Whom do I call)
python __${project://yscb.py}__ knowledge-db callees compile_stage1 --json -s

# 5. 評估多階重構影響面
python __${project://yscb.py}__ knowledge-db impact ReleasePublisher --depth=2 --json

# 6. 檢視空間與索引狀態
python __${project://yscb.py}__ knowledge-db status
```
