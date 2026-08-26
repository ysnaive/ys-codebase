# 語意化需求定義 (Semantic Requirements)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 核心願景與問題陳述

在完成 R01~R05 全量架構白皮書與原始碼交叉審查（參見 [architecture_compliance_checklist.md](../../../brain/b9f3f6f5-de94-477f-9e28-c3b279fe5f8e/architecture_compliance_checklist.md)）後，發現當前實作在以下關鍵維度存在設計偏離與真實部署下的潛在崩潰風險：
1. **宿主組態與專案空間混淆 (BUG-01, BUG-02)**：`AtomicEngine` 錯誤地使用 `project://yscb.config.json` 來存取宿主頂層組態。在真實環境中，`project://` 指向被管理的外部宿主專案（預設為 `!undefined`），當兩者路徑不同或未初始化 `project_root` 時，所有套件管理指令（`install`, `update`, `remove`, `reload`, `rollback`, `list`, `status`）將直接崩潰。
2. **宿主探測隱式猜測 (BUG-03)**：`uri._find_host_config` 在找不到 `yscb.config.json` 時，違背「零臆測 (Zero Speculation)」原則，靜默 fallback 猜測當前目錄與 `./ys_codebase`，掩蓋配置缺失。
3. **Provider 產物標準拓撲與 Index 清冊 (D-06, D-03)**：`dev build` 尚未自動維護 `index.json` 版本索引清單。
4. **相依求解與反向安全防護 (D-02, D-08)**：`act_solve_deps` 目前為 stub，`cmd_remove` 缺少反向相依阻斷。

本子計畫旨在徹底修復上述結構性 Bug 與規範偏離，確保在「真實下游專案接入（`project://` 分離）」與「自引用開發」兩種場景下皆能 100% 穩定無誤。

---

## 2. 使用情境與工作流程 (User Scenarios & Workflows)

### 情境 1：下游獨立專案環境下的套件管理操作 (Real Project Isolation)
- **前置狀態**：專案根目錄為 `/MyProject/`，`ys_codebase` 安裝於 `/MyProject/tools/yscb/`，且 `config.project.json` 中 `project_root` 尚未配置（為 `!undefined`）或配置為 `../../`。
- **操作步驟**：使用者在 `/MyProject/tools/yscb/` 或專案根目錄執行 `python yscb.py install custom_mod`。
- **預期行為**：
  - 系統精確定位 `/MyProject/tools/yscb/yscb.config.json`，不引發 `project://` 零 Fallback 阻斷錯誤。
  - 快照備份至 `snapshot://`（即 `tools/yscb/.snapshots/`），不污染專案空間。
  - 所有套件管理操作正常完成。

### 情境 2：無效或未初始化環境防呆阻斷 (Zero Speculation Guardrail)
- **前置狀態**：在一個完全未初始化的空白目錄執行 `python yscb.py list` 或 `core.uri.resolve("yscb://...")`。
- **操作步驟**：執行指令。
- **預期行為**：系統直接拋出顯式 `FileNotFoundError` 或清晰指引訊息（`Please run 'python yscb.py init <yscbRoot>' first`），嚴禁靜默猜測 `./ys_codebase`。

---

## 3. 系統邊界與排除範疇 (Scope & Exclusions)

### 納入範疇
- 修復 `core.engine` 中所有宿主組態（`yscb.config.json`）讀寫路徑，徹底與 `project://` 解耦。
- 修復 `core.uri._find_host_config` 移除隱式 Fallback 猜測。
- 補齊/加固對應的測試案例（包含「`project_root` 為 `!undefined` 且與宿主目錄完全分離」的隔離整合測試）。
- 討論並判定 D-01~D-08 偏差項目的處置優先級與實作邊界。

### 排除範疇
- `agents-workflow` 業務模組遷移（留待後續獨立主/子計畫）。

---

## 4. 開放議題與討論紀錄 (Open Issues & Discussion Log)

- [x] **議題 1（Critical）：宿主組態定位機制與 `_get_config` / `_save_config` / 快照修復 (BUG-01, BUG-02)**
  - *決策結論*：**採用方案 A（底層實體路徑直接解耦）**。
  - *實作規範*：`AtomicEngine` 中的 `_get_config`、`_save_config`、`act_init`、`act_snapshot` 與 `act_restore_snapshot` 統一呼叫 `uri._find_host_config()` 取得 `host_dir`，直接以 `os.path.join(host_dir, "yscb.config.json")` 進行實體讀寫與快照，徹底與 `project://` 解耦。
  - *狀態*：✅ Confirmed

- [x] **議題 2（Critical / High）：`core.uri._find_host_config` 移除隱式猜測與 `yscb://` 常數特化定錨 (BUG-03)**
  - *決策結論*：
    1. **`yscb://` 保留原生特化解算**：作為整個 VFS 與依賴注入體系的最底層根錨點，其路徑直接基於 `core` 實體代碼位置（`__file__` 往上 3 層）常數確定性錨定，保證自引用極早期第一次自舉注入正常運作。
    2. **宿主組態透過 Context 注入**：`host_dir` 與 `yscb.config.json` 由宿主顯式注入（或確定性依賴注入路徑），徹底廢除向上動態爬目錄與 `os.getcwd()` 隱式猜測。
  - *狀態*：✅ Confirmed

- [x] **議題 3（Medium）：`dev build` 自動生成/維護 `index.json` 版本清冊 (D-06)**
  - *決策結論*：在 `dev build` 完成打包後，自動掃描 `build/{module}/` 下現存版本目錄，生成/更新包含 `name`, `description`, `versions: [...]` 的標準 `index.json`。
  - *狀態*：✅ Confirmed

- [x] **議題 4（Medium）：`remove` 反向相依安全防護機制 (D-08)**
  - *決策結論*：在 `cmd_remove` 執行前，自動掃描所有已安裝模組之 `dependencies`；若有其他模組依賴目標模組且未指定 `--force`，顯式阻斷並提示相依模組清單。
  - *狀態*：✅ Confirmed

- [x] **議題 5（Low / Minor）：Manifest 相依格式、`cmd_init` 頂層組態欄位與文檔齊全度 (D-01, D-04, D-05)**
  - *決策結論*：
    1. 相依解析支援 Dict 與 List 雙向相容。
    2. `yscb.py` `cmd_init` 補齊 `"default_provider": provider_arg`。
    3. `source/dev/` 補齊 `contributes.format.md` 說明書。
  - *狀態*：✅ Confirmed

- [x] **議題 6（Medium）：`act_solve_deps` 相依拓撲解析之實作顆互度 (D-02)**
  - *決策結論*：**採用方案 A（實現遞迴相依拓撲收集）**。
  - *實作規範*：`act_solve_deps` 讀取目標模組之 manifest，若含有 `dependencies`（支援 dict 與 list 格式），遞迴排解拓撲順序，返回拓撲排序後的待安裝清冊 `[(dep_1, ver_1), ..., (target, target_ver)]`。
  - *狀態*：✅ Confirmed

---

## 5. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：目前討論已完整，無其他新議題
