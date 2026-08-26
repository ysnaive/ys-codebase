# 需求規格說明書 (Requirements Specification)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

為確保 R01~R04 四大調研的所有環節無死角落實，將需求細化為 6 大核心功能規格：

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應調研與 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **模組資料三位一體確立、Git 策略與 temp 廢除** | 1. 核心正式確立三大資料協議：`storage://` (持久化/Git 追蹤)、`cache://` (快取/UX暫態/Git 忽略)、`config://` (專案設定/Git 追蹤)。<br>2. 確立 Git 版本控制策略：`yscb://storage/` 與 `yscb://config/` 100% 納入 Git 追蹤；`yscb://.cache/` 100% 納入 `.gitignore` 忽略。<br>3. 正式廢除 `temp://` 協議與 `yscb://.temp/` 物理目錄，所有臨時環境、程序互斥鎖與測試沙盒 100% 併入 `cache://`（如 `cache://.yscb.lock`、`cache://sandbox/`）。 | P0 | [P00:DR-02], R01 |
| **FR-02** | **方案 B 全量 Root 化與 `@/` 自省解算引擎** | 1. 廢除全系統所有 `*.root://` 協議（`storage.root`, `cache.root`, `config.root`, `module.root`, `module.source.root`, `module.build.root`, `module.release.root`, `module.mirror.root`），協議庫精簡 50%（僅保留 8 個核心標準協議）。<br>2. 顯式跨模組尋址：`{scheme}://{module}/{path}`（如 `storage://agents-workflow/manifest.json` ➔ `yscb://storage/agents-workflow/manifest.json`）。<br>3. 當前模組自省尋址：`{scheme}://@/{path}`（如 `storage://@/manifest.json` 自動綁定當前活躍模組）。<br>4. 空間根目錄存取：`{scheme}://` ➔ `yscb://{dir}/`。<br>5. 徹底消除雙重嵌套歧義，提供舊協議相容轉向與 DeprecationWarning 提示。 | P0 | [P00:DR-03], R02 |
| **FR-03** | **模組資料全生命週期自動化治理與 `--purge`** | 1. `core:remove <mod>` (標準卸載)：自動物理清空 `cache://{mod}/`（不留垃圾快取），預設安全保留 `storage://{mod}/` 與 `config://{mod}/`。<br>2. `core:remove <mod> --purge` (深度清除)：擴充 CLI 參數 `--purge`，強制物理銷毀 `storage://{mod}/`、`config://{mod}/` 與 `cache://{mod}/`。<br>3. `core:update <mod>` (升級)：自動清空 `cache://{mod}/` 防止跨版本舊快取污染，Deep-Infill `config://{mod}/`，安全保留既有 `storage://{mod}/`。<br>4. `core:install <mod>` (安裝)：初始化模組空間，Deep-Infill 部署範本組態至 `config://{mod}/`。 | P0 | [P00:DR-04], R03 |
| **FR-04** | **`core` 基礎設施與 CLI 工具鏈無損遷移** | 1. 重構 `core/manifest.json`：更新 contributes 之 uri_schemes，移除 8 個 `*.root` 與 `temp`。<br>2. 重構 `core/core/uri.py`：更新 `_BOOTSTRAP_FALLBACK_SCHEMES`，重構 `resolve()` 支援方案 B 與 `@/` 引擎，消除 `contributes.merged.json` 之 `os.path.join` 硬編碼改走 `cache://core/contributes.merged.json`。<br>3. 重構 `core/core/engine.py`：將互斥鎖 `temp://.yscb.lock` 改為 `cache://.yscb.lock`，消除 `os.path.join(..., 'storage', ...)` 硬編碼改走 `storage://{module}`，在 `act_reload` 與 `act_delete` 中落實生命週期快取自動清理與 `--purge` 邏輯。<br>4. 重構 `core/core/installer.py` 與 `core/scripts/cli.py`：支援 `remove <module> [--purge] [--clean] [--force]`。 | P0 | [P00:DR-05], R04 |
| **FR-05** | **`dev` 開發工具鏈與沙盒測試環境全面遷移** | 1. 重構 `dev/manifest.json`：移除 `module.source.root`、`module.build.root`、`module.release.root`。<br>2. 重構 `dev/dev/testing/sandbox.py` 與 `case.py`：將測試沙盒路徑自 `temp://{id}` 全面遷移為 `cache://sandbox/{id}`。<br>3. 重構 `dev/dev/builder.py`、`releaser.py`、`checker.py`、`runner.py`、`scaffold.py`、`contract.py`：全面移除 `*.root://`，改用 `module.source://`、`module.build://`、`module.release://`、`module://`。 | P0 | [P00:DR-05], R04 |
| **FR-06** | **`agents-workflow` 模組重構與 `release_manifest.json` 錯誤路徑修復** | 1. 修復 `publisher.py` 中的 `MANIFEST_STORAGE_URI`，改寫為 `storage://@/release_manifest.json`（或 `storage://agents-workflow/release_manifest.json`），確保寫入 `storage/agents-workflow/release_manifest.json`，並安全清理/遷移歷史誤建的 `storage/core/agents-workflow/`。<br>2. 重構 `compiler.py`：消除 `.cache` 硬編碼，統一使用 `cache://@/resolved_contents/...`。<br>3. 更新 `agents-workflow/manifest.json` 與所有工作流模板中的 URI 引用，移除 `module.root://` 改為 `module://`。 | P0 | [P00:DR-05], R04 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **無上下文環境下調用 `@/` 自省語法** | 當調用 `storage://@/file.json` 時，若當前 `ExecutionContext` 與 `_active_module_context` 均未設定且未傳入 `current_module`，`uri.resolve()` 必須強制拋出 `UndefinedModuleContextError`，嚴禁盲目 fallback 到 `"core"` 造成資料污染。 |
| **EC-02** | **路徑穿越攻擊與邊界溢出 (Path Traversal)** | 當 URI 包含 `storage://@/../../secret.json` 或 `cache://../../../root` 時，VFS 解算器必須進行實體目錄沙盒校驗，若解析後路徑溢出其所屬根目錄，立即拋出 `SecurityError` 阻斷。 |
| **EC-03** | **舊版 `*.root://` 協議向下相容警告與過渡** | 在遷移過渡期間，若外部腳本或舊版設定誤調用 `storage.root://` 等舊協議，解算器應輸出結構化 `DeprecationWarning` 並自適應重定向至新協議（如 `storage.root://foo` ➔ `storage://foo`），確保不發生硬崩潰。 |
| **EC-04** | **`--purge` 清除時目標目錄不存在** | 若執行 `remove --purge` 時該模組從未產生過 `storage` 或 `config` 目錄，系統應平滑略過，不拋出 `FileNotFoundError`。 |
| **EC-05** | **`release_manifest.json` 遷移時歷史遺留檔案防護** | 在修復 `publisher.py` 時，若檢測到歷史遺留的 `storage/core/agents-workflow/release_manifest.json`，且目標 `storage/agents-workflow/release_manifest.json` 尚未存在，自動平滑遷移該檔案並刪除舊目錄，防止版本清冊遺失。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **解算效能 (Performance)** | `uri.resolve()` 具備記憶體 Fast-Path 與正規化快取，單次 URI 解析平均延遲 $\le 0.05\text{ms}$，在大規模批次遍歷時零明顯效能損耗。 |
| **NFR-02** | **架構純淨性 (Purity)** | 100% 依賴 Python 標準庫，零第三方相依（Zero Third-Party Dependencies）。 |
| **NFR-03** | **測試覆蓋率 (Regression)** | 全代碼庫全模組測試套件維持 **100% 通過 (All Passed)**，包含契約測試、自省測試、沙盒隔離測試、`--purge` 專屬測試與 `@/` 語法測試。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** **上下文污染陷阱**：在測試或多模組連續執行時，必須確保使用 `with uri.module_scope(module_name):` 上下文管理器，100% 保證退出區塊時還原 `_active_module_context`，防止測試相互污染。
- **`[!WARNING]`** **`storage/` 實體搬移安全**：在修正 `release_manifest.json` 位置時，需安全遷移或同步清理 `storage/core/agents-workflow/` 遺留檔案，避免發布清冊雙份分叉。
- **`[!NOTE]`** **測試案例同步升級**：全代碼庫測試中約有 50+ 處舊 `temp://` 與 100+ 處 `*.root://` 斷言，必須在 Phase 5/6 同步更新，確保流水線 100% 綠燈。
