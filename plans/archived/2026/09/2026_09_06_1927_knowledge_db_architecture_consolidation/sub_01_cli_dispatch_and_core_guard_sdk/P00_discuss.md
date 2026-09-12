# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：第一步改為 cli 串接系統改造，cli 檔名不變，規範改為必須宣告函式 process(args)，dev create module 骨架功能時便預先創立好，並在 module 檢查管道上添加檢測，cli 中必須有 process 且不可有 main，另外，於 Core 添加通用守門 SDK，各模組入口 (process) 調用，骨架建立時就會預先填入。
- **核心目標**：
  1. **CLI 入口函式標準化**：全生態系模組入口檔案維持 `scripts/cli.py`，但進入點規範統一宣告為 `def process(args: List[str]) -> int`。
  2. **禁絕 `main` 與腳本誘因**：徹底禁止 `def main(...)` 函式與 `if __name__ == '__main__':` 執行區塊，從代碼結構上消除 AI Agent 直接運行腳本之誘因。
  3. **Core 通用守門 SDK**：於 `core` 模組實作通用防偽守門 SDK，於各模組 `process(args)` 頂部調用，未經宿主分派直接調用時於 1 毫秒內剛性熔斷並輸出修正引導。
  4. **骨架生成功能適配 (`dev create`)**：於 `dev.scaffold` 預裝符合新規範之 `scripts/cli.py`，預先內建 `process(args)` 與 Core 守門 SDK 調用。
  5. **靜態合規檢測管線 (`dev check`)**：於 `dev.checker` 增設 AST 剛性檢測，針對 `scripts/cli.py` 強制驗證「必須包含 process 函式、絕對不可有 main」，違規直接判定 `FAIL` 阻擋發布。
  6. **宿主分派層適配 (`yscb.py`)**：改造 `yscb.py` 派發邏輯，改為調用模組之 `process(args)` 並注入防偽驗證 Token。
  7. **禁絕頂層執行陳述式 (Zero Top-Level Executable Code)**：於 `dev.checker` 增設 AST 嚴格掃描，`scripts/cli.py` 頂層除 Docstring 與 import 語句外，嚴禁任何未包覆在 `func` / `class` 內之裸執行語句（如裸函式呼叫、運算或流程控制），杜絕匯入時意外執行。
- **邊界排除 (Explicitly Excluded)**：
  - 暫不啟動全域 Server 常駐守護中樞（列入後續子計畫）。
  - 暫不實作各領域模組內部業務邏輯重構，專注於 CLI 進入點協議與守門架構落地。
  - 嚴格遵守全域重構期管制紀律：**嚴禁執行本地 `@build` 自部署**。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 入口檔案與函式簽名標準化**：模組進入點檔案路徑維持 `scripts/cli.py` 不變；導出函式統一規範為 `def process(args: List[str]) -> int`。
- **[P00:DR-02] 禁絕 `main` 標識與腳本執行區塊**：嚴禁於 `scripts/cli.py` 宣告 `main` 函式或 `if __name__ == '__main__':`，代碼僅作為純可匯入庫由宿主調用。
- **[P00:DR-03] Core 守門 SDK 設計與剛性熔斷**：於 `core` 建立守門機制，核驗 `YSCB_HOST_DIR` 與 `YSCB_HOST_DISPATCH_TOKEN`，驗證失敗直接拋出退出碼 126 並輸出引導指令。
- **[P00:DR-04] Dev 工具鏈雙向守門**：
  - `dev.scaffold`：生成新模組骨架時預置標準 `process(args)` 與守門調用。
  - `dev.checker`：以 AST 語法樹靜態掃描 `scripts/cli.py`，未含 `process` 或殘留 `main` 立即裁定 `FAIL`。
- **[P00:DR-05] 頂層裸執行陳述式剛性阻擋**：因 Python 模組載入時頂層陳述式必然執行，`dev.checker` 增設剛性 AST 檢驗：`scripts/cli.py` 頂層節點僅允許 Docstring、`Import`、`ImportFrom`、`FunctionDef` 與 `ClassDef`。任何未包覆於函式或類別之執行陳述式（如頂層呼叫、邏輯分支等）一律判定 `FAIL`。

---

## 3. 開放議題與確認紀錄

- [x] CLI 進入點路徑是否變動？（確認：維持 `scripts/cli.py`）
- [x] 進入點函式命名？（確認：命名為 `process(args)`）
- [x] 是否徹底排除 `main`？（確認：不可有 `main` 函式，不可有 `__main__` 執行區塊）
- [x] 守門 SDK 職責歸屬？（確認：收斂至 `core` 模組）
- [x] 頂層裸執行陳述式？（確認：嚴禁任何未包覆在 func/class 之執行內容）
- [ ] 守門 SDK 具體模組路徑定調（預計於 P02/P03 確定為 `core.guard` 或 `core.platform.guard`）
