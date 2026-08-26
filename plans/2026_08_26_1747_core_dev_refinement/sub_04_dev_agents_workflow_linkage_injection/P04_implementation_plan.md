# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 P02 架構設計與 P03 API 規格中有明確對應介面與資產路徑。
- [x] **邊界防護**：EC-01 ~ EC-03 在 `core.engine` 特例下載、缺少 build zip 提示與 Contributes below 模式中有具體防護。
- [x] **依賴純淨**：100% Python 標準庫，符合 NFR-01~02 約束。
- [x] **Test-First 剛性定稿**：`P06_test_plan.md` (FT-01~03, ET-01, RT-01) 已同步剛性定稿 (Confirmed)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- :--- | :---: | :--- |
| **維度 2** | `docs/dev/user_guide.md` | Modify | 補充 `install <mod>@build` 本地建置產物特例安裝指令說明與日常開發閉環。 |
| **維度 4** | `docs/dev/DESIGN_NOTES.md` | Modify | 記錄 `install @build` 特例通道與 `contributes["agents-workflow"]` 宣告式工程規範注入之架構決策。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在未執行 `dev build` 的情況下，直接執行 `python yscb.py install dev@build --force`，系統是否會意外下載到錯誤的 remote 版本或造成鏡像庫損壞？  
> 💡 **防護解法**：`PackageManager.act_download` 在檢測到 `@build` 特例時，強制鎖定 `module.build://` 尋找，絕不回退至 remote provider；若找不到任何 `.build.zip`，立即中斷並拋出明確錯誤引導：`"Build package not found for '{module_name}'. Please run 'python yscb.py dev build {module_name}' first."` (EC-01)。

> ❓ **尖銳問題 2**：`dev` 模組透過 `contributes["agents-workflow"]` 注入規範時，若未來其他擴充模組也需要注入規範，是否會互相覆蓋或產生衝突？  
> 💡 **防護解法**：`dev` 在 `manifest.json` 中採用 `mode: "below"` 模式掛載至 `WORKFLOW_SOP_STANDARDS` 錨點下方，保留錨點行本體供多個模組疊加注入，最終在 Stage 1 編譯結束時由編譯器狀態機安全收斂並抹除殘留錨點標籤 (DR-02)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Dev 工程規範資產建立)**：
  - 新建 `source/dev/assets/standards/DevEngineeringStandards.md`。
  - 冠以「YS-Codebase 模組開發專案特化工程規範」，包含禁止 Agent 主動 release/install 防呆鐵律、三層空間 SSOT、虛擬沙盒測試規範與靜態合規守門。
- [ ] **TASK-02 (Dev Contributes 宣告)**：
  - 修改 `source/dev/manifest.json`，宣告 `contributes["agents-workflow"]`（向 `WORKFLOW_SOP_STANDARDS` 註冊 `insert`, `mode: "below"`）。
- [ ] **TASK-03 (Core Engine @build 特例實作)**：
  - 修改 `source/core/core/engine.py`：
    - `_get_module_manifest_from_provider_or_local` 支援 `@build` Manifest 解析。
    - `act_download` 支援 `@build` 強制自 `module.build://` 下載。
- [ ] **TASK-04 (測試與驗證)**：
  - 在 `source/core/tests/test_engine.py` 與 `source/dev/tests/test_basic.py` 擴充單元測試覆蓋 FT-01~03 與 ET-01。
  - 執行 `agents-workflow release antigravity` 驗證規範物化注入效果。
  - 實機跑測 `python yscb.py dev test --all`（全系統沙盒回歸）。
- [ ] **TASK-05 (知識庫 1:1 交付與結案)**：
  - 更新 `docs/dev/user_guide.md` 與 `docs/dev/DESIGN_NOTES.md`。
  - 追加全域 `CHANGELOG.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 `dev` 模組透過宣告 `contributes["agents-workflow"]`（`mode: "below"`）實現零侵入專案工程規範注入。
- **[P04:DR-02]** 確立 `core.engine` 之 `@build` 本地建置產物特例安裝通道，終結本地開發需先手動 release 的冗餘負擔。
- **[P04:DR-03]** 剛性確立「禁止 Agent 主動 release 與本地自引用安裝」防呆鐵律，Agent 唯一驗證手段為 `dev test` 於隔離沙盒測試。
