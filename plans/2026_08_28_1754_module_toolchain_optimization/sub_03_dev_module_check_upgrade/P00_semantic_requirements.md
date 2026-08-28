# 語意化需求澄清與範疇定義 (Semantic Requirements)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 原始需求與核心意圖 (Original Request & Core Intent)

- **原始需求陳述**：*「針對現有的 python yscb.py dev check 指令進行功能深化與規則擴充」*
- **核心目標**：強化 `dev check` 靜態合規與模組架構守門能力，建立多維度檢查規則、嚴重性分級 (`[PASS]`, `[WARN]`, `[FAIL]`)、Release 剛性阻斷、以及「反模式/重複造輪子」之靶向特徵攔截，保障整個 YS-Codebase 生態系的一致性與純淨度。

---

## 2. 需求討論與決策記錄 (Decision Records)

### [sub_03:P00:DR-01] Manifest 規範與 Core 依賴強制性
- **決策內容**：`manifest.json` 必須包含 `name`, `version`, `entry`, `dependencies`。
- **規則約束**：
  - `version` 必須符合嚴格 SemVer 格式 (`X.Y.Z` 或 `X.Y.Z.build`)。
  - `dependencies` **必須明確包含 `core` 模組**（`core` 本體除外），違者標記 `[FAIL]`。
  - `name` 必須與模組目錄名稱完全一致。

### [sub_03:P00:DR-02] Core 注入完備性檢核
- **決策內容**：檢查模組是否具備 `contributes/core.json` 並宣告基本 CLI 子指令說明 (`commands`) 或語意 URI (`uri_schemes`)。
- **規則約束**：若缺失則標記為 `[WARN]` 提醒建議，不阻斷建置與發布。

### [sub_03:P00:DR-03] 空間穿透防禦 (Zero Probing)
- **決策內容**：全量掃描模組內 `.py` 檔案，嚴禁出現 `module.source://`、`source/` 等源碼空間穿透路徑。
- **規則約束**：除 `dev` 模組自身之構建/打包/腳本工具外，業務模組出現源碼穿透一律標記 `[FAIL]` 並阻斷發布。

### [sub_03:P00:DR-04] 三級嚴重度與 Release 阻斷機制
- **決策內容**：
  - `[PASS]`：模組完全合規。
  - `[WARN]`：建議但不強制，輸出黃色警告/提醒訊息，不阻斷發布。
  - `[FAIL]`：嚴重架構或規範違規，輸出紅色錯誤清單。
- **阻斷約束**：當存在 `[FAIL]` 時，**剛性阻斷 `dev release` 正式發布打包**；但依然允許 `dev build` 以利開發者在本機環境調試修復。

### [sub_03:P00:DR-05] 檔案結構與 Configurable 模板清冊合規
- **決策內容**：
  - 進入點 `scripts/cli.py` 必須存在 (`[FAIL]`)。
  - 測試檔案必須繼承 `dev.testing.case.YSCBTestCase` (`[FAIL]`)。
  - 若模組包含預設組態模板，必須置於 `configurable/` 目錄內，**嚴禁於模組根目錄散落 `config.*.json` 模板** (`[FAIL]`)。
  - 檢查殘留之 `.tmp`、`.bak`、`.DS_Store` 等無效暫存檔案 (`[WARN]`)。

### [sub_03:P00:DR-06] 文檔合規檢查 (`contributes.format.md`)
- **決策內容**：檢查模組目錄是否提供 `contributes.format.md` 擴充手冊。若未提供則標記為 `[WARN]` 提醒。

### [sub_03:P00:DR-07] 反模式靜態靶向攔截 (Reinventing-the-Wheel Detection)
- **決策內容**：精確靶向檢測繞過 SDK 讀寫系統組態與手動探測 contributes 的反模式，**完全不干擾模組日常之原生 `open()`, `json.load()` 操作**。
- **規則約束**：
  - **Direct Config File Access**：非 `core` 模組之業務代碼中出現 `"config.project.json"` 或 `"config.local.json"` 字串常數 ➔ 標記 `[FAIL]`，提示使用 `core.config` SDK。
  - **Direct Contributes Probing**：非 `core` 模組之代碼中出現 `"contributes.merged.json"` 或手動探測 `cache://` 內部 contributes 物化產物 ➔ 標記 `[FAIL]`，提示使用 `core.contributes` SDK。
  - `source/core/` 模組本體與所有模組之 `tests/` 單元測試目錄豁免此項檢測。

---

## 3. 範疇邊界與分流判定 (Scope Boundaries)

- **包含範疇 (In Scope)**：
  - 升級 `source/dev/dev/checker.py` 核心檢核邏輯與 AST 分析引擎。
  - 升級 `source/dev/dev/releaser.py` 與 `source/dev/scripts/cli.py`，整合 `[FAIL]` 阻斷機制。
  - 強化 `python yscb.py dev check` 之終端彩色與結構化診斷報告輸出。
  - 新增單元測試 `source/dev/tests/test_checker.py` 覆蓋所有檢查規則與分級。
- **排除範疇 (Out of Scope)**：
  - 不修改外部模組業務邏輯（除配合修復潛在 check 違規項外）。

---

## 4. 三大分流層級建議 (Phasing Track Recommendation)

- [ ] **Level 0 (Fast Track)**：不適用（涉及多維度靜態規則引擎、Release 守門阻斷與 CLI 輸出重大功能擴充）。
- [x] **Level 1 (Full Track) — (Recommended)**：標準完整開發流程（Phase 0 ~ Phase 7），具備完整需求規格書 (P01)、架構設計 (P02)、API 規格 (P03)、測試計畫 (P06) 與驗收演練。
- [ ] **Level 2 (Umbrella 主計畫)**：本計畫已隸屬於 Umbrella 主計畫下之單一 Full Track 子計畫。
