# 需求規格說明書 (Requirements Specification)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 專題報告：[R01_dev_toolchain_refactor.md](./R01_dev_toolchain_refactor.md), [R02_release_toolchain_support.md](./R02_release_toolchain_support.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev build` 自動清空目標目錄與本地打包 | 移除 `--clean` 選項。語法 `python yscb.py dev build [module_name \| --all]`。打包前一律自動清空目標模組專屬的 `build/<mod>/` 目錄，產出 `build/<mod>/<ver>.build.zip`（100% 完整保留 `tests/` 與開發檔案），並自動更新 `build/<mod>/index.json`。 | P0 | [P00:DR-01] |
| **FR-02** | `dev release` 純粹化發布打包與 3-Gate 校驗 | 移除所有版本遞增 (bump)、`-y`、`--dry-run`、`--tag`、`--no-test` 等流水線參數與 Git 操作。語法完全對標 `build`：`python yscb.py dev release [module_name \| --all]`。打包前依序通過 Gate 1（靜態規格）、Gate 2（版本未重複）、Gate 3（版本未倒退）校驗，純淨排除 `tests/` 與 `.yscbignore`，產出 `release/<mod>/<ver>.zip`。 | P0 | [P00:DR-02]<br/>[P00:DR-05] |
| **FR-03** | `dev release` 多版本時序滑動窗口與歷史收斂治理 | 落實發布產物淘汰演算法：<br/>1. **同三元組 (X.Y.Z) 至多保留 3 份 Revision**：依時序/SemVer 由大到小排序，最多保留 3 個最新 Revision（`X.Y.Z.W`, `X.Y.Z.W-1`, `X.Y.Z.W-2`），第 4 份及更舊的 Revision zip 自動刪除。<br/>2. **跨三元組升級舊版收斂 (僅留 1 份 Revision)**：當 `patch` 或以上 level 產生遞增時（版本變為 `X.Y.Z+1.W` 或更高），所有過往舊三元組的延遲保留版本全數清理，舊三元組僅留下最後且最高的 1 個 Revision（`X.Y.Z.W_max`）。<br/>3. **索引實體同步**：`release/<mod>/index.json` 始終以物理磁碟上真實存在的 zip 包為 SSOT 生成與排序，已被刪除的 Revision 100% 排除。 | P0 | [P00:DR-02]<br/>[P00:DR-04] |
| **FR-04** | `dev release --all` 依賴拓撲排序批次發布 | 當執行全量發布時，自動讀取各模組 `manifest.json` 中的 `dependencies` 依賴宣告，建構 DAG 並執行拓撲排序，確保被依賴模組（如 `core`）優先於下游模組（如 `dev`, `agents-workflow`）依序發布。 | P0 | [P00:DR-06] |
| **FR-05** | `dev test` 流水線化與 `--no-build` 支援 | 語法 `python yscb.py dev test [module_name \| --all] [options]`。預設先自動調用 `Builder.build_module` 或 `Builder.build_all` 產出最新 build 產物再進沙盒測試；若傳入 `--no-build` 則跳過 build 直接進入測試沙盒。 | P0 | [P00:DR-03] |
| **FR-06** | `dev bump-*` 獨立版本單向遞增指令 | 新增獨立指令：`dev bump-major <mod>`、`dev bump-minor <mod>`、`dev bump-patch <mod>`、`dev bump-revision <mod>`。讀取 `source/<mod>/manifest.json`，對指定版本段單向遞增並寫回檔案，輸出新舊版本對比。 | P0 | [P00:DR-07] |
| **FR-07** | `dev release-check` 獨立發布就緒預檢 | 新增獨立指令：`python yscb.py dev release-check <module>`（僅支援單一模組，不支援 `--all`）。依序執行 Gate 1 (靜態規格)、Gate 2 (版本未重複)、Gate 3 (版本未倒退) 校驗，若不合格回報錯誤原因並以 exit 1 阻斷。 | P0 | [P00:DR-08] |
| **FR-08** | `dev release-git` 4 步發布與版本控制工具鏈 | 新增指令：`python yscb.py dev release-git <module> <commit msg>`。依序執行：<br/>1. `dev test <module>`（測試失敗即中斷）<br/>2. `dev release-check <module>`（預檢失敗即中斷）<br/>3. `dev release <module>`（純淨發布打包，失敗即中斷）<br/>4. 本地 `git add -A` + `git commit -m "<commit msg>"` + 打上版本 Tag（如 `<module>/v<version>`）。<br/>🚨 **嚴禁自動向遠端 remote 執行 `git push`，僅完成本地端操作**。 | P0 | [P00:DR-09] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **發布重複四元版本阻斷 (Immutability Gate)** | 當嘗試發布的四元版本號（如 `1.0.0.0`）已存在於 `release/<mod>/` 或 `index.json` 時，Gate 2 立即拋出 `ReleaseVersionExistsError` 並中斷發布，杜絕無聲覆蓋。 |
| **EC-02** | **發布版本倒退阻斷 (Monotonicity Gate)** | 當嘗試發布的版本號小於或等於同三元組在庫的最高 revision（或小於在庫歷史版本）時，Gate 3 立即拋出 `VersionRollbackError` 並中斷發布，防止版本序列倒退。 |
| **EC-03** | **`release-git` 任一步驟失敗即中斷** | 若 `test` 失敗、或 `release-check` 失敗、或 `release` 打包失敗，`release-git` 必須立即終止後續所有步驟，絕對禁止執行 Git Commit 與 Git Tag。 |
| **EC-04** | **`release-check` 傳入 `--all` 阻斷** | 若使用者嘗試執行 `dev release-check --all`，CLI 必須立即回報錯誤並提示「`release-check` 僅支援單一模組」。 |
| **EC-05** | **`dev test` 前置 build 失敗阻斷** | 若前置 `build` 過程中靜態合規檢查失敗或打包異常，`test` 必須立即輸出 build 錯誤並中斷，禁止進入沙盒執行測試。 |
| **EC-06** | **拓撲排序循環依賴檢測** | 若多模組間存在循環依賴（如 A 依賴 B，B 依賴 A），`dev release --all` 必須精確輸出循環依賴鏈路並中斷流程。 |
| **EC-07** | **首次發布模組產物目錄初始化** | 若模組為歷史首次發布，`release/<mod>/` 與 `index.json` 尚不存在，發布器必須自動建立目錄並生成初始 `index.json`。 |
| **EC-08** | **非 Git 倉庫環境下執行 `release-git`** | 若當前工作目錄非 Git 倉庫，`release-git` 在完成步驟 1~3 後，於步驟 4 提示警告並優雅退出，不導致未捕獲崩潰。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **純 Python 標準庫** | 工具鏈重構 100% 基於 Python 3.8+ 標準庫（`zipfile`, `os`, `shutil`, `json`, `subprocess`），零第三方外部套件依賴。 |
| **NFR-02** | **Dogfooding 空間隔離** | 嚴格遵循專案自引用三層空間邊界，所有源碼修改 100% 位於 `source/dev/`，測試位於 `test/`，未經編譯發布嚴禁直接修改根目錄產物。 |
| **NFR-03** | **CLI 執行效能** | 單模組 `release-check` 執行耗時 $< 50\text{ms}$；全模組拓撲排序演算耗時 $< 10\text{ms}$。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`**：`dev release-git` 嚴禁自動向遠端倉庫執行 `git push`，所有 Git 提交與 Tag 嚴格限制在本地端完成，杜絕意外推送。
- **`[!WARNING]`**：發布目錄 `release/<mod>/` 中的 zip 檔案與 `index.json` 為微內核安裝源 SSOT，任何淘汰演算法的物理刪除操作必須確保僅刪除舊 Revision，嚴禁誤刪歷史大/次版本或當前活躍版本。
- **`[!NOTE]`**：微內核安裝匹配機制（`core.semver:match_constraint`）在三段式版本依賴下對第四段尾號不敏感，會自動安全解析至該三元組下的最新 revision 發布包。
