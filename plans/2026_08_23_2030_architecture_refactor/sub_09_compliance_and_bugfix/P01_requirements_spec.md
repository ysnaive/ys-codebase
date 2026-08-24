# 需求規格定義書 (Requirements Specification)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

所有需求皆嚴格 1:1 轉譯自 `P00_semantic_requirements.md` 中的 6 大決策議題，嚴禁新增未經討論之功能：

| 需求編號 | 需求名稱 | 核心規則與行為規範 | 對應 P00 語意 | 優先級 |
| :--- | :--- | :--- | :--- | :---: |
| **FR-01** | 宿主組態與專案空間實體路徑解耦 | `AtomicEngine` 中的 `_get_config()`、`_save_config()`、`act_init()`、`act_snapshot()` 與 `act_restore_snapshot()` 統一使用宿主目錄實體路徑操作 `os.path.join(host_dir, "yscb.config.json")`，徹底與 `project://` 解耦，確保 `project_root` 未定義或分離時套件管理零阻斷。 | P00 議題 1 (BUG-01, BUG-02) | 🚨 P0 |
| **FR-02** | `core.uri` 代碼位置常數確定性定錨與 Context 注入 | 1. `yscb://` 保留原生特化常數解算，直接由 `uri.py` 代碼位置（`__file__` 往上 3 層）確定性自定位。<br/>2. 宿主目錄透過 Context 顯式注入（支援 `set_host_dir` API 與 `YSCB_HOST_DIR` 環境變數）。<br/>3. 徹底移除動態向上爬目錄迴圈與 `os.getcwd()` fallback 猜測；找不到組態時直接拋出顯式 `FileNotFoundError`。 | P00 議題 2 (BUG-03, D-07) | 🚨 P0 |
| **FR-03** | `dev build` 自動維護 `index.json` 版本清冊 | `Builder.build_module()` 完成純淨打包後，自動掃描 `build/{module}/` 下現存版本目錄，生成或更新標準 `build/{module}/index.json`（包含 `name`, `description`, `versions: [...]`）。 | P00 議題 3 (D-06) | 🟡 P2 |
| **FR-04** | `cmd_remove` 反向相依安全阻斷防護 | `cmd_remove` 在執行 `UNREGISTER` 前，自動掃描所有已安裝模組的 `manifest.json`。若有其他模組宣告依賴目標模組且未帶 `--force`，拋出錯誤並阻斷移除；帶 `--force` 時輸出 Warning 允許強制移除。 | P00 議題 4 (D-08) | 🟡 P2 |
| **FR-05** | 相依格式雙向相容與 `cmd_init` 組態齊全度 | 1. 模組相依解析函式支援 Dict 格式 `{"core": ">=1.0.0"}` 與 List 格式 `["core >=1.0.0"]` 雙向解析。<br/>2. `yscb.py` `cmd_init` 寫入包含 `"default_provider": provider_arg` 的完整初始組態。<br/>3. 於 `source/dev/` 補齊 `contributes.format.md` 說明書。 | P00 議題 5 (D-01, D-04, D-05) | 🟢 P3 |
| **FR-06** | `act_solve_deps` 遞迴相依拓撲解析 | `AtomicEngine.act_solve_deps()` 讀取目標模組 manifest，若包含 `dependencies`，遞迴解析相依關係並返回拓撲排序後的待安裝清冊 `[(dep_1, ver_1), ..., (target, target_ver)]`；檢測到循環依賴時拋出錯誤阻斷。 | P00 議題 6 (D-02) | 🟡 P2 |

---

## 2. 邊界條件與異常處理清單 (Edge Cases)

| 邊界編號 | 邊界與異常情境 | 系統防禦與降級行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | `project_root` 為 `!undefined` 或為外部獨立專案目錄 | 執行所有 `yscb.py` 套件管理指令（`install`, `update`, `reload`, `status`, `list` 等）均能正常讀寫 `yscb.config.json`，絕不因 `project://` 未定義而拋出 `ValueError`。 | FR-01 |
| **EC-02** | 在未初始化的目錄中執行 `core.uri.resolve("yscb://...")` 且未注入 Context | 系統直接拋出顯式 `FileNotFoundError`，絕不進行任何隱式目錄探測或猜測 `./ys_codebase`。 | FR-02 |
| **EC-03** | 嘗試移除被其他已安裝模組依賴之模組（如 `dev` 被 `A` 依賴） | `cmd_remove` 阻斷並輸出：`Error: Cannot remove 'dev' because it is required by: A. Use --force to override.`，Exit Code 為 1。 | FR-04 |
| **EC-04** | 帶有 `--force` 旗標執行移除被依賴模組 | 系統輸出 Warning 提示後放行移除，並執行 `RELOAD` 刷新運行端。 | FR-04 |
| **EC-05** | `dev build` 對同模組多次建置不同版本（例 `1.0.0`, `1.1.0`, `0.9.0`） | `index.json` 中的 `versions` 陣列自動保持 SemVer 排序且不含重複版本。 | FR-03 |
| **EC-06** | `act_solve_deps` 遇到循環依賴（例 `A -> B -> A`） | 檢測到遞迴造訪節點時拋出 `ValueError("Circular dependency detected in module dependencies")` 顯式阻斷。 | FR-06 |

---

## 3. 非功能性需求 (Non-Functional Requirements)

| 需求編號 | 維度 | 驗收標準 |
| :--- | :--- | :--- |
| **NFR-01** | **零第三方依賴** | 100% 採用 Python 3.10+ 原生標準庫，絕不引入額外外部套件。 |
| **NFR-02** | **極致解析效能** | `yscb://` 常數解算與相依拓撲排序均在微秒 ($<0.1\text{ms}$) 級別完成。 |
| **NFR-03** | **回歸測試保證** | 全量測試套件（Auto-Contract + 持久化測試 + 下游專案隔離測試）100% Passed。 |

---

## 4. 專案特化擴充判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| sop_ext 清單 | on_demand | ❌ 排除 (Excluded) | 本子計畫專注於微內核路徑解耦、定錨機制修正與工具鏈合規補齊，不涉及業務特化擴充 |

---

## 5. 決策紀錄 (Decision Records)

### [P01:DR-01] 宿主組態檔案操作與 `project://` 徹底隔離
- **結論**：`AtomicEngine` 內部所有對 `yscb.config.json` 的讀寫、清冊維護與快照還原，一律依賴宿主目錄實體路徑，嚴禁透過 `project://` 解析。
- **理由**：`project://` 代表外部被管理專案，宿主組態是工具庫自身的基礎設施，兩者在架構職責上完全正交。

### [P01:DR-02] `yscb://` 由代碼樹常數確定性定錨，廢除模糊爬目錄探測
- **結論**：`yscb://` 解析基礎直接以 `core` 模組代碼位置（`__file__` 往上 3 層）常數錨定，宿主 Context 顯式傳遞，徹底移除向上 `while` 爬目錄迴圈與 `os.getcwd()` 猜測。
- **理由**：徹底根除環境路徑漂移與跨環境執行時的隱性 Bug，貫徹「零臆測」鐵律。

---

## 6. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：P01 需求規格書與邊界條件確認無誤，可進入 Phase 2
