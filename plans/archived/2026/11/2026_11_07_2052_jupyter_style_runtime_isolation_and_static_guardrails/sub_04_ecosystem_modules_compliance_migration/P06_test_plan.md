# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_04_ecosystem_modules_compliance_migration  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Passed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元與契約測試 | 驗證 `file-space`、`vscode-support`、`gdrive-support` 模組生產輸出遷移至 `core.log`、頂層可變狀態收斂至 `RuntimeContext` 與 `@dataclass(frozen=True)` 相容性 | FR-01, FR-03, FR-04 | `python yscb.py dev test file-space -q --sync` / `python yscb.py dev test vscode-support -q --sync` / `python yscb.py dev test gdrive-support -q --sync` |
| **FT-02** | 單元與契約測試 | 驗證 `dev` 模組 `core.log` 遷移、`get_virtual_cwd()` 虛擬目錄查找、`subprocess.run(..., timeout=...)` 超時防禦與 `@dataclass(frozen=True)` | FR-01, FR-02, FR-04 | `python yscb.py dev test dev -q --sync` |
| **FT-03** | 單元與契約測試 | 驗證 `ast` 模組 `core.log` 遷移、`Path(get_virtual_cwd()).resolve()` 路徑正規化、`RuntimeContext.module_states` 方言與連結快取代理、`core.loader.load_module_from_path` 動態載入與 `@dataclass(frozen=True)` | FR-01, FR-02, FR-03, FR-04 | `python yscb.py dev test ast -q --sync` |
| **FT-04** | 單元與契約測試 | 驗證 `knowledge-db` 模組 `core.log` 遷移、`Path(get_virtual_cwd()).resolve()`、`_GLOBAL_ENGINE_INSTANCE` / `_GLOBAL_INDEX_CACHE` / `_ACTIVE_WORKER` PEP 562 相容代理與兩階段背景同步 | FR-01, FR-02, FR-03, FR-04 | `python yscb.py dev test knowledge-db -q --sync` |
| **FT-05** | 單元與契約測試 | 驗證 `agents-workflow` 模組 `core.log` 遷移、A2 無阻塞確認（移除裸 `input()`）、`Path(get_virtual_cwd()).resolve()`、頂層不可變容器與 `@dataclass(frozen=True)` | FR-01, FR-02, FR-03, FR-04 | `python yscb.py dev test agents-workflow -q --sync` |
| **ET-01** | 邊界測試 | 驗證白箱單元測試直接讀寫 `_GLOBAL_ENGINE_INSTANCE`、`_GLOBAL_INDEX_CACHE`、`_DIALECT_INSTANCES`、`_LAST_LINKER_CACHE` 與 `redirect_stdout` / `redirect_stderr` 攔截時 100% 向後相容，且有狀態索引與 DTO 凍結互不干擾 | EC-01, EC-02, EC-03, EC-04 | `python yscb.py dev test knowledge-db -q` / `python yscb.py dev test ast -q` |
| **RT-01** | 靜態合規與全倉回歸測試 | 驗證上層 7 大模組共 115 個非測試 `.py` 檔案達成 A1~F13 靜態守門 0 違規，且全倉 `dev check --all`（9/9 模組）與 `core`、`server` 回歸測試 100% 通過 | NFR-01, NFR-02 | `python yscb.py dev check --all` / `python yscb.py dev test core -q` / `python yscb.py dev test server -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `file-space`: `Pass: 17(100.0%), Fail: 0`；`vscode-support`: `Pass: 22(100.0%), Fail: 0`；`gdrive-support`: `Pass: 34(100.0%), Fail: 0`；均已完成 `@build` 同步 | 2026-11-08 |
| **FT-02** | `Passed` | `dev`: `Pass: 109(100.0%), Fail: 0, Skip: 0`，已完成 `dev@build` 同步 | 2026-11-08 |
| **FT-03** | `Passed` | `ast`: `Pass: 37(100.0%), Fail: 0, Skip: 0`，已完成 `ast@build` 同步 | 2026-11-08 |
| **FT-04** | `Passed` | `knowledge-db`: `Pass: 112(100.0%), Fail: 0, Skip: 0`，已完成 `knowledge-db@build` 同步 | 2026-11-08 |
| **FT-05** | `Passed` | `agents-workflow`: `Pass: 145(100.0%), Fail: 0, Skip: 0`，已完成 `agents-workflow@build` 同步 | 2026-11-08 |
| **ET-01** | `Passed` | 白箱狀態代理、PEP 562 `__getattr__`、`redirect_stdout`/`redirect_stderr` 串流攔截與非阻塞初始化防呆均 100% 通過 | 2026-11-08 |
| **RT-01** | `Passed` | 7 大上層模組 AST 靜態掃描 `TOTAL: 0` 違規；`core` (`Pass: 281, Fail: 0`)、`server` (`Pass: 63, Fail: 0`) 與 `dev check --all` (`9 Total, 9 Passed, 0 Warnings, 0 Failed`) 100% 通過 | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認上層 7 大模組（`dev`, `file-space`, `ast`, `knowledge-db`, `agents-workflow`, `vscode-support`, `gdrive-support`）已完成 `@build` 自部署同步，且 `python yscb.py dev check --all` 與 `python yscb.py server status` 運行正常 | `Pending` | 待驗收 |
