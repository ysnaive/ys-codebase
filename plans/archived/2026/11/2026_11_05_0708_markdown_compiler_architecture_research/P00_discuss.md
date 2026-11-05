# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_05_0708_markdown_compiler_architecture_research  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 計畫類型：Research  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 由《`module:markdown-compiler` 無傾向通用型 CST 微核心與可插拔編譯管線架構設計書》初稿出發，探討：
    1. 無損區段語法樹（`LosslessCST`）、多產物虛擬圖譜（`ArtifactGraph`）與五相位可插拔管線（`5-Phase Pass Pipeline`）之微核心設計。
    2. 單一純淨 SSOT 與避免工作區鏡像氾濫（Mirror Proliferation）之邊界：記憶體即時編譯（In-Memory Compilation，供未來 GUI Kit、`knowledge-db` 與 `server` 消費）vs. 邊界受控物化（Out-of-Tree Materialization，僅供封閉外部宿主如 `.agents/skills/` 消費）。
    3. 跨模組職責正交歸位：將通用編譯管線直接整併入 `module:ast`、將 `docs/` 規範與動態原始碼錨點及 `kdb means "<專有名詞>"` 術語字典歸位至 `module:knowledge-db`、並將 `module:agents-workflow` 純化為骨幹框架與領域包擴充架構（`agents-workflow-coding`、`-unity`、`-pixel-art`）。
    4. 將收斂之完整架構藍圖記入長期路線圖（`plans/roadmap/`），優先處理與其相關之底層問題。
- **核心目標**：
  - 完成跨代碼與文檔之統一 CST/AST 編譯管線、知識庫文檔治理與工作流領域解耦之架構論證，並轉入 `plans/roadmap/ast_compile_pipeline_and_kdb_doc_governance.md` 儲備。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 100% 依賴 Python 標準庫與 `core` 微內核契約（`uri`、`vfs`、`contributes`）；直接擴充既有 `module:ast`、`module:knowledge-db`、`module:agents-workflow`、`module:server` 與 `module:file-space`，不額外切分獨立 `markdown-compiler` 模組。
- **邊界排除 (Explicitly Excluded)**：
  - 本調研不直接執行業務代碼修改；收斂結論透過出口 ② 納入 `plans/roadmap/`，待前置底層問題處理完畢後再透過 `roadmap promote` 啟動實作。
- **架構影響範圍**：
  - 長期演進涉及 `ys_codebase/source/{ast,knowledge-db,agents-workflow,server,file-space}/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 底座選型：100% Python 標準庫之「無損區段語法樹（Lossless Block-CST）」**：
  - 放棄 `mdformat` / `mistune` / `mistletoe` 等全樹重繪渲染器，採用自建 0 外部依賴之 `LosslessCST`：每個節點保存精確起訖偏移量 `(raw_start, raw_end)` 與 `SourceOrigin`，未變動節點 100% 原位保留原始字元切片（Bit-for-Bit Lossless），僅對標記為 `dirty` 之變動節點執行局部重繪與切片拼接。
- **[P00:DR-02] 拒絕鏡像環境氾濫：單一純淨 SSOT +「記憶體即時編譯 vs. 邊界受控物化」雙模輸出**：
  - 嚴禁在專案內建立與原始碼平行的雙向物化鏡像樹。對內（GUI Kit、`knowledge-db`、`server`）一律調用 `compile()` 於記憶體內消費 `ArtifactGraph`；對外（僅限無法改造讀取邏輯之封閉宿主如 `.agents/skills/`）方調用 `materialize()` 單向輸出至隱藏物化區並搭配 `core.file_lock` 唯讀鎖防護。
- **[P00:DR-03] 取消獨立 `markdown-compiler` 模組，直接整併入 `module:ast`**：
  - `module:ast` 原本即具備多語言 AST 解析與符號圖譜能力（且已內建 `markdown` 基礎支援）。將 `LosslessCST`、`ArtifactGraph` 與 `5-Phase Compile Pipeline` 直接整併入 `module:ast`：無外部模組透過 `contributes/ast.json` 注入規則時為零開銷 No-op；有規則注入時即成為統一編譯管線；若同時安裝 `server` + `file-space`，則自動湧現為跨程式碼與文檔之常駐 **Language Server**。
- **[P00:DR-04] `docs/` 文檔規範與術語字典全權歸位 `module:knowledge-db`**：
  - 將 `docs/` 規範與 `documentation` 技能自 `agents-workflow` 移交 `knowledge-db`；由 `knowledge-db` 向 `ast` 貢獻文檔編譯與驗證規則（支援 `DESIGN_NOTES.md` 動態連結原始碼 AST 區段、符號簽名與 Docstring，消除死鏈與行號漂移），並新增 `yscb kdb means "<專有名詞>"` 術語字庫精準查詢能力。
- **[P00:DR-05] `module:agents-workflow` 純化為骨幹框架，領域能力外掛化（`-coding` / `-unity` / `-pixel-art`）**：
  - `agents-workflow` 移除內部私有 `compiler.py`，改為向 `ast` 貢獻編譯規則並調用 `ast` 物化 SDK；同時將 `plan` 軌道能力改為 `contributes` 注入，現有純軟工程計畫聚合下沉至 `agents-workflow-coding`，使 `agents-workflow` 本體成為乾淨的跨領域骨幹框架與 CLI 工具。

---

## 3. 開放議題與確認紀錄

- [x] **議題 1（通用編譯管線之模組歸屬）**：確認取消獨立 `markdown-compiler` 模組，直接整併入 `module:ast`。
- [x] **議題 2（工作區鏡像氾濫防範與輸出模式）**：確認維持單一純淨 SSOT，區分記憶體內即時編譯（供 GUI Kit / KDB / Language Server）與邊界單向物化（供封閉宿主 `.agents/`）。
- [x] **議題 3（`docs/` 文檔規範與術語查詢歸屬）**：確認回歸 `module:knowledge-db`，由其向 `ast` 貢獻動態原始碼區段/Docstring 連結規則並提供 `kdb means "<專有名詞>"`。
- [x] **議題 4（`agents-workflow` 骨幹純化與領域包拆分）**：確認 `agents-workflow` 僅保留骨幹框架與規則貢獻，領域計畫下沉至 `agents-workflow-coding` 等外部擴充包。
- [x] **議題 5（調研出口裁決）**：確認選擇 **出口 ②（路線圖儲備）**，寫入 `plans/roadmap/ast_compile_pipeline_and_kdb_doc_governance.md` 並更新 `declarative_track_schema_and_domain_packs.md`，優先處理底層基礎問題。
