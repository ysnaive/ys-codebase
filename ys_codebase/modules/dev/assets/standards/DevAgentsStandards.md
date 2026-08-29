### 🏛️ 模組開發與 Dogfooding 閉環鐵律 (Module Dev & Dogfooding)

凡安裝 `dev` 模組，Agent 進行生態系模組開發時**必須強制遵守**三大空間隔離與雙軌流水線：

#### 1. 三層空間隔離矩陣 (3-Tier Space Matrix)
- **空間 ① 源碼空間 (`source/<module>/`)**：【唯一 SSOT】所有代碼、腳本與工作流修改 **100% 必須在此進行**。
- **空間 ② 測試空間 (`cache://dev/sandbox/`)**：【品質閘門】自動化測試於隔離沙盒執行（`dev test <module>`），未 100% 通過嚴禁同步。
- **空間 ③ 運行空間 (`modules/<module>/` 與 `.mirror/`)**：【編譯產物】**嚴禁手動直接修改**，一律由 CLI 同步物化。

#### 2. 雙軌開發與發布閉環 (Dual-Track Pipeline)
- **軌道 A：日常開發調試 (Dogfooding Track)**（未晉升版本之日常修改）：
  $$\text{編輯 } \texttt{source/} \;\longrightarrow\; \texttt{dev check <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{install <mod>@build --force}$$
- **軌道 B：版本晉升交付 (Release Track)**（獲明確指示 bump/release/交付）：
  $$\texttt{dev bump-[part] <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{dev release <mod>} \;\longrightarrow\; \texttt{install <mod> --force}$$

#### 3. 🚨 發布與部署防呆守門 (Guardrails)
- **嚴禁未授權正式發布**：日常熱開發未獲明確指示前，**絕對禁止**自主切入軌道 B 執行 `dev release`，一律維持軌道 A (`@build`)。
- **部署後免重複測試鐵律**：通過沙盒測試並完成 `@build` 或正式安裝後，**嚴禁重複調用 `dev test` 跑測**；物化完成即結案交付。
- **語意 URI 解耦鐵律**：模組內部跨空間存取**嚴禁硬編碼相對路徑**，必須 100% 使用語意協議（`storage://`、`cache://`、`config://`、`module.*://`）。
