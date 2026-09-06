# 需求規格說明書 (Requirements Specification)

> 功能名稱：cli_dispatch_and_core_guard_sdk  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | CLI 入口簽名標準化 | 模組進入點檔案維持 `scripts/cli.py`，但統一宣告標準進入點函式 `def process(args: List[str]) -> int:`，接收字串參數列表並回傳整數退出碼。 | P0 | [P00:DR-01] |
| **FR-02** | 禁絕 `main` 與執行區塊 | `scripts/cli.py` 嚴禁宣告 `def main(...)` 函式，且嚴禁包含 `if __name__ == '__main__':` 執行區塊，徹底消除獨立腳本誘因。 | P0 | [P00:DR-02] |
| **FR-03** | Core 通用守門 SDK | 於 `core` 模組提供輕量守門 SDK（`core.guard.guard_dispatch`），核驗 `YSCB_HOST_DIR` 與 `YSCB_HOST_DISPATCH_TOKEN`。未經授權直接調用時於 1ms 內攔截輸出引導指令並以 Exit Code 126 退出。 | P0 | [P00:DR-03] |
| **FR-04** | 骨架生成範本升級 | 升級 `dev.scaffold.Scaffolder.create_module`，建立新模組時預置符合新規範之 `scripts/cli.py`（內建 `process(args)`、頂部調用 Core 守門 SDK、零 `main` 殘留）。 | P0 | [P00:DR-04] |
| **FR-05** | 靜態 AST 進入點合規檢核 | 升級 `dev.checker.Checker`，於合規檢驗管線以 AST 掃描 `scripts/cli.py`：必須含有 `process` 函式；嚴禁含有 `main` 函式；嚴禁含有 `if __name__ == '__main__':`，違規者判定 `FAIL`。 | P0 | [P00:DR-04] |
| **FR-06** | 頂層裸執行語句禁絕檢核 | 升級 `dev.checker.Checker`，`scripts/cli.py` 模組頂層節點僅允許 Docstring、`Import`、`ImportFrom`、`FunctionDef` 與 `ClassDef`。任何未包覆於函式或類別中之執行陳述式（如頂層呼叫、邏輯分支等）一律判定 `FAIL`。 | P0 | [P00:DR-05] |
| **FR-07** | 宿主入口派發層適配 | 改造 `yscb.py` 之 `dispatch_module`，動態載入模組 `scripts/cli.py` 並調用其 `process(args)` 函式；派發前注入 `YSCB_HOST_DISPATCH_TOKEN`。 | P0 | [P00:DR-01] |
| **FR-08** | 生態系現有模組升級遷移 | 全面改寫 `core`、`dev`、`agents-workflow`、`knowledge-db` 之 `scripts/cli.py`，改為導出 `process(args)`、移除 `main` 殘留與頂層裸代碼，並掛載 Core 守門 SDK。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 模組缺少 `process` 函式 | `dev check` 靜態掃描直接判定 `FAIL`；`yscb.py` 動態分派時捕獲 `AttributeError`，提示清晰錯誤並返回退出碼 1。 |
| **EC-02** | 模組殘留 `main` 函式或 `if __name__ == '__main__':` | `dev check` 靜態 AST 掃描立即定位節點行號，報告 `STRUCTURE` 類別 `FAIL` 錯誤並中斷發布。 |
| **EC-03** | `scripts/cli.py` 包含頂層裸執行陳述式（如頂層函式呼叫） | `dev check` AST 掃描檢測到非宣告型頂層節點，立即報告 `ANTIPATTERN` 類別 `FAIL`，並精準指出違規陳述式與行號。 |
| **EC-04** | 未經授權直接執行模組腳本 (`python .../cli.py`) | Core 守門 SDK 於 `process` 執行前探測到缺乏有效 Token，印出標準 `[YSCB Security Guard]` 警示與正確命令，以 126 退出。 |
| **EC-05** | 單元測試與自動化套件直接測試 `process(args)` | 當環境變數包含 `YSCB_TESTING=1` 時，Core 守門 SDK 豁免阻斷，確保 pytest 與 unittest 100% 正常運行。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 啟動延遲 | Core 守門 SDK 僅進行記憶體環境變數檢查，驗證耗時 $\le 0.1\text{ms}$，無磁碟 IO 開銷。 |
| **NFR-02** | 依賴約束 | Core 守門 SDK、`dev` 靜態 AST 檢驗管線與 `yscb.py` 派發層 100% 使用 Python 標準庫 (`sys`, `os`, `ast`, `importlib`)，零第三方依賴。 |
| **NFR-03** | 檢測吞吐量 | `dev check` 針對 `scripts/cli.py` 之 AST 剖析與語義樹檢核耗時 $\le 10\text{ms}$，不影響日常跑測體驗。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 模組頂層 `if hasattr(sys.stdout, "reconfigure"): ...` 等 Windows 編碼保護陳述式亦屬於頂層執行代碼，應統一收斂包覆進 `process(args)` 函式內部第一階段，確保頂層除 import 外無任何可執行語句。
- **`[!CAUTION]`** 於全生態系整體架構重構模式下，**絕對禁止**執行 `python yscb.py install <module>@build`，所有修改僅在 `source/` 內推進並透過沙盒測試驗證。
