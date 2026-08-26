# YS-Codebase 模組開發專案特化工程規範 (YS-Codebase Module Engineering Standards)

本文件定義針對 **YS-Codebase 工具庫體系模組作者與 Agent** 在進行模組（如 `core`、`dev`、`agents-workflow` 或第三方擴充模組）之開發、測試、構建與交付時，**必須強制遵守**的專案特化工程規範與防呆防護紀律。

---

## 🚨 1. Agent 發布與安裝行為剛性防呆鐵律 (Zero Unsolicited Release & Install)

- **嚴禁 Agent 主動發布與覆蓋宿主安裝**：
  在開發者未明確下達發布/安裝指示（如 Prompt 顯式包含「發布」、「安裝」、「同步」、「release」、「install」等明確指令）的前提下，**Agent 絕對禁止主動執行 `python yscb.py dev release` 正式打包，以及對當前本機宿主環境進行 `python yscb.py install` 或覆蓋安裝**！
- **沙盒測試為唯一允許驗證手段**：
  Agent 在開發過程中的所有代碼與行為驗證，**唯一合法且允許的手段為 `python yscb.py dev test <module>` 於隔離虛擬沙盒中執行測試**。

---

## 🏛️ 2. Dogfooding 自引用三層空間邊界 (The 3-Tier Space Matrix)

專案呈現「自引用 (Dogfooding)」狀態，所有模組開發必須嚴格遵循三層空間權限矩陣：

1. **空間 ① 源碼開發空間 (`source/<module>/`)**：【唯一源碼來源 (SSOT)】
   - 包含所有模組之原始碼、腳本、SOP 工作流與資產檔案。
   - 所有代碼修改 **100% 必須在此空間進行**。
2. **空間 ② 測試驗證空間 (`cache://dev/sandbox/`)**：【品質守門閘門】
   - 所有自動化測試皆在獨立建立的虛擬沙盒中執行（`dev test`）。
   - 測試環境完全隔離，嚴禁測試代碼外溢污染父環境或根目錄。
3. **空間 ③ 自引用運行消費空間 (`modules/<module>/` 與 `.mirror/`)**：【部署運行產物】
   - 專案根目錄下的 `modules/` 與 `.mirror/` 視為編譯/安裝產物，**嚴禁手動直接修改**。
   - 必須透過標準流水線由 CLI 依賴管理工具自動同步物化。

---

## 🔄 3. 標準四步開發閉環流水線 (The Canonical 4-Stage Pipeline)

進行模組開發或功能修訂時，標準閉環步驟如下：

```text
[Step 1: Source]      編輯 source/<module>/... (唯一 SSOT)
       │
       ▼
[Step 2: Check]       python yscb.py dev check <module> (靜態 AST 語法與 Manifest 稽核)
       │
       ▼
[Step 3: Test]        python yscb.py dev test <module> (沙盒全自動構建並跑測，100% Passed)
       │
       ▼ (需經開發者指示)
[Step 4: Sync/Deploy] 本地開發安裝: python yscb.py install <module>@build --force
                      正式發布安裝: python yscb.py dev release <module> --force ➔ python yscb.py install <module> --force
```

---

## 🧪 4. 全保真虛擬沙盒測試與除錯規範 (Sandbox Testing & Diagnostics)

1. **沙盒空間約束**：
   - 虛擬沙盒由 `SandboxProvisioner` 動態生成於 `cache://dev/sandbox/sandbox_{timestamp}/`。
   - 測試執行完畢後若全部通過，系統會自動清理沙盒；嚴禁在專案根目錄殘留沙盒目錄。
2. **失敗現場自動保留機制**：
   - 若測試發生例外或斷言失敗，測試框架會**自動保留現場沙盒目錄**，並於控制台印出絕對路徑，以利開發者手動檢驗與復現除錯。
   - 若需在測試通過時仍保留沙盒進行人工互動驗證，可附加 `--keep-sandbox` 參數。
3. **常用測試加速與除錯命令**：
   - **跳過重複建置 (快速單元跑測)**：`python yscb.py dev test <module> --no-build`
   - **指定測試案例/正則篩選**：`python yscb.py dev test <module> -k <pattern>`
   - **僅執行通用契約測試**：`python yscb.py dev test <module> --contract-only`
   - **指定測試維度類型**：`python yscb.py dev test <module> --type=<logic|host_cli|network>`
4. **模組測試自治 Hook**：
   - 若模組測試需要客製化環境準備或清理，可在 `source/<module>/scripts/hook.dev.py` 中實作 `on_test_setup(sandbox_root)` 與 `on_test_teardown(sandbox_root)`。

---

## 📦 5. 模組結構合規與語意 URI 規範 (Compliance & VFS Governance)

1. **靜態合規守門 (`dev check`)**：
   - 提交與交付前，必須確保 `python yscb.py dev check <module>` 通過。
   - 驗證項目包含：`manifest.json` 必填欄位 (`name`, `version`, `entry`)、進入點存在性、以及所有 `.py` 檔案之 Python AST 語法無錯誤。
2. **語意 URI 引用原則**：
   - 模組內部檔案存取**嚴禁使用硬編碼之宿主相對路徑**，必須統一使用語意空間協議：
     - 持久化儲存空間：`storage://<module>/...`
     - 暫存快取空間：`cache://<module>/...`
     - 專案組態空間：`config://<module>/...`
     - 模組源碼空間：`module.source://<module>/...`
     - 本地建置產物空間：`module.build://<module>/...`
     - 發布來源空間：`module.release://<module>/...`
