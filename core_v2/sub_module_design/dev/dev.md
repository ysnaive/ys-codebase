# 子模組架構設計規格：`dev 2.0`（模組開發工具鏈、靜態憲法守門與二層部署導向測試框架）

> **所屬功能域**：`獨立開發工具鏈模組 (core_v2/source/dev/)`
> **模組類型**：`Tier 0`（100% Python 3.11+ 標準庫，零第三方依賴）
> **依賴上限（Allowed Imports）**：`core.surface.sdk`、`core.foundation.{primitives, errors, proc}`（以及僅供 `dev check` / `dev build` 靜態分析使用的標準庫 `ast` / `zipfile`）
> **狀態**：`Draft — Prototype Design`（核心方向已對齊，細部介面與 CI 宣告格式待後續專題討論定案）

---

## 1. 定位與從 `dev 1.x` 到 `dev 2.0` 的核心演化

`dev 2.0` 承接 1.x 的腳手架、合規檢查、打包建置、測試執行與發布流水線職責，並針對 1.x 的歷史痛點進行根因重構：

| 維度 | `dev 1.x` 作法 | `dev 2.0` 設計方向 |
| :--- | :--- | :--- |
| **測試環境本質** | `op-mksb` 將宿主 `.modules/`、`source/`、`config/` 硬拷貝並以 Junction 掛載 `.venv`（測的是開發機副本） | 分化為**「共用沙盒 `@build` 邏輯測試」**與**「乾淨目錄從零部署 E2E 測試」**兩層，達成真正的部署驗收 |
| **測試前置自治** | 動態掃描 `scripts/hook.dev.py` | **徹底廢除 `hook.*.py`**，獨立部署測試改由下游／模組宣告真實建置與組態指令 |
| **失敗保留判定** | 測試方法結尾強制手寫 `self.mark_passed()` | **正式淘汰 `mark_passed()`**；統一由標準庫 `unittest.TestResult` 掛鉤判定成功／失敗並決定是否保留現場 |
| **測試底座依賴** | 標準庫 `unittest` | **維持 100% 純標準庫 `unittest`** 保住 `dev` 的 Tier 0 零依賴特性（輔以輕量參數化與 dataclass diff helper）；層級 2 允許下游透過測試指令自行呼叫外部測試工具（如 `pytest`） |
| **靜態守門範圍** | 8 步模組結構與 CLI 契約檢查 | **吸收升級現有 `Gate 0`**：區分 `core` 內核憲法模式與下游業務模組模式，並納入 `YSCB_*` / `_YSCB_*` 環境變數守門 |
| **版本與發布帳本** | 四段式 `Major.Minor.Patch.Revision` + `index.json` 雙軌帳本（`versions` 3-Revision 視窗 + `releases` 全歷史防回退） | **完整繼承**，並於 `dev build` 新增靜態編譯 `tasks.index.json` 供 `core.surface.cli` 毫秒啟動 |

---

## 2. 四大核心支柱雛型 (Core Pillars)

### 2.1 `dev check 2.0`（統一靜態 AST 架構憲法守門器）
將現行 `core_v2/tests/test_gate0.py` 的 AST 靜態分析能力抽取收斂為雙模式規則引擎：
1. **Core 內核模式**：檢查六大功能域嚴格單向匯入 DAG、0 `Any`、禁非法動態反射（僅白名單放行）、Active Living Spec 公開符號與簽名 1:1 對齊、禁止已退役符號殘留。
2. **下游業務模組模式**：
   - 公開匯入邊界僅允許 `core.surface.sdk` 與 `core.foundation.{primitives, errors}`。
   - 靜態封殺裸 `open()`、`os.path`、`threading.Lock`、`pickle`、直接改動 `sys.path`、私開 `yscb.py` 子進程與 `scripts/hook.*.py` 殘留。
   - 強制落實 [foundation.md](../foundation/foundation.md) 定義之 **`YSCB_*` vs `_YSCB_*` 環境變數命名與存取守門**（未登記禁止任意讀取 `os.environ`）。
   - 驗證 `Module` / `TaskGroup` / `@task` / `@on_event` / `@periodic` 宣告合法性與 `manifest.json` 完整性。

### 2.2 `dev test 2.0`（二層部署導向測試模型 + Core 專屬壓測）

全層強制啟用 `-W error::ResourceWarning` 與防宿主穿透守門（`_YSCB_TEST_SANDBOX=1` + 顯式 `HostPath`，嚴禁回退 `os.getcwd()`）：

1. **層級 1：日常邏輯與契約測試（共用單一沙盒 + 受測 `@build`）**
   - 維護單一工作區級共用沙盒，避免反覆建置目錄與 I/O 開銷。
   - **非受測模組**：從當前 `yscb.config` 取用，且**僅限受測模組 `manifest.dependencies` 宣告之依賴閉包**（防止漏宣告隱性依賴）。
   - **受測模組**：一律以打包後之 **`@build` 產物**引入沙盒（提早攔截漏打資產、`contributes/` 或 `tasks.index.json` 錯誤）。
   - 支援在測試內搭配 `YscbClient.local` 執行快速業務邏輯與事件契約驗證，並內建 Auto-Contract 2.0 動態契約測試。
   - 禁止於共用沙盒執行破壞全域環境的模組卸載／升級操作。
2. **層級 2：獨立乾淨部署測試（Clean-Room Deploy E2E）**
   - 建立 **100% 空白隔離目錄**（不拷貝宿主環境），由下游或模組宣告完整的 **CI 建置指令** 與 **測試指令**（涵蓋初始化、安裝 `@build`、寫入組態、執行實際驗證），達成「本機測試與遠端 CI 同構」的真部署驗收。
   - 執行完畢由標準 `TestResult` 自動裁決：通過即銷毀，失敗則保留除錯現場（延續 1.x 滾動上限 3 個沙盒與全通清空機制）。
3. **Core 內核專屬壓力套件（Kernel Live Stress）**
   - 現行 `RC-01~RC-08` 屬於 `core` 內核獨有之多進程競態／交棒／跨進程鎖壓測，保留為 `core` 專屬高壓套件，後續掛載於 `dev test core` 的高壓模式，不強制耦合至一般業務模組測試基類。

### 2.3 `dev build 2.0` & `dev release 2.0`
* `dev build`：靜態掃描並編譯 `tasks.index.json`，產出本機開發驗證包 `@build.zip`（供層級 1/2 測試與本機 Dogfooding）。
* `dev release` / `dev bump-*`：延續四段版號、`index.json` 雙軌帳本（防版本倒退）與事後修補保護。

---

## 3. 分期推進策略 (Phased Delivery)

* **Phase 1（僅依賴 Wave 1.1 內核）**：待以下未決細節討論完成後，可先抽離 `dev.checker` 雛型與輕量 `dev.testing` 雛型進行概念驗證。
* **Phase 2（待 Wave 1.2 補齊 `metadata`、`packaging`、`surface.cli` 與 `core_v2/yscb.py` 後）**：正式接軌 `dev build`（`tasks.index.json`）、層級 1 `@build` 自動部署、層級 2 CI 獨立沙盒與 `dev create / release`。

---

## 4. 待深入討論與延後定案項目 (Open Design Questions)

以下項目刻意保持開放，**尚未凍結定案**，將於後續設計討論與 CI 格式規劃時逐一拍板：

1. **層級 1 `unittest` 開發體驗細部設計**：
   - 共用沙盒之具體生命週期、唯讀防護邊界與 `@build` 增量更新策略。
   - `dev.testing` 擬內建之標準庫 helper 集合（如參數化裝飾器、`dataclass` diff 斷言、`YscbClient.local` 測試基類 API 與 Auto-Contract 2.0 清單）。
2. **層級 2 獨立部署測試與 CI 宣告格式（延後至設計 CI 格式時一併拍板）**：
   - 下游建置指令與測試指令的宣告檔格式（檔名、Schema、變數佔位符與跨平台 `argv` 規範）。
   - Tier 1 重型依賴模組（如 `ast` / `knowledge-db`）在乾淨沙盒內的本地 wheel/env 快取透傳與 `--cold-network` 切換策略。
3. **既有 `core_v2/tests/` 整合時機**：
   - `test_gate0.py` 規則抽入 `dev.checker` 的切分方式，以及既有分域測試套件（`foundation_fs` / `surface_sdk` / `runtime_daemon` / `rc_e2e`）與 `dev test core` 的接軌邊界。
