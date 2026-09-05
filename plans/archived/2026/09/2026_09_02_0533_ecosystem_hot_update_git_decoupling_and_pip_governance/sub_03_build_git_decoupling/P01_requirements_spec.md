# 需求規格說明書 (Requirements Specification)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Git 忽略規則注入 | `yscb.py` 內部的 `_generate_internal_gitignore` 標記區塊中必須包含 `/.build/\n` 規則，採用標記區塊軟合併演算法，杜絕破壞專案自訂規則。 | P0 | [P00:DR-03] |
| **FR-02** | 語意空間協議重構 | `source/core/contributes/core.json` 與 `source/core/core/uri.py` 中的 `module.build` 空間協議預設解析路徑自 `yscb://build/{module}/{version}/` 全面更名為 `yscb://.build/{module}/{version}/`，`module.build.root://` 對齊為 `yscb://.build/`。 | P0 | [P00:DR-02] |
| **FR-03** | 建置工具鏈路徑對齊 | `dev.builder.Builder` 之 `build_package` 預設建置輸出目錄全面對齊至 `module.build://`（即 `.build/` 目錄），自動生成各模組之 `<version>.zip` 與 `index.json`。 | P0 | [P00:DR-04] |
| **FR-04** | 宿主與沙盒提取對齊 | `yscb.py` 之 `_restore_module_package` 與 `dev.testing.sandbox` 之沙盒套件疊加提取邏輯，優先探測並載入 `.build/<module>/<version>.zip`。 | P0 | [P00:DR-04] |
| **FR-05** | 最高工程規範更新 | 更新 `docs/_project/STANDARDS.md` 第 1 節空間協議表，`module.build.root://` 與 `module.build://` 映射目標變更為 `yscb://.build/`，Git 追蹤政策正式標記為 `🚫 忽略`。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 全新環境未執行建置時 `.build/` 不存在 | 工具鏈在建置輸出前必須呼叫 `os.makedirs(dest_dir, exist_ok=True)` 自動建立目錄；在查詢或還原時若目錄不存在則安全返回空或降級。 |
| **EC-02** | 歷史殘留之舊 `build/` 目錄存在 | 嚴格遵守零過渡原則，工具鏈完全不探測、不搬移、不備份舊 `build/` 目錄，專注於最新 `.build/` 設計。 |
| **EC-03** | 沙盒隔離執行環境下的建置產物注入 | `dev.testing.sandbox` 透過語意 URI `module.build://` 自動定位宿主 `.build/` 目錄並原子解壓縮覆蓋至沙盒運行端，確保 Dogfooding 沙盒測試無縫運作。 |
| **EC-04** | yscb:// == project:// 拓撲下的軟合併防護 | `_generate_internal_gitignore` 必須維持標記邊界軟合併，不得全量覆寫 `.gitignore`，保護宿主自訂規則與其他模組宣告。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 零開銷 | 協議解析路徑更名為靜態字串替換，執行效能耗時開銷 $0\mu\text{s}$。 |
| **NFR-02** | Git 解耦指標 | 執行 `dev build` 後，`git status` 輸出中不得出現任何 `.build/` 內部檔案與目錄變更。 |
| **NFR-03** | 生態系相容性 | 全生態系全量單元測試（agents-workflow, core, dev, knowledge-db）100% 通過（298/298）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]` 零過渡設計原則**：
  堅決不引入向下相容舊 `build/` 的過渡代碼。舊目錄由專案或下游端自主清理，保持架構純度。
- **`[!NOTE]` `@build` 本地開發版優先提取原則**：
  在 `_restore_module_package` 中，若目標版本為 `@build` 或 `.build/` 產物時間戳較鏡像庫更新，優先以 `.build/` 產物物化並反向更新鏡像庫。
