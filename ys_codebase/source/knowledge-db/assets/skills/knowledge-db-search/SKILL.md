---
name: knowledge-db-search
description: 透過 knowledge-db search 與 ast (outline/callers/callees/impact) 檢索文檔與程式碼、查閱單檔結構大綱與追蹤呼叫拓撲。觸發情境：探索未知程式碼或文檔路徑、查閱檔案類別與成員簽名行號、查詢上下游呼叫關係、評估修改影響半徑或調用原生搜尋讀檔工具前。
---
<!-- yscb:ignore:begin -->
維護者註記：本技能為檢索與結構推理之單一入口，整合 Layer 3 `knowledge-db`（語意/關鍵字搜尋）與 Layer 2 `ast`（確定性單檔結構大綱與雙向呼叫拓撲）。已註冊空間明細下沉至 `./references/registered-spaces.md` 按需查閱，避免常駐佔用主檔 Context。
<!-- yscb:ignore:end -->
# 知識庫與 AST 結構拓撲檢索 (`knowledge-db-search`)

透過 `knowledge-db`（混合語意與關鍵字檢索）與 `ast`（確定性單檔結構大綱與雙向呼叫拓撲）執行**三階段漏斗檢索**：先以搜尋定位檔案，再以 `ast outline` 掌握單檔結構與行號區間，最後用原生工具精準區段讀取，嚴格節約 Context Token。

## 1. 意圖路由與三階段漏斗決策表 (Intent Routing Matrix)

| 探索階段 / 意圖 | 標準動作（單一反射） | 禁止事項 |
| :--- | :--- | :--- |
| **Stage 1：探索未知文檔 (`docs/`、`plans/`)** | `python __${project://yscb.py}__ knowledge-db search "<query>" --ftype=md --limit=10` | 嚴禁未檢索直接盲讀或遍歷 `docs/` |
| **Stage 1：探索未知程式碼與符號座標** | `python __${project://yscb.py}__ knowledge-db search "<query>" --limit=10` | 嚴禁直接用 `grep` 大海撈針或無範圍全檔讀取 |
| **Stage 1.5：已知檔案查結構大綱與行號區間** | `python __${project://yscb.py}__ ast outline <file> [--public\|--private\|--static\|--non-static\|--methods\|--fields\|--types\|--merged]` | 嚴禁對大型源碼檔未看 `outline` 即盲猜行號區間；注意輸出之 `[Partial Siblings]` 跨分部姊妹檔提示 |
| **Stage 2：精準閱讀目標實作區段** | 依 `search` 或 `ast outline` 取得之 `line_number` / `Lstart-Lend`，調用 `__%{agent_tool.file_read_range}__` 讀取目標區段（建議單次 $\le 160$ 行） | 嚴禁無行號區間全檔傾倒；嚴禁重複呼叫 `search -s` 拼湊長文 |
| **追蹤誰呼叫了目標符號 (Callers)** | `python __${project://yscb.py}__ ast callers "<symbol>" [-s]` | 嚴禁僅靠純文字搜尋函式名猜測呼叫方 |
| **追蹤目標符號呼叫了誰 (Callees)** | `python __${project://yscb.py}__ ast callees "<symbol>" [-s]` | 嚴禁逐檔手動展開內部呼叫鏈 |
| **評估修改爆炸半徑 (Impact)** | `python __${project://yscb.py}__ ast impact "<symbol>" --depth=2` | 嚴禁修改核心介面或資料結構前跳過影響面評估 |
| **單檔精確字串定位 / 替換前確認** | 各環境之 `__%{agent_tool.file_grep_single}__`（限定單一檔案路徑） | 嚴禁以目錄或全專案為 SearchPath 進行跨檔廣搜 |

## 2. 指令參數與進階過濾速查

- **全文與語意搜尋 (`knowledge-db search`)**：
  - `python __${project://yscb.py}__ knowledge-db search "<query>" [--space=<name>] [--ftype=<ext>] [--limit=10] [-s] [--context-lines=5]`
  - 多關鍵詞請放於同一次查詢字串內，系統自動執行 BM25 + 向量混合 RRF 排序與複合詞覆蓋加權（內建 8,000 字元自適應預算與冗餘切片去重）。
  - **空間過濾按需下沉**：預設跨全空間聯集檢索，**無需指定 `--space`**；唯有當全空間搜尋結果混雜過多跨領域雜訊、或無法取得預期資料需深入區分檢索空間時，再按需查閱 [`references/registered-spaces.md`](./references/registered-spaces.md) 了解各空間涵蓋範圍並加上 `--space=<name>`。
- **單檔結構大綱與正交過濾 (`ast outline`)**：
  - `python __${project://yscb.py}__ ast outline <file_or_uri> [--merged]`
  - **三維度正交過濾（組間 AND、組內 OR）**：
    - 可見度：`--public`、`--protected`、`--internal`、`--private`、`--non-private`
    - 綁定類型：`--static`、`--non-static`
    - 成員種類：`--methods`（方法/函式/建構子）、`--fields`（欄位/屬性）、`--types`（僅顯示類別/結構/介面/列舉容器）
  - **跨分部類別 (`partial class`)**：預設僅顯示該物理檔案定義之成員，並自動附帶 `[Partial Siblings]` 列出同型別其餘分部檔案；加 `--merged` 可檢視跨檔邏輯聚合完整成員表。
- **確定性符號定址與同名異載 (`ast callers | callees | impact`)**：
  - 支援 `[kind] [scope.]name[(param_types...)]` 語法（如 `"class Engine"`、`"Window.Open"`、`"Window.Open(string, int)"`）。
  - **同名異載 (Method Overloads)**：查詢 `"Class.Method"`（不含參數）若匹配同一父型別下的多個重載，預設自動將同型別所有重載視為同一群組展開聯集拓撲並標註 `matched_overloads`；跨不同父型別同名符號則返回結構化歧義候選清單。

## 3. 常見踩坑指南 (Gotchas)

- **指令路由分流**：全文/語意搜尋位於 `yscb.py knowledge-db search`；單檔大綱與呼叫拓撲 (`outline` / `callers` / `callees` / `impact`) 統一路由至 `yscb.py ast <subcmd>`。
- **嚴禁讀取因 `-s` 輸出過大而被宿主截斷轉存的暫存檔（如 `output.txt`）**：一旦發生截斷，應立即縮小查詢關鍵字、移除 `-s` 或改用 `ast outline` + 區段讀檔。
- **JIT 雙水位線熱自癒**：`file-space` $\to$ `ast` $\to$ `knowledge-db` 具備 Pull-Based JIT 自動增量同步，日常修改程式碼後直接查詢即可（0 手動 `index`）。
- **嚴禁繞過 Venv**：一律透過 `python __${project://yscb.py}__` 執行，嚴禁直接呼叫系統裸 `python` 載入模組內部腳本。
