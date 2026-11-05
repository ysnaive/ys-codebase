# 技術路線圖：`module:git-support` 獨立模組與 Git 操作解耦及變更守門架構 (Roadmap)

> 主題：`module:git-support` 獨立模組與 Git 操作解耦及變更守門架構 (`git_support_module_and_guardrails`)  
> 歸檔日期：2026-11-05  
> 狀態：Backlog  
> 目標範疇：`core`（CLI 派發否決權契約 `pre_cli_dispatch` Veto）、新模組 `module:git-support`（Git 操作封裝、受保護路徑指紋簽認守門）、`agents-workflow`、`dev`  
> 前置解鎖條件：[Tier 4 - 排序 #7 (Backlog)] 受保護檔案防誤改已由 #1 (core.file_lock) 物理覆蓋、Git 快照與溯源已由 #2b/#3 覆蓋；本項收斂為選配 CLI pre-flight Veto (與 [TODO-21] 協同) 及跨模組 Git 輔助擴充，待多團隊簽認需求出現時啟動  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **業務模組零星夾帶 Git 子程序呼叫**：部分模組（如工作流軌跡紀錄查詢異動檔案、開發發布流程執行本地提交與打標籤）內部直接呼叫 `git` 命令，若未來擴充更多版本控制協同功能，易在各模組散落重複之 Git 探測與降級樣板。
  - **核心架構檔案缺乏防無心改動之顯式確認護欄**：在長時程自主開發過程中，Agent 可能於修復次要問題時無意間順手修改高敏感度檔案（如宿主入口或核心規範），目前缺乏在 CLI 派發前與提交前針對「特定檔案內容雜湊」進行顯式簽認與留痕之輕量護欄。
- **長期願景與目標定位**：
  - 建立選配官方模組 `module:git-support`，以事件反轉（Event Inversion）解耦各業務模組對 Git 之直接操作，並提供零環境探針、綁定檔案內容雜湊（`(rel_path, content_sha256)`）之顯式授權護欄。
- **範疇與邊界約束**：
  - **`.gitignore` 規則管理已統一由 `core.gitignore` 內建負責**：`.gitignore` 生成與託管區塊軟合併屬零外部依賴之標準檔案衛生防呆，由 `core.gitignore` 原生透過 `contributes` / SDK / 事件統一收斂，不在 `git-support` 重複實作。
  - **誠實定位守門機制為「防疏漏護欄與審計留痕」而非「絕對安全沙盒」**：在 Agent 具備宿主完整終端權限之前提下，本地檔案與 Git Hook 皆可被繞過；故授權機制聚焦於 Level 1 顯式指紋簽認與 `audit.jsonl` 決策留痕，不宣稱不可繞過之密碼學隔離。
  - **嚴格區分「不受版控託管」與「搜尋/掃描排除」**：`.gitignore` 僅管理不納入版本控制之本機產物，與 `file-space` 掃描排除或搜尋忽略（`.ignore`）語意正交，絕不混用。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **零環境探針（Zero Environment Probes）**：僅依賴標準庫與基礎 `git` CLI，不讀取任何特定 IDE 之私有環境變數或對話紀錄檔。
  - **結構化否決契約（Structured Veto Contract）**：`core` 擴充 `pre_cli_dispatch` 事件時，派發上下文置於 `ExecutionContext.metadata`，且**僅在 Hook 顯式回傳結構化否決字典（`{"veto": True, "reason": ..., "exit_code": ...}`）時阻斷執行**，嚴禁將布林 `False` 視為否決（確保與既有回傳 `bool` 之 Hook 完全相容）。
  - **依指令權限分級攔截（Tier-Aware Guardrails）**：對 `[SAFE]` 唯讀診斷與檢索指令僅輸出提示而不阻斷，確保調查動線順暢；僅對 `[GATED]` / 寫入型指令與 `pre-commit` 執行剛性攔截。
  - **事件反轉與非 Git 環境無損降級**：其他模組不硬依賴 `git-support`；透過事件廣播委派版本控制操作，未安裝或非 Git 工作區時自動靜默降級。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **Git 子程序操作收斂**：將工作區異動查詢及發布提交標籤操作收斂至 `git-support`，由各模組透過事件提供資料。
  - **內容指紋綁定簽認（Content-Hash Authorization）**：針對 `protected_paths` 內與 `HEAD` 存在差異之檔案，比對當前內容 SHA-256 是否已登錄於授權表；檔案內容再次變動時雜湊自然失效，須重新簽認並記錄於受追蹤之審計日誌。
  - **非破壞性 `pre-commit` 串接**：尊重使用者既有 `core.hooksPath` 與既有 Hook 腳本，採附加呼叫而非覆蓋寫入，並支援 Git Worktree（`.git` 為檔案之拓撲）。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 待跨模組 Git 協同需求增加或需啟用受保護路徑變更護欄時按階段推進。
- **階段演進構想 (High-Level Stages)**：
  1. **Phase A（`core` 結構化 Veto 契約與 Git 子程序操作抽離）**：於 `core` 實作向後相容之 `pre_cli_dispatch` 結構化否決契約與 `ExecutionContext.metadata` 傳遞；建立 `module:git-support` 收斂 Git 輔助操作。
  2. **Phase B（依權限分級之內容指紋變更護欄）**：實作 `protected_paths` 內容 SHA-256 指紋核對、`authorize` 審計留痕與非破壞性 `pre-commit` 串接。

