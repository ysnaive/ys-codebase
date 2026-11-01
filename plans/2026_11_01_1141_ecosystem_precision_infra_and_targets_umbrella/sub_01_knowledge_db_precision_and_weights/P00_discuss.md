# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 檢索精準度、拓撲消歧、Watcher 時序、空間權重與 C#/C++ 解析強化  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `knowledge-db` 相關之待辦事項（`TODO-04`, `TODO-08`, `TODO-09`, `TODO-14`, `TODO-15`）打包作為 Umbrella 子計畫 `sub_01` 優先推進。
- **核心目標**：
  1. **`TopologyLinker` 三處靜態消歧邏輯漏洞修復 (`TODO-08`)**：
     - 移除 `if prefix` 分支內對 `caller_class` 的錯誤回退（防止 `this._helper.Save()` 因 `_helper` 型別未知而誤綁回 `caller_class.Save()` 自綁定）。
     - 加固 `len(candidates) == 1` 的連線門檻（無明確型別或匯入支撐時，僅在通過 `_score_candidates` 正向加分或位於同檔案定義時才建立呼叫邊，根除跨模組同名幽靈邊）。
     - 收緊 `_score_candidates` 短變數子字串匹配，要求 `len(prefix_tail) >= 3`（防止單字母變數 `e`、`s`、`i` 誤配所有含該字母的類別）。
  2. **`.watcher_active` 寫入時序與異常清理及 `.watcher_dirty` 前台檢核對齊 (`TODO-09`)**：
     - 於 `service.py` 將寫入 `.watcher_active` 移至 `observer.start()` 成功之後，並於被動模式 `except Exception:` 分支清理殘留之 `.watcher_active`。
     - 於 `pipeline.py` `_is_watcher_active` 補齊對 `.watcher_dirty` 的讀取檢核（若存在 `.watcher_dirty` 則返回 `False` 觸發前台增量同步，對齊 `[DN-04]` 文檔契約）。
  3. **`SpaceDef` 宣告式檢索權重 (`weight`) 支援 (`TODO-14`)**：
     - 於 `knowledge-db/contributes/_format.json` 的 `spaces` Schema 新增選填 `"weight": "float?"`（預設 `1.0`），於 `space.py` `SpaceDef` 解析保存 `weight`，並於 `hybrid.py` 檢索算分時乘上所屬 Space 之 `weight`。
     - 於 `agents-workflow/contributes/knowledge-db.json` 為 `docs` 設定預設較高權重（如 `1.2`）或調降 `plans`（如 `0.85`），使 `docs/` 系統事實預設優先於 `plans/` 歷史過程，且天然支援下游專案於 `config/knowledge-db/contribute.json` 覆寫。
  4. **C#/C++ AST 成員修飾詞 `visibility` 解析與 C# 跨檔案 `partial class` 符號聚合 (`TODO-15`)**：
     - 修正 `parsers/treesitter.py`：針對 C#、C++、Java、TypeScript 等語言，從 AST 節點（或其 `modifier` / `access_specifier` 子節點）提取 `public` / `private` / `protected` / `internal` 修飾詞決定 `visibility`（僅對 Python 等無顯式修飾詞語言回退底線命名慣例 `_name`）。
     - 支援同 Space、同 Namespace 下之 C# `partial class` 跨檔案符號與成員聚合，使 `callers` / `callees` / `search` 能跨越 `partial class` 拆分檔完整解析成員歸屬。
  5. **未安裝 `agents-workflow` 時隱藏 Agent 專屬提示 (`TODO-04`)**：
     - 於 `knowledge-db` CLI 輸出截斷提示或尾端導引時，檢查 `module://agents-workflow` 是否已安裝；若未安裝則不輸出專供 AI Agent 閱讀之工作流提示文字。
- **邊界排除 (Explicitly Excluded)**：
  - 執行期反射、DI 容器或 C# Source Generator 之宣告式/動態呼叫圖連結（歸屬遠期路線圖 `declarative_and_dynamic_call_graph_linking.md`）。
- **架構影響範圍**：
  - `ys_codebase/source/knowledge-db/`（`contributes/_format.json`、`knowledge_db/{space.py,hybrid.py,linker.py,service.py,pipeline.py,parsers/treesitter.py,queries/c_sharp.scm}`、`scripts/cli.py`、`tests/`）與 `ys_codebase/source/agents-workflow/contributes/knowledge-db.json`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **宣告式 `SpaceDef.weight` 乘算與預設權重配置**：於 `knowledge-db/contributes/_format.json` 的 `spaces` 定義新增 `"weight": "float?"`（預設 `1.0`，必須 $> 0$）；`HybridSearchEngine` 在彙整各 Space 檢索候選分數時乘以 `space_def.weight`。`agents-workflow/contributes/knowledge-db.json` 預設設定 `docs` `weight: 1.2`、`plans` `weight: 0.85`，下游專案可透過專案級 `contribute.json` 自由覆寫。
- **[P00:DR-02]** **`TopologyLinker` 消歧防偽邊三原則**：(1) 有明確呼叫接收者前綴 (`prefix`) 但無法解析其型別時，絕不回退綁定至 `caller_class`；(2) 全域唯一同名候選 (`len(candidates) == 1`) 若帶未知 `prefix`，必須通過 `_score_candidates > 0` 或同檔案定義方連線；(3) `_score_candidates` 名稱子字串啟發式加分強制要求 `len(prefix_tail) >= 3`。
- **[P00:DR-03]** **多語言 AST `visibility` 與 C# `partial class` 跨檔聚合**：`TreeSitterParser` 針對具顯式存取修飾詞之語言（C#、C++、Java、TS）直接解析 AST 修飾詞（C# 類別成員未標註時預設 `private`、頂層型別預設 `internal`），僅 Python/JS 回退底線規則；並於索引/連結階段將同 Space 且同 Namespace (或同頂層限定名) 之 `partial class` 成員統一匯聚至主類別節點或共享成員表。

---

## 3. 開放議題與確認紀錄

- 需求與解法邊界均已由兩份深度審閱報告及開發者拍板確認，無待決開放議題。

