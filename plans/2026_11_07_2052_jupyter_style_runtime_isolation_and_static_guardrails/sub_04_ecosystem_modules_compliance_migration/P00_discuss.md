# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_ecosystem_modules_compliance_migration  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：完成 `sub_03` 結案與 commit 後，推進 Umbrella 主計畫第四個子計畫 `sub_04_ecosystem_modules_compliance_migration`。
- **核心目標**：
  - 將上層 7 大業務模組（`dev`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support`）之非測試生產 `.py` 程式碼全面遷移對齊至 `core.log`、`core.context` (`RuntimeContext` / `get_virtual_cwd` / `get_env`)、`core.loader` 與 13 項 AST 靜態守門規範（A1~F13）：
    1. **(A1) 輸出與日誌統一遷移 (`core.log`)**：將 7 大模組中殘留之原生 `print()`、`sys.stdout.write`、`sys.stderr.write` 與 `logging.*` 全面遷移至 `core.log`（`log`、`log_stream`、`log_info`、`log_warn`、`log_error`、`log_debug` 與 `log_file` / `log_file_jsonl`），確保前景輸出 100% 維持既有格式契約、背景輸出自動走 `LogExecutionScope` 隔離。
    2. **(A2 / B4 / B5 / F13) 互動輸入、工作目錄、環境變數與子進程超時收斂**：
       - 消除裸 `input()` / `sys.stdin` 讀取（`agents-workflow` 之互動確認改走受控介面或參數化）；
       - 將 `os.chdir()`、`os.getcwd()`、`Path.cwd()` 遷移至 `core.context.get_virtual_cwd()`（與顯式路徑參數）；
       - 消除生產代碼執行期對 `os.environ` 的原地寫入/突變（改透過 `bind_runtime_context(env=...)` 或子進程 `env=` 參數傳遞）；
       - 為 `dev/tester.py` 等缺少 `timeout=` 之 `subprocess.run` 補齊明確超時防禦。
    3. **(C8 / C9 / D10) 頂層可變狀態清零、資料結構凍結與動態載入收斂**：
       - 將 7 大模組頂層可變容器字面量（`list`/`dict`/`set`）轉為 `tuple` / `frozenset` / `types.MappingProxyType`（保留 `__all__`），並將模組級執行期可變快取（如 `knowledge-db` 之 `_GLOBAL_ENGINE_INSTANCE` / `_GLOBAL_INDEX_CACHE` / `_ACTIVE_WORKER`、`file-space` 之 `_SUBSCRIBERS`、`ast` 之單例快取等）收斂至 `RuntimeContext` 或受管容器，達成 0 `global` 關鍵字與 0 頂層可變快取；
       - 將各模組之 `@dataclass` 補齊 `frozen=True`（或於需內部狀態變更時改為標準類別 / `object.__setattr__` 契約），並移除類別頂層可變預設屬性；
       - 將 `dev` 與 `ast` 中直接操作 `sys.modules` / `spec_from_file_location` 之動態載入收斂至 `core.loader.load_module_from_path`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接復用 `sub_01` ~ `sub_03` 已落地之 `core.log`（`log`, `log_stream`, `log_info`, `log_warn`, `log_error`, `log_debug`, `log_file`, `log_file_jsonl`）、`core.context`（`RuntimeContext`, `get_runtime_context`, `bind_runtime_context`, `get_virtual_cwd`, `get_env`）與 `core.loader`（`load_module_from_path`）。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改各模組之 `tests/` 測試案例斷言邏輯（除非白箱測試直接讀寫已遷移至 `RuntimeContext` 之私有屬性，此時透過 PEP 562 模組 `__getattr__` 或相容代理維持向後相容）。
  - `module:ast` 僅執行機械式合規遷移（A1~F13 語法與狀態收斂），不變更其語法樹解析與方言演算法架構。
  - `dev/checker.py` 13 項 AST 靜態守門規則本身之強制啟用屬於下一個子計畫 `sub_05_dev_closed_loop_ast_static_guardrails`。
- **架構影響範圍**：
  - `ys_codebase/source/{dev,file-space,ast,knowledge-db,agents-workflow,vscode-support,gdrive-support}/`（及 `core/context.py` 擴充對應領域快取槽位）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 7 大業務模組生產輸出與 CLI 格式 100% 無損遷移 (`A1` & `A2`)**：
  - 所有 CLI 與業務模組中之 `print(...)` 遷移至 `core.log.log(...)`（包含 `stream="stderr"` 映射 `file=sys.stderr` 與 `flush=True`），`sys.stdout.write` / `sys.stderr.write` 遷移至 `core.log.log_stream(...)`，`logging.getLogger(...)` 呼叫遷移至 `log_debug` / `log_info` / `log_warn` / `log_error`；`gdrive_support/coordinator.py` 之 `_append_log` 委派至 `core.log.log_file`。
- **[P00:DR-02] 頂層可變狀態收斂與 PEP 562 白箱相容代理 (`C8` & `C9`)**：
  - 針對測試中有直接存取或重設的模組頂層狀態（如 `knowledge_db.engine._GLOBAL_ENGINE_INSTANCE`、`knowledge_db.pipeline._GLOBAL_INDEX_CACHE`、`knowledge_db.service._ACTIVE_WORKER` 等），統一將實體狀態存入 `core.context.get_runtime_context().module_states`（或專屬欄位），並於原模組提供無 `global` 關鍵字之存取函式與 PEP 562 `__getattr__` 相容讀取，確保零頂層可變變數且既有白箱測試 100% 無縫通過。
- **[P00:DR-03] `@dataclass(frozen=True)` 與初始化後欄位賦值處理 (`C9`)**：
  - 7 大模組內所有 `@dataclass` 統一加上 `frozen=True`；若既有 `@dataclass` 於 `__post_init__` 中有正規化賦值，統一改用 `object.__setattr__(self, ...)` 或 `dataclasses.replace`，確保完全符合 C9 靜態守門且行為不變。

---

## 3. 開放議題與確認紀錄

- 已對齊主計畫 `umbrella_overview.md` 與 `R01_technical_surface_and_blast_radius_audit.md` 之 `sub_04` 規格，無開放議題，狀態標記為 `Confirmed`。
