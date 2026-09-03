# 需求與決策對齊說明書 (Discuss & Decisions)

> 功能名稱：build_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 需求背景與邊界 (Context & Boundaries)

- **背景與動機**：
  - 現行系統中，各模組透過 `dev build` 命令產出之發布版本包與索引檔案存放在 `build/` 目錄中（如 `build/core/1.0.2.build.zip`）。
  - 由於 `build/` 產物 100% 為 `source/` 原始碼檔案之完全映像 (Mirror / Bundle)，且系統 SSOT 始終唯一錨定於 `source/`，若將 `build/` 納入 Git 追蹤，每次開發建置或熱更新均會產生龐大且冗餘之二進位變更，嚴重污染 Git 歷史並導致 Repo 體積膨脹。
  - 開發者指示：「插入新子項目，build 解耦規劃，因 build 產物為 source 來源檔案之完全映像，可以與 sub 02 相同之模式優化為 git 忽略之 .build/」。
- **核心目標**：
  1. 將 `module.build.root://` 與 `module.build://` 語意 URI 協議映射之實體底層目錄自 `yscb://build/` 正式更名為 `yscb://.build/`，與系統既有之 `.modules/`、`.mirror/`、`.cache/`、`.snapshots/` 等內部運行/生成目錄對齊隱藏規範。
  2. 將 `yscb://.build/` 建置產物從 Git 追蹤中徹底解耦，由 `yscb.py` 內建之 `_generate_internal_gitignore` 軟合併注入 `/.build/` 規則，消除發布產物對 Git 歷史的冗餘變更污染。
  3. 更新生態系核心工具鏈（`dev.builder`、`dev.releaser`、`dev.testing.sandbox`、`yscb.py` 等），全面將建置輸出、沙盒載入與模組提取對齊至 `.build/` 目錄。
  4. 同步更新全專案最高工程規範 [docs/_project/STANDARDS.md](file:///workspace/ys-codebase/docs/_project/STANDARDS.md)，將 `module.build.root://` 與 `module.build://` 之路徑映射改為 `yscb://.build/`，且 Git 追蹤政策修訂為 `🚫 忽略`。
- **邊界排除 (Explicitly Excluded)**：
  - **零平滑過渡**：比照 `sub_02` 決策，絕對不加入任何針對舊 `build/` 目錄的探測、搬移、更名或平滑遷移相容邏輯，代碼庫保持純淨，由下游端自行處置舊 `build/`。
  - 不更動 `source/` 源碼目錄的 Git 追蹤政策（`source/` 始終為唯一 SSOT 與 Git 核心追蹤資產）。
  - 不影響 `release/` 目錄（發布發行庫仍維持獨立）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 比照 sub_02 模式推動 build 產物 Git 解耦**：
  - 將建置產物實體目錄從 `build` 正式更名為 `.build`。
  - 核心邏輯直接面向 `.build/`，落實零平滑遷移負擔原則，不探測亦不處理舊 `build/`。

- **[P00:DR-02] 語意空間協議 module.build 全面指向 .build/**：
  - `core.contributes`: 更新 `contributes/core.json` 中 `module.build` 空間協議之預設解析值為 `yscb://.build/{module}/{version}/`。
  - `core.uri`: 更新 `_BOOTSTRAP_FALLBACK_SCHEMES` 中 `module.build` 空間預設值為 `yscb://.build/`。

- **[P00:DR-03] Git 忽略規則軟合併與規範更新**：
  - 在 `yscb.py` 的 `_generate_internal_gitignore` 標記區塊中，注入 `/.build/\n` 規則（確保 `/.modules/` 與 `/.build/` 均受控管）。
  - 修訂 `docs/_project/STANDARDS.md` 第 1 節空間協議表：將 `module.build.root://` 與 `module.build://` 映射至 `yscb://.build/`，Git 政策標記為 `🚫 忽略`。
  - 同步修訂三大空間隔離禁令中提及 `build/` 之說明為 `.build/`。

- **[P00:DR-04] 生態系工具鏈全面對齊 .build/**：
  - `dev.builder`: `Builder.build_package` 產物輸出至 `module.build://` (即 `.build/`)。
  - `dev.releaser`: 發布來源包探測與打包優先對齊 `.build/`。
  - `dev.testing.sandbox`: 繼承與覆蓋本地開發建置產物時，自 `module.build://` (即 `.build/`) 提取。
  - `yscb.py`: `_restore_module_package` 中的 `build_candidates` 優先探測 `yscb_abs/.build/<module>/<version>.zip`。

---

## 3. 開放議題與確認紀錄

- [x] 是否已明確建置產物更名方向？（已確認：全面更名為 `.build/` 並受 Git 忽略）
- [x] 是否需要舊 build 目錄平滑過渡？（已確認：堅決不加，維持代碼庫純淨，比照 sub_02）
- [x] 是否已明確工具鏈與協議更新範圍？（已確認：涵蓋 `core.uri`、`contributes`、`dev` 工具鏈、`yscb.py` 與 `STANDARDS.md`）
