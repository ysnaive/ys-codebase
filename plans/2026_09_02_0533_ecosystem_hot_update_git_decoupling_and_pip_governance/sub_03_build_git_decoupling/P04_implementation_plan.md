# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中均有具體合約與實作拓撲對應。
- [x] **邊界防護**：EC-01 ~ EC-04 均有清晰防禦機制（自動建目錄、零過渡純淨隔離、沙盒對齊、軟合併保護）。
- [x] **依賴純淨**：符合 NFR-01~03 指標約束（零效能損耗、Git 完全忽略、生態系 100% 回歸相容）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **最高工程規範** | `docs/_project/STANDARDS.md` | Modify | 修訂空間協議表第 1 節，`module.build` 系列政策標記為 `🚫 忽略`，實體路徑更名為 `yscb://.build/`。 |
| **模組手冊** | `docs/core/README.md` | Modify | 更新空間協議表與說明，標明建置空間為 `yscb://.build/`。 |
| **源碼手冊** | `source/core/README.md` | Modify | 更新空間協議表中 `module.build` 映射。 |
| **全域發布日誌** | `CHANGELOG.md` | Modify | 記錄本子計畫 `sub_03` 變更明細與交付成果。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者本地歷史殘留舊的 `build/` 目錄，`dev build` 或 `restore` 是否可能產生路徑混淆或讀取到過期產物？  
> 💡 **防護解法**：在 `core.json`、`core.uri`、`dev.builder` 與 `yscb.py` 中，所有建置產物存取路徑均剛性收斂為 `.build`。建置時必定產出至 `.build/`，還原時亦優先探測 `.build/`。工具鏈絕不主動探測或讀寫舊 `build/`，杜絕任何過期產物干擾，下游端可隨時無痛手動刪除舊目錄。

> ❓ **尖銳問題 2**：沙盒隔離環境執行 `python yscb.py dev test <mod>` 時，如何確保提取到的是 `.build/` 的最新產物？  
> 💡 **防護解法**：`SandboxProvisioner` 透過語意協議 `module.build://` 定位宿主建置空間，由於空間協議解析目標已統一變更為 `yscb://.build/`，沙盒將自動定位並提取宿主 `.build/` 下的最新 ZIP 套件解壓覆蓋，確保 Dogfooding 沙盒測試完全一致。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：更新 `yscb.py` 內部的 `_generate_internal_gitignore` 標記區塊，注入 `/.build/\n` 忽略規則 (FR-01)
- [ ] **TASK-02**：更新 `yscb.py` 模組還原提取函式 `_restore_module_package`，將 `build_candidates` 優先探測路徑改為 `.build/` (FR-04)
- [ ] **TASK-03**：更新 `source/core/contributes/core.json` 與 `source/core/core/uri.py`，將 `module.build` 空間協議預設解析值改為 `yscb://.build/` (FR-02)
- [ ] **TASK-04**：檢視並更新 `source/dev/dev/builder.py`，確保 `Builder.build_package` 產物輸出路徑完全對齊 `module.build://`（即 `.build/`）(FR-03)
- [ ] **TASK-05**：檢視並更新 `source/dev/dev/testing/sandbox.py`，確保沙盒環境套件覆蓋對齊 `module.build://` (FR-04)
- [ ] **TASK-06**：更新最高工程規範 `docs/_project/STANDARDS.md` 空間協議表，政策修訂為 `🚫 忽略`，實體路徑改為 `yscb://.build/` (FR-05)
- [ ] **TASK-07**：編寫單元測試套件 `source/core/tests/test_build_git_decoupling.py` (FT-01~FT-05, ET-01, PT-01)
- [ ] **TASK-08**：Dogfooding 閉環驗證與全生態系回歸跑測 (RT-01, NFR-03)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性鎖定 8 步任務拓撲與 .build/ 純淨解耦架構**：
  - 嚴格落實零過渡代碼原則，不引入任何舊 `build/` 相容分支，所有工具鏈統一面向 `.build/` 空間協議。
