# 需求規格說明書 (Requirements Specification)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Dev 模組專屬工程規範資產建立 | 建立 `source/dev/assets/standards/DevEngineeringStandards.md`，章節標題與內文明確冠以 **「YS-Codebase 模組開發專案特化工程規範 (YS-Codebase Module Engineering Standards)」**，收斂四大核心主軸：<br/>1. **禁止主動 release 與本地自引用安裝防呆鐵律**：在開發者未明確下達指示（如「發布/安裝/同步」）前，Agent 絕對禁止主動執行 `dev release` 或 `install` 覆蓋宿主環境；唯一允許的驗證手段為 `dev test` 於隔離沙盒測試。<br/>2. **三層空間邊界與四步閉環流水線**：SSOT `source/`、禁止手動污染 `modules/`、`Source` ➔ `Build` ➔ `Sandbox Test` ➔ `Install/Reload`。<br/>3. **虛擬沙盒測試與除錯規範**：沙盒嚴格位於 `cache://dev/sandbox/`、失敗現場保留機制、加速參數 `--no-build`、`-k`。<br/>4. **模組結構合規與語意 URI 規範**：發布前必跑 `dev check`、全面使用 `storage://`, `cache://`, `module.source://`。 | P0 | [P00:DR-03], [P00:DR-05] |
| **FR-02** | Dev 模組 Contributes 宣告與錨點掛載 | 在 `source/dev/manifest.json` 中宣告 `contributes["agents-workflow"]`，向 `agents-workflow` 現有之 `WORKFLOW_SOP_STANDARDS` 錨點註冊 `insert`（模式為 **`mode: "below"`**），將 `DevEngineeringStandards.md` 宣告式掛載至 `DevelopmentStandards.md` 尾部，保留錨點供多模組疊加注入。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `install @build` 本地建置產物特例安裝 | 在 `source/core/core/engine.py` 的依賴解算 (`_get_module_manifest_from_provider_or_local`) 與下載 (`act_download`) 中擴充特例：<br/>當版本約束或 revision 為 `build`（例 `install <mod>@build` 或 `<mod>@<ver>.build`）時，特例強制直接自本地端 `module.build://{module_name}/` 尋找 `*.build.zip` 並直接物化安裝至 `module.mirror://`，免去開發者本地開發必須手動先跑 release 的冗餘負擔。 | P0 | [P00:DR-04] |
| **FR-04** | 工作流發布自動合成與驗證 | 執行 `agents-workflow release` 時，編譯器自動自 `cache://core/contributes.merged.json` 讀取 `dev` 貢獻之 `insert`，將 `DevEngineeringStandards.md` 注入至發布之 `DevelopmentStandards.md` 中。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `install @build` 時本地尚未執行 `dev build` | 若本地 `module.build://{module_name}/` 不存在任何 `.build.zip` 產物，拋出明確錯誤提示：`"Build package not found for '{module_name}'. Please run 'python yscb.py dev build {module_name}' first."`，不盲目回退至 remote。 |
| **EC-02** | 未安裝 `dev` 模組時之發布純淨性 | 若環境未安裝 `dev` 模組，`agents-workflow` 的 `WORKFLOW_SOP_STANDARDS` 錨點在 Stage 1 解算完成後自動乾淨抹除殘留標籤行，維持 100% 通用純淨。 |
| **EC-03** | `install @build` 指定不同模組名稱 | 支援單獨針對特定模組使用 `@build`，例如 `python yscb.py install dev@build`，其他依賴模組若無 `@build` 標記則維持自一般 provider 解算。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構純淨度 | 100% Python 標準庫，零第三方套件依賴，嚴格遵守 Dogfooding 三層空間邊界。 |
| **NFR-02** | 回歸測試品質 | 模組內部測試與全模組沙盒端到端測試維持 100% 通過（114/114 Passed）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `dev` 模組向 `agents-workflow` 宣告 `contributes` 需經過 `core.contributes` 拓撲合併寫入 `cache://core/contributes.merged.json`，隨後由 `agents-workflow.compiler` 在 Stage 1 讀取展開。
- **`[!IMPORTANT]`** `install @build` 特例必須在依賴拓撲解算與檔案下載兩處皆支援，確保 `installed_modules` 記錄之版本號與 zip 來源一致。
