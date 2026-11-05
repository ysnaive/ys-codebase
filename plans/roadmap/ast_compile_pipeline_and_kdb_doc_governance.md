# 技術路線圖：AST 無損區段編譯管線、知識庫文檔治理與工作流骨幹正交化架構 (Roadmap)

> 主題：AST 無損區段編譯管線、知識庫文檔治理與工作流骨幹正交化架構 (`ast_compile_pipeline_and_kdb_doc_governance`)  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：`ast`、`knowledge-db`、`agents-workflow`、`server`、`file-space`（跨模組語法樹編譯管線、文檔與術語治理、語言伺服器及工作流骨幹解耦）  
> 前置解鎖條件：完成底層核心與知識庫既有結構優化及深層審計修繕後啟動  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **文檔與規則編譯器職責分散且缺乏通用語法樹底座**：工作流資產編譯器目前內嵌於 `agents-workflow` 內部，採用基於正則表達式與行掃描之特化管線，缺乏帶精確來源座標溯源（`SourceOrigin`）之無損具象語法樹（Lossless CST）與通用多產物圖譜（`ArtifactGraph`），無法由其他模組複用或擴充編譯規則。
  - **系統文檔（`docs/`）治理職責錯置與原始碼錨點易腐敗**：`docs/` 知識庫規範（如 `ARCHITECTURE.md`、`README.md`、`DESIGN_NOTES.md` 與 `documentation` 技能）目前寄居於 `agents-workflow`；同時 `DESIGN_NOTES.md` 等設計文檔在引用原始碼區段、符號簽名或 Docstring 時缺乏動態 AST 綁定與編譯期校驗，極易隨代碼演進產生行號漂移與死鏈。
  - **檢索廣度展開後缺乏精準術語字典閉環**：Agent 與開發者透過 `knowledge-db search` 展開廣度檢索時，頻繁遭遇專案領域專有名詞、核心縮寫或架構決策代號，卻缺乏如 `kdb means "<專有名詞>"` 之秒級精準定義與關聯查閱能力，被迫反覆發起廣域搜尋並消耗大量上下文。
  - **開發視角切換摩擦**：開發者在 IDE 中須頻繁於原始碼、`plans/` 計畫文件與 `docs/` 文檔間來回切換，缺乏統一的記憶體內即時編譯視圖與語言伺服器（Language Server）為未來 GUI Kit 提供結構化狀態與關聯投射。
- **長期願景與目標定位**：
  - 將無傾向（Unopinionated）之 **無損區段語法樹（`LosslessCST`）與五相位可插拔編譯管線（`5-Phase Compile Pipeline`）直接整併入 `module:ast`**：未安裝任何規則貢獻模組時管線為零開銷空轉（No-op）；當外部模組透過 `contributes/ast.json` 注入規則時，即成為跨代碼與文檔之統一 AST/CST 編譯與靜態檢核中心；若環境同時具備 `server` 與 `file-space`，則自動湧現為常駐增量 **Language Server**。
  - 將 **`docs/` 文檔規範與知識庫治理全權回歸 `module:knowledge-db`**：由 `knowledge-db` 向 `ast` 貢獻文檔編譯與程式碼符號綁定規則（動態連結原始碼區段與 Docstring），並內建結構化術語字庫與 `yscb kdb means "<專有名詞>"` 精準語意解析指令。
  - 將 **`module:agents-workflow` 純化為乾淨的工作流骨幹框架與 CLI 工具**：移除內部私有編譯器，改為向 `ast` 貢獻工作流語意規則並調用 `ast` 物化 SDK；同時將領域專屬之 `plan` 軌道與技能資產改由外部 `contributes` 注入（如純軟工程下沉至 `agents-workflow-coding`，未來可平行擴充 `agents-workflow-unity`、`agents-workflow-pixel-art` 等領域包）。
- **範疇與邊界約束**：
  - 涵蓋 `module:ast` 之 `LosslessCST`、虛擬產物圖譜（`ArtifactGraph`）、五相位可插拔編譯管線與物化 SDK；`module:knowledge-db` 之 `docs/` 規範接管、原始碼 AST 符號動態關聯與 `kdb means` 術語字典；以及 `module:agents-workflow` 編譯能力委派與領域包解耦介面（領域軌道解耦細節與 `declarative_track_schema_and_domain_packs` 協同演進）。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **100% Python 標準庫與原位切片無損不變量（Bit-for-Bit Lossless Splicing）**：`module:ast` 之 Markdown CST 解析與拼接器嚴格維持零第三方 PyPI 依賴，每個節點記錄原始位元組/字元區間 `(raw_start, raw_end)` 與跨檔溯源座標 `SourceOrigin(provider_module, source_uri, source_line, source_col)`；未標記 `dirty` 之節點 100% 原位保留原始字元切片，徹底杜絕全樹重繪造成的清單重排、表格變形或語法破壞。
  - **無傾向微核心與零貢獻空轉不變量（Zero-Contribution No-Op）**：`module:ast` 編譯管線本體不硬編碼任何特定業務領域（如 IDE 發布目標、工作流階段或知識庫標記）之語意；所有標準文檔操作指令（如 `literal`、`ignore`、`if/elif/else`、`outline`、`toc`、`split`、`merge`）透過 `ast` 自我貢獻（Self-Contribution）注入，業務規則則由下游模組按需注入。無外部規則注入時，管線不產生任何額外副作用。
  - **單一純淨 SSOT 與「記憶體即時編譯 vs. 邊界受控物化」分離**：專案工作區永遠只維護單一純淨原始檔（Single Clean SSOT），嚴禁產生雙向同步之鏡像編輯樹。針對支援插件或自訂前端之消費者（如未來 GUI Kit、`knowledge-db` 檢索與 `server` 語言服務），直接調用 `ast.compile()` 於記憶體內取得展開後之 `ArtifactGraph`；僅針對無法改造讀取邏輯之封閉外部消費者（如各宿主 IDE 固定掃描之 `.agents/skills/`），方由 `agents-workflow` 調用 `ast.materialize()` 單向輸出至受保護之物化目錄（結合 `core.file_lock` 唯讀鎖防護）。
  - **職責正交歸位（Orthogonal Module Ownership）**：
    - `module:ast`：專責跨語言 AST 與 Markdown `LosslessCST` 解析、符號圖譜、五相位編譯管線、記憶體/磁碟物化 SDK 與 Language Server 增量診斷。
    - `module:knowledge-db`：專責 `docs/` 文檔規範（含 `documentation` 技能）、文檔與原始碼 AST 符號/Docstring 雙向連結校驗、知識檢索（`search`）與領域術語字典查詢（`means`）。
    - `module:agents-workflow`：專責 Agent 行為護欄與工作流生命周期骨幹 CLI，僅向 `ast` 貢獻編譯規則並開放 `plan` 領域擴充槽位（由 `agents-workflow-coding` 等外部包注入具體研發階段與模板）。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **`module:ast` 五相位可插拔管線與五大 `contributes` 擴充槽位**：
    1. **五大宣告式擴充槽位（`contributes/ast.json`）**：開放 `passes`（相位處理器）、`directives`（區塊與單行指令處理器）、`predicates`（條件表達式命名空間）、`inline_resolvers`（行內語意插槽解析器）與 `pipelines`（具名管線預設組合）。
    2. **五相位確定性調度（5-Phase Pipeline）**：依序執行 `Phase 100 (PREPROCESS：保護區遮罩與註解剝除)` $\to$ `Phase 200 (COMPOSE：條件剪枝、跨檔插槽展開、相對標題自動位移與表格合併)` $\to$ `Phase 300 (TRANSFORM：單檔拆多檔 emit_child、延遲大綱階層編號與目錄生成)` $\to$ `Phase 400 (RESOLVE：跨產物相對路徑、環境變數與原始碼 AST 符號/Docstring 鑲嵌解算)` $\to$ `Phase 500 (VALIDATE：結構契約守門與 SourceOrigin 精準單行診斷)`。
    3. **Language Server 自動湧現**：當環境安裝 `file-space` 與 `server` 時，`module:ast` 透過增量依賴帳本（Dependency Ledger）監聽檔案變更，對受影響之代碼與文檔 CST 執行毫秒級局部重編譯與跨檔死鏈/符號變更診斷，直接供 IDE 與 GUI Kit 消費。
  - **`module:knowledge-db` 文檔接管、動態代碼綁定與 `kdb means` 術語字典**：
    1. **原始碼區段與註解動態連結**：`knowledge-db` 向 `ast` 註冊行內解析器與檢核規則，使 `DESIGN_NOTES.md` 與 `docs/` 可直接透過語意錨點綁定目標 Python 模組之類別、函式簽名或指定 Docstring 區段；當底層原始碼行號變動或符號重構時，編譯管線可自動更新投射位置或於 `Phase 500` 精準報錯，徹底消滅過時行號與假文檔。
    2. **`yscb kdb means "<專有名詞>"` 秒級術語字典**：於 `docs/`、設計決策（`[DN-*]`）與模組契約中提取結構化術語定義、別名與上下游關聯符號並建立輕量索引，提供毫秒級概念釋義、定義座標與關聯設計筆記查詢，消除 Agent 在廣域檢索中途遭遇未知專有名詞時的二次廣搜開銷。
    3. **`documentation` 技能歸位**：將三層文檔架構規範與 `documentation` 技能自 `agents-workflow` 遷移至 `knowledge-db` 統一維護與貢獻。
  - **`module:agents-workflow` 骨幹純化與領域包注入**：
    1. **編譯邏輯下沉委派**：`agents-workflow` 將原本內建之工作流模板拼裝、錨點注入與目標環境剪枝改寫為 `contributes/ast.json` 規則，並透過 `ast` SDK 完成技能與規範物化。
    2. **領域工作流外掛化**：`agents-workflow` 本體僅保留無領域偏見之計畫生命周期框架與通用 CLI；純軟研發專屬之階段定義、模板與檢核器抽離聚合為 `agents-workflow-coding`，使骨幹得以無縫支撐非純軟領域擴充包。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 需先完成當前底層基礎問題（含代碼庫深層審計修繕、知識庫引擎與檢索底座優化、以及宣告式唯讀檔案鎖 `core.file_lock` 等前置基礎建設）後再行啟動。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`module:ast` `LosslessCST` 與五相位可插拔編譯管線基座）**：於 `ast` 實作 100% 標準庫之 `LosslessCST`、`ArtifactGraph`、五大 `contributes` 擴充槽位與自我注入之核心通用指令集，並提供記憶體編譯與磁碟物化 SDK。
  2. **Stage 2（`module:knowledge-db` 接管 `docs/` 規範、AST 符號動態連結與 `kdb means`）**：將 `documentation` 技能與文檔治理移交 `knowledge-db`，實作 `DESIGN_NOTES.md` 原始碼區段/Docstring 動態綁定校驗器與 `yscb kdb means "<專有名詞>"` 術語字典引擎。
  3. **Stage 3（`module:agents-workflow` 編譯委派與 `agents-workflow-coding` 領域解耦）**：將 `agents-workflow` 內部編譯器切換至 `ast` 編譯管線 SDK，並結合 `TrackSpec` 擴充機制將軟體工程專屬計畫資產下沉至 `agents-workflow-coding`，同時打通 `server` + `file-space` 常駐 Language Server 與 GUI Kit 雙向關聯閉環。

