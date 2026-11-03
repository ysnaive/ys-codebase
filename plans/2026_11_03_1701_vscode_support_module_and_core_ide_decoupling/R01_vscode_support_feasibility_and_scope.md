# 專題調研與分析報告：`module:vscode-support` 關鍵前提實證與範疇評估 (R01_vscode_support_feasibility_and_scope.md)

> 調研主題：`module:vscode-support` 三大前提實證與單一 Full Track 範疇邊界評估  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1701_vscode_support_module_and_core_ide_decoupling  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：在啟動 `module:vscode-support` 實作前，路線圖列出了三項技術前提與 Phase A / B / C 的範疇取捨問題：
  1. **前提 ①（組態模板來源）**：`core/engine.py` 在安裝模組時會物理剝除 `module://<mod>/configurable/`。究竟是否需要修改 `core/engine.py` 額外將模板快照存至 `cache://`，還是可以直接從 `module.mirror://` 取得？
  2. **前提 ②（`configurationDefaults` vs `.vscode/settings.json`）**：能否完全靠本地外掛 `package.json` 的 `contributes.configurationDefaults` 注入 `python.analysis.extraPaths` 與 `files.exclude`，從而彻底不寫入 `.vscode/settings.json`？
  3. **前提 ③（本地外掛啟用摩擦與雙軌 Schema 註冊）**：VS Code `.vscode/extensions/` 本地工作區外掛需使用者手動於「Workspace Recommendations」點擊 Install 並 Reload Window；在 Antigravity / VS Code 衍生環境中如何保證 JSON Schema 100% 可靠生效？
- **調研目標與範疇**：透過本機代碼庫與 `.mirror/` 實證檢驗上述三項前提，並評估單一 Full Track 的最適交付範圍（Phase A + B vs Phase C）。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 前提 ① 實證：`module.mirror://` 原始安裝包完整保留 `configurable/`（免改 `core/engine.py`）

透過實機檢視 `ys_codebase/.mirror/core/1.2.4.0.zip`（以及 `server`、`knowledge-db`、`agents-workflow` 之 `.mirror` 壓縮包）確認：
- `_deploy_and_strip_single_module_config()` 僅剝除已解壓至運行端 `module://<mod>/` 的 `configurable/` 目錄，而位於 `module.mirror://<mod>/<version>.zip` 的原始安裝包 **100% 完整保留 `configurable/config.*.json`**。
- **結論**：`vscode-support` 的 `SchemaCompiler` 在推導組態 Schema 時，只需依序查找：
  1. `module.source://<mod>/configurable/`（母倉或模組開發環境直接讀取目錄）
  2. `module.mirror://<mod>/<installed_version>.zip`（下游純消費環境使用 Python 標準庫 `zipfile` 於記憶體內秒級讀取 `configurable/config.*.json`）
- **架構收益**：**完全無須修改 `core/engine.py` 新增 `configurable.snapshot.json` 機制**，`core` 的變動面縮小至僅需移除 `ide_projector.py`、新增 1 行 `on_env_synced` 廣播與修復 `[TODO-18]` `validator.py`。

### 2.2 前提 ② 評估：`configurationDefaults` 與 `.vscode/settings.json` 之取捨

| 比較維度 | 方案 1：僅靠外掛 `configurationDefaults` | 方案 2：維持 `SettingsProjector` 軟合併 `.vscode/settings.json` + 本地外掛 `package.json` |
| :--- | :--- | :--- |
| **是否需手動安裝外掛才生效** | 是（未點擊 Install local extension 前，Pylance 完全找不到 `.venv` 套件，全倉 import 紅線） | **否**（`install vscode-support` 當下 `.vscode/settings.json` 即刻同步，Pylance 零延遲生效） |
| **相對路徑解析可靠性** | Pylance 對來自 extension `configurationDefaults` 的相對路徑解析隨版本存在差異 | `.vscode/settings.json` 原生支援工作區相對路徑（已於現有 `IdeProjector` 完整驗證） |
| **現有設定相容與可逆性** | 無法清理舊版 `_yscb_managed` 殘留 | 100% 繼承既有 `_yscb_managed` 差集軟合併與 `on_remove` 乾淨還原 |

- **結論**：保留 `SettingsProjector` 對 `.vscode/settings.json` 的 `_yscb_managed` 軟合併，並支援在 `.venv/current-site-packages`（或既有跨平台路徑）投影與單檔 Schema 輸出，兼顧「零手動步驟即刻生效」與「本地外掛完整擴充能力」。

### 2.3 前提 ③ 評估：單檔級 JSON Schema 的零摩擦生效策略

- 生成檔案位置統一收納於 `.vscode/extensions/yscb-vscode-support/`（內含 `.gitignore` 寫入 `*` 自我忽略，不污染 Git 工作區）：
  - `.vscode/extensions/yscb-vscode-support/package.json`（宣告 `contributes.jsonValidation`）
  - `.vscode/extensions/yscb-vscode-support/schemas/contributes/<mod>.schema.json`
  - `.vscode/extensions/yscb-vscode-support/schemas/config/<mod>.schema.json`
  - `.vscode/extensions/yscb-vscode-support/schemas/meta/{format-meta,manifest}.schema.json`
- 為消弭本地外掛「首次需手動點 Install」的摩擦，`SettingsProjector` 在同步 `.vscode/settings.json` 時，亦可選擇性於 `_yscb_managed` 託管下同步指向 `./.vscode/extensions/yscb-vscode-support/schemas/...`（或由外掛 `jsonValidation` 提供），且在 `remove vscode-support` 時一併 100% 抹除還原。

### 2.4 單一 Full Track 範疇切分建議（Phase A + B vs Phase C）

| 階段 | 內容項目 | 複雜度與規模預估 | 風險評估 | 建議處置 |
| :--- | :--- | :--- | :--- | :---: |
| **Phase A** | `core` 移除 `IdeProjector`、新增 `on_env_synced`、修復 `[TODO-18]` `validator.py` 浮點數/負數預設值 | 小（約 40 LOC 修改，淨刪減 `core` 約 270 LOC） | 極低 | **納入本次 Full Track** |
| **Phase B** | 建立 `module:vscode-support`（`SettingsProjector`、`SchemaCompiler`、`WorkspaceExtensionSynthesizer`、`hook.core.py`、`cli.py` `sync/status/revert`、`contributes/_format.json`） | 中（單一新模組約 450~550 LOC + 完整單元測試） | 低（100% Python 標準庫，無外部套件或 JS 依賴） | **納入本次 Full Track** |
| **Phase C** | `agents-workflow` TextMate 語法高亮注入与 Node.js `extension.js`（`DocumentLinkProvider` / `HoverProvider`） | 中高（跨語言引入 JS 腳本與多模組連動） | 中（涉及 VS Code Extension Host JS 執行期與跨模組修改） | **延後（不納入本次計畫）** |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. `module.mirror://` 已完整保存原始 `configurable/`，**無須修改 `core/engine.py`**。
  2. 將 **Phase A + Phase B** 合併於當前單一 Full Track 計畫內實作，規模適中、職責內聚（100% 純 Python 實作、無須升級為 Umbrella），即可一次交付「`core` 零 IDE 假設解耦 + `[TODO-18]` 修復 + `module:vscode-support` 設定同步與全模組單檔級 JSON Schema 自動編譯」。
  3. Phase C（`extension.js` 與跨模組語法高亮注入）建議明確排除於本次計畫之外，保持首次發布乾淨穩定。
- **後續建議**：採納 **出口 ①（立即於本計畫推進 Phase 01~07）**。

