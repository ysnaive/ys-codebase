### 🏛️ 模組開發與 Dogfooding 自引用空間閉環鐵律 (Module Dev & Dogfooding Axiom)

本模組提供本地擴充模組開發與測試設施。凡安裝 `dev` 模組之專案，Agent 進行生態系模組開發時**必須強制遵守**以下三大空間隔離與四步標準閉環流水線：

#### 1. 三層空間權限矩陣
- **空間 ① 源碼開發空間 (`source/<module>/`)**：【唯一源碼來源 (SSOT)】所有代碼、腳本、工作流修改 **100% 必須在此空間進行**。
- **空間 ② 測試驗證空間 (`cache://dev/sandbox/`)**：【品質守門閘門】所有自動化測試在獨立隔離沙盒中執行（`python __${yscb.host://yscb.py}__ dev test <module>` 或 `python __${yscb.host://yscb.py}__ dev test --all`），未 100% 通過前嚴禁放行更新自引用產物。
- **空間 ③ 自引用運行消費空間 (`modules/<module>/` 與 `.mirror/`)**：【部署運行產物】視為編譯產物，**嚴禁手動直接修改**，一律由 CLI 同步物化。

#### 2. 標準四步開發閉環流水線 (The Canonical 4-Stage Pipeline)
1. `Step 1 (Source)`：編輯 `source/<module>/...` (唯一 SSOT)。
2. `Step 2 (Build/Check)`：`python __${yscb.host://yscb.py}__ dev check <module>` 靜態稽核，或 `python __${yscb.host://yscb.py}__ dev build <module>` 產出本機開發包。
3. `Step 3 (Regression)`：實機執行 `python __${yscb.host://yscb.py}__ dev test <module>` (或全量 `python __${yscb.host://yscb.py}__ dev test --all`) 100% Passed。
4. `Step 4 (Dogfooding Sync)`：
   - 透過 `@build` 直裝通道部署至 `modules/`：`python __${yscb.host://yscb.py}__ install <module>@build --force` (🚨 嚴禁未獲指示使用 `dev release` 正式發布)。
   - 工作流系統自動完成資產物化與 `AGENTS.md` 軟合併無損。

#### 3. 🚨 發布、安裝與部署免測防呆鐵律 (Release & Install Guardrails)
- **嚴禁未獲授權主動發布**：未獲開發者明確指示前，**絕對禁止**主動執行 `python __${yscb.host://yscb.py}__ dev release` 正式打包，或對當前本機宿主環境進行 `python __${yscb.host://yscb.py}__ install` 覆蓋安裝。
- **部署後免重複測試鐵律 (No Redundant Test Post-Deployment)**：在通過沙盒測試並完成 **`@build` 本地部署 (`python __${yscb.host://yscb.py}__ install <module>@build --force`)** 後，**不需要且嚴禁重複調用 `dev test` 跑測**！安裝部署僅為產物物化與環境同步操作，部署完成後直接結案交付。

#### 4. 📦 語意 URI 與源碼解耦鐵律 (VFS & Decoupling Governance)
- **嚴禁硬編碼相對路徑**：模組內部跨空間檔案存取**嚴禁使用硬編碼之宿主相對路徑**，必須 100% 使用語意空間協議（`storage://`、`cache://`、`config://`、`module.source://`、`module.build://`、`module.release://`）。
