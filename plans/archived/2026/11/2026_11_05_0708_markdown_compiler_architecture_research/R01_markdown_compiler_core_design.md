# 專題調研與分析報告：`module:ast` 統一無損 CST 編譯管線、`knowledge-db` 文檔治理與 `agents-workflow` 骨幹解耦架構調研 (R01_markdown_compiler_core_design.md)

> 調研主題：`module:ast` 統一無損 CST 編譯管線、`knowledge-db` 文檔治理與 `agents-workflow` 骨幹解耦架構調研  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 現有工作流資產編譯器內嵌於 `agents-workflow/compiler.py`，為基於正則與行掃描之特化管線，無法為其他模組提供帶來源座標溯源（`SourceOrigin`）之語法樹轉換或靜態校驗。
  - 專案中之 `docs/` 系統文檔規範（如 `DESIGN_NOTES.md`、`ARCHITECTURE.md` 與 `documentation` 技能）目前寄居於 `agents-workflow`，且文檔中對原始碼行號、函式簽名與 Docstring 的引用缺乏 AST 級動態連結與校驗，極易隨代碼修改而腐敗。
  - Agent 與開發者於 `knowledge-db search` 廣度檢索中途遭遇專案專有名詞時，缺乏如 `kdb means "<專有名詞>"` 之精準字典查詢，且開發者在 IDE 中須頻繁於原始碼、`plans/` 與 `docs/` 間切換。
  - 若為了解決上述問題而在工作區物化大量編譯後鏡像檔案，將導致「SSOT 原始檔 + 物化鏡像檔」雙軌氾濫與同步災難；若將所有變體塞入單一原始檔，又會導致單檔充斥條件分支而混亂不可控。
- **調研目標與範疇**：
  1. 評估通用 Markdown 無損語法樹（`LosslessCST`）與五相位可插拔編譯管線（`5-Phase Compile Pipeline`）之技術選型與模組歸屬（獨立模組 vs. 直接整併入 `module:ast`）。
  2. 制定「單一純淨 SSOT」下之「記憶體即時編譯（In-Memory Compilation）」與「邊界受控物化（Out-of-Tree Materialization）」分流法則。
  3. 釐清 `module:ast`、`module:knowledge-db` 與 `module:agents-workflow`（含外部領域包 `agents-workflow-coding` 等）之正交職責邊界。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- **核心分析與實證內容**：

### 2.1 語法樹底座選型：100% 標準庫之「無損區段語法樹（Lossless Block-CST）」

| 候選底座 | 核心機制 | 致命限制與取捨分析 | 選型裁決 |
| :--- | :--- | :--- | :---: |
| **`markdown-it-py` + `mdformat` / `mistune` / `mistletoe`** | Token 流轉 AST + 全樹重繪渲染器（Full-Tree Re-rendering） | 轉回 Markdown 時會強制重排清單序號、改動表格欄寬、對底線加轉義並破壞 GitHub Alerts 或四反引號代碼圍欄；且具第三方套件依賴。 | ❌ 淘汰 |
| **外部知識管理軟體（如 Obsidian）** | 雙向連結 GUI 筆記本 + 社群插件 | 強綁定桌面編輯器 runtime，Headless CLI 與 Agent 無法直接調用其插件渲染管線，且無法理解 `project://` / `code.symbol://` 等跨模組語意。 | ❌ 淘汰 |
| **自建 `Lossless Block-CST` 微核心（整併入 `module:ast`）** | 100% Python 標準庫，解析帶精確起訖偏移量 `(raw_start, raw_end)` 之 CST，僅對標記 `dirty` 之變動節點執行原位切片替換（Span Splicing） | 未變動之原始文本維持 **Bit-for-Bit 100% 無損**；零外部依賴；直接與 `module:ast` 既有之 Python/JS/TS/JSON AST 引擎共享符號圖譜與座標體系。 | ✅ **採納** |

### 2.2 防範鏡像氾濫與單檔混亂：「記憶體即時編譯 vs. 邊界受控物化」與「骨骼—肌肉分離」

1. **為何不能對 `docs/` 與 `plans/` 搞磁碟物化鏡像？**
   - 只有當「下游消費者是無法修改讀取邏輯的封閉外部程式（如宿主 IDE 固定掃描 `.agents/skills/`）」時，才需要單向磁碟物化（`ast.materialize()`，並結合 `core.file_lock` `0o444` 唯讀鎖防護）。
   - 對於受控於本生態系之消費者（如未來 GUI Kit、`knowledge-db` 檢索與 `server` Language Server），一律維持 **單一純淨 SSOT 原始檔**，直接於記憶體內調用 `ast.compile()` 獲取展開後之 `ArtifactGraph` 視圖，工作區零鏡像污染。
2. **為何單一原始檔不會因多領域擴充而混亂？**
   - 採用「骨骼（統一流程模板）與肌肉（外部模組透過 `contributes` 注入之領域片段）物理分離」：主檔案僅保留乾淨的結構錨點插槽，各領域規則存放在各自模組目錄中，徹底消滅單檔龐大 `if/elif/else` 條件分支。

### 2.3 三大核心模組正交職責重構（`ast` × `knowledge-db` × `agents-workflow`）

| 模組 | 重構後之核心定位 | 對外提供 / 貢獻之核心能力 |
| :--- | :--- | :--- |
| **`module:ast`** | **跨語言 AST + Markdown `LosslessCST` + 五相位可插拔編譯管線與 Language Server 基座** | 1. 內建 `LosslessCST`、`SourceOrigin` 跨檔溯源、`ArtifactGraph` 與 `Phases 100~500` 管線調度器（無外部規則貢獻時為零開銷 No-op）。<br/>2. 開放 `contributes/ast.json` 五大槽位（`passes`, `directives`, `predicates`, `inline_resolvers`, `pipelines`）並自我注入基礎指令（`literal`, `ignore`, `if`, `outline`, `toc`, `split`, `merge`）。<br/>3. 提供 `compile()`（記憶體視圖）與 `materialize()`（磁碟物化 SDK）；當安裝 `server` + `file-space` 時自動擴充為常駐 **Language Server**。 |
| **`module:knowledge-db`** | **知識庫檢索、`docs/` 文檔規範總管、動態代碼連結與 `kdb means` 術語字典中心** | 1. 自 `agents-workflow` 接管 `docs/` 三層文檔規範與 `documentation` 技能。<br/>2. 向 `ast` 貢獻文檔編譯與驗證規則：支援 `DESIGN_NOTES.md` 等文檔直接動態綁定原始碼區段、AST 符號簽名或引用原始碼註解/Docstring，由編譯管線自動校驗與投射，杜絕死鏈與過時行號。<br/>3. 實作 `yscb kdb means "<專有名詞>"` 術語字庫查詢，供 Agent 與 GUI Kit 秒級獲取專有名詞定義與關聯決策。 |
| **`module:agents-workflow`** | **純淨無領域偏見之工作流骨幹框架與通用 CLI 工具** | 1. 移除內部私有 `compiler.py`，改為向 `ast` 貢獻工作流語意規則並調用 `ast.materialize()` 物化 `.agents/`。<br/>2. 將 `plan` 軌道機制改為 `contributes` 外部注入：現有純軟工程計畫下沉至 `agents-workflow-coding`，未來可平行擴充 `agents-workflow-unity`、`agents-workflow-pixel-art` 等領域包。 |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  - 不另立獨立 `markdown-compiler` 模組，直接將無傾向 `LosslessCST` 與五相位可插拔編譯管線整併入 `module:ast`（結合 `server` + `file-space` 自動成為 Language Server），將 `docs/` 規範、原始碼 AST 區段/註解動態連結與 `kdb means` 術語字典歸位至 `module:knowledge-db`，並將 `module:agents-workflow` 純化為骨幹框架（領域計畫外掛化為 `agents-workflow-coding` 等）。
- **後續建議（選填）**：
  - 依開發者裁決採 **出口 ②（路線圖儲備）**，已將完整架構藍圖寫入 [`plans/roadmap/ast_compile_pipeline_and_kdb_doc_governance.md`](../roadmap/ast_compile_pipeline_and_kdb_doc_governance.md) 並同步更新 [`plans/roadmap/declarative_track_schema_and_domain_packs.md`](../roadmap/declarative_track_schema_and_domain_packs.md)，待相關底層基礎問題處理完畢後再行啟動。
