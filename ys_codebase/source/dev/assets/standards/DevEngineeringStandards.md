# YS-Codebase 模組開發專案特化工程規範 (Dev Engineering Standards)

本文件定義 Agent 在進行 YS-Codebase 生態系模組（`core`、`dev`、`agents-workflow`、`knowledge-db` 等）之開發、測試、構建與交付時**必須強制遵守**的專案特化工程防呆紀律。

---

## 1. 🚨 發布、安裝與部署免測防呆鐵律 (Release & Install Guardrails)

- **嚴禁主動發布與覆蓋安裝**：未獲開發者明確指示前，**絕對禁止**主動執行 `python __${yscb.host://yscb.py}__ dev release` 正式打包，或對當前本機宿主環境進行 `python __${yscb.host://yscb.py}__ install` 覆蓋安裝。
- **沙盒測試為唯一驗證手段**：代碼與行為驗證唯一合法手段為沙盒測試（`python __${yscb.host://yscb.py}__ dev test <module>`）。
- **部署後免重複測試鐵律 (No Redundant Test Post-Deployment)**：在通過沙盒測試並完成 **`@build` 本地部署 (`install <mod>@build --force`)** 或 **授權之 `release` 正式發布部署 (`dev release` ➔ `install <mod> --force`)** 後，**不需要且嚴禁重複調用 `dev test` 跑測**！安裝部署僅為產物物化與環境同步操作，部署完成後直接結案交付。

---

## 2. 🏛️ Dogfooding 自引用三層空間邊界 (The 3-Tier Space Matrix)

1. **空間 ① 源碼開發空間 (`source/<module>/`)**：【唯一源碼來源 (SSOT)】所有代碼、腳本、工作流修改 **100% 必須在此空間進行**。
2. **空間 ② 測試驗證空間 (`cache://dev/sandbox/`)**：【品質守門閘門】所有自動化測試在獨立隔離沙盒中執行（`dev test`），嚴禁測試代碼外溢污染。
3. **空間 ③ 自引用運行消費空間 (`modules/<module>/` 與 `.mirror/`)**：【部署運行產物】視為編譯產物，**嚴禁手動直接修改**，一律由 CLI 同步物化。

---

## 3. 🔄 標準四步開發閉環流水線 (The Canonical 4-Stage Pipeline)

1. `Step 1 (Source)`：編輯 `source/<module>/...` (唯一 SSOT)。
2. `Step 2 (Check)`：`python __${yscb.host://yscb.py}__ dev check <module>` (靜態 AST 語法與 Manifest 稽核)。
3. `Step 3 (Test)`：`python __${yscb.host://yscb.py}__ dev test <module>` (沙盒全自動構建與測試，100% Passed)。
4. `Step 4 (Sync/Deploy)`：*(需經開發者指示)*
   - 本地開發安裝：`python __${yscb.host://yscb.py}__ install <module>@build --force`
   - 正式發布安裝：`python __${yscb.host://yscb.py}__ dev release <module> --force` ➔ `python __${yscb.host://yscb.py}__ install <module> --force`

---

## 4. 📦 語意 URI 與源碼解耦鐵律 (VFS & Decoupling Governance)

- **嚴禁硬編碼相對路徑**：模組內部跨空間檔案存取**嚴禁使用硬編碼之宿主相對路徑**，必須 100% 使用語意空間協議（`storage://`、`cache://`、`config://`、`module.source://`、`module.build://`、`module.release://`）。
