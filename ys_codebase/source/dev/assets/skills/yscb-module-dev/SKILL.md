---
name: yscb-module-dev
description: 生態系模組開發與 Dogfooding 閉環指南。當進行 YSCB 生態系模組代碼修改、新增功能、執行沙盒測試 (dev test)、安裝除錯 (@build) 或版本晉升與發布 (bump/release) 時觸發。
---

# 生態系模組開發與 Dogfooding 閉環指南 (Module Dev & Dogfooding Guild)

本手冊定義 YSCB 生態系模組開發的三大空間隔離規範、雙軌流水線與發布防呆守門。

---

## 🏛️ 1. 三層空間隔離矩陣 (3-Tier Space Matrix)

進行生態系模組開發時，必須強制遵守三大空間隔離：

| 空間層級 | 路徑範疇 | 空間定位與操作約束 |
| :--- | :--- | :--- |
| **空間 ① 源碼空間** | `source/<module>/` | 【唯一 SSOT】所有代碼、腳本、模板與工作流修改 **100% 必須在此進行**。 |
| **空間 ② 測試空間** | `cache://dev/sandbox/` | 【品質閘門】自動化測試於隔離沙盒執行（`python yscb.py dev test <module>`），未 100% 通過嚴禁同步。 |
| **空間 ③ 運行空間** | `modules/<module>/` 與 `.mirror/` | 【編譯產物】**嚴禁手動直接修改**，一律由 CLI 同步編譯物化。 |

---

## 🚀 2. 雙軌開發與發布閉環 (Dual-Track Pipeline)

```mermaid
graph TD
    A[編輯 source/<module>/] --> B[dev check <mod>]
    B --> C[dev test <mod>]
    C -->|日常調試 Track A| D[install <mod>@build --force]
    C -->|版本晉升 Track B| E[dev bump-[part] <mod>]
    E --> F[dev test <mod>]
    F --> G[dev release <mod>]
    G --> H[install <mod> --force]
```

### 軌道 A：日常開發調試 (Dogfooding Track)
未獲明確版本晉升指示之日常修改：
$$\text{編輯 } \texttt{source/} \;\longrightarrow\; \texttt{dev check <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{install <mod>@build --force}$$

### 軌道 B：版本晉升交付 (Release Track)
獲開發者明確指示 bump / release / 交付結案：
$$\texttt{dev bump-[part] <mod>} \;\longrightarrow\; \texttt{dev test <mod>} \;\longrightarrow\; \texttt{dev release <mod>} \;\longrightarrow\; \texttt{install <mod> --force}$$

---

## 🛡️ 3. 防呆守門鐵律 (Guardrails)

1. **嚴禁未授權正式發布**：日常熱開發未獲明確指示前，**絕對禁止**自主切入軌道 B 執行 `dev release`，一律維持軌道 A (`@build`)。
2. **部署後免重複測試**：通過沙盒測試並完成 `@build` 或正式安裝後，**嚴禁重複調用 `dev test` 跑測**；物化完成即結案交付。
3. **語意 URI 解耦**：模組內部跨空間存取**嚴禁硬編碼相對路徑**，必須 100% 使用語意協議（`storage://`、`cache://`、`config://`、`module.*://`）。
