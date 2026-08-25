# 變更摘要 (Walkthrough)

> 功能名稱：第三方真實使用者原生情境測試、問題排查與框架加固 (Native Consumer Testing & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述

本子計畫 `sub_13` 成功解決了原生消費者端到端自舉時發現的關鍵問題，並全面升級為**全系統單檔 Zip 打包標準與 4-Stage Atomic Reload 流水線**：
1. **預設 Provider 遠端化**：宿主 `yscb.py` 之 `DEFAULT_PROVIDER_URL` 剛性設定為官方 GitHub 遠端發布庫。
2. **全系統全面 Zip 單檔標準與明文空間二分法**：全系統明文展開目錄嚴格僅限 `source/<mod>/`（源碼 SSOT）與 `modules/<mod>/`（運行代碼）。`build/`、`release/` 與 `.mirror/` 全面強制採用單檔 `{version}.zip` 存儲，徹底消滅散裝目錄與檔案殘留。
3. **4-Stage Atomic Reload 流水線**：
   - **Stage 1 (自癒拉取)**：檢查 `mirror://`，缺失自動自癒下載補齊。
   - **Stage 2 (解壓物化)**：解壓前剛性清空 `modules/<mod>/`，保證 100% 鏡像 Zip 包。
   - **Stage 3 (組態治理)**：掃描組態模板軟合併至 `config/`，並無條件物理刪除 `modules/` 內模板與 `.yscbignore`。
   - **Stage 4 (依賴注入)**：聚合能力快照並廣播 `on_reload` 事件。
4. **職責解耦與語意協議精確歸屬**：`release.root` 與 `release` 協議自 `core` 剝除，精準歸由 `dev` 模組貢獻治理。全模組黑盒回歸測試 74/74 項 100% Passed。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
|---------|:-------:|------|
| `ys_codebase/source/core/core/engine.py` | Modify | 實作統一同構單檔 Zip 下載 (`act_download`)、4-Stage Atomic Reload 流水線與模板/雜質物理清除 |
| `ys_codebase/source/core/manifest.json` | Modify | 移除 `release.root` 與 `release` 語意協議，落實職責解耦 |
| `ys_codebase/source/dev/manifest.json` | Modify | 接管並貢獻 `release.root` 與 `release` 語意協議至 core |
| `ys_codebase/source/dev/dev/builder.py` | Modify | 升級 `build_module` 輸出單檔 `build.zip`，`package_release` 輸出純淨單檔 `release.zip`，同 X.Y.Z 淘汰舊單檔 |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | 對齊單檔 `.zip` 發布產物檢驗與原子交易回滾刪除 `.zip` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 沙盒對齊單檔 Zip 套件建置與同構解包物化 |
| `yscb.py` | Modify | 預設 Provider 遠端化，實作原生標準庫 Zip 下載與解包自舉 (`_fetch_and_extract_zip`) |
| `ys_codebase/source/core/tests/test_remote_zip_bootstrap.py` | Add | 微內核單檔 Zip 下載、CRC32 校驗、解包與模板剝除單元測試套件 |
| `docs/core/ZIP_PACKAGE_SPEC.md` | Add | Zip 套件規格與同構自舉管線手冊 (維度 3) |
| `docs/dev/RELEASE_PIPELINE.md` | Modify | 更新發布流水線對齊單檔 Zip 打包標準與回滾機制 (維度 3) |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-12]` (全系統全面 Zip 單檔標準) 與 `[DN-13]` (4-Stage Reload 與清空解包) (維度 5) |
| `CHANGELOG.md` | Modify | 登記全域版本變更歷史摘要 (sub_13) |

---

## 3. 測試與品質驗證結果

- **自動化測試**：`python yscb.py dev test --all` 實機執行 **74/74 項單元與整合測試 100% Passed**。
  - `core` 模組：47/47 Passed（Auto-Contract 3/3 + Custom Tests 44/44）
  - `dev` 模組：27/27 Passed（Auto-Contract 3/3 + Custom Tests 24/24）
- **全面 Zip 單檔純淨性驗收**：
  - `build/` 目錄：僅包含 `*.build.zip` 與 `index.json`，零散裝目錄。
  - `release/` 目錄：僅包含純淨 `*.zip` 與 `index.json`，零散裝目錄。
  - `.mirror/` 目錄：僅包含單檔 `*.zip` 快取，Stage 1 自癒拉取運作正常。
- **運行空間純粹性驗收**：`modules/` 運行端目錄純淨無 `config.*.json` 與 `.yscbignore` 殘留。
- **回歸測試耗時**：~7.5s。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的 `docs/` 文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :--- | :--- | :--- |
| `docs/core/ZIP_PACKAGE_SPEC.md` | ✅ 已新建 | 明文空間二分法、全面單檔 Zip 打包標準、4-Stage Reload 流水線與遠端 HTTP 協議 | P03 §4, P05 TASK-07, P06 FT-01~06 |
| `docs/dev/RELEASE_PIPELINE.md` | ✅ 已更新 | 更新發布流水線對齊單檔 Zip 打包、單檔回滾機制與 release 協議歸屬 | P03 §4, P05 TASK-02, P06 FT-02 |
| `docs/core/DESIGN_NOTES.md` | ✅ 已更新 | 登記 `[DN-12]` (全系統全面 Zip 單檔標準) 與 `[DN-13]` (4-Stage Reload 與清空解包) | P05 TASK-01~04, P06 FT-03 |
| `CHANGELOG.md` | ✅ 已更新 | 登記全域高階變更歷史（sub_13 全面 Zip 打包與 4-Stage Reload 流水線） | 全功能 |

---

## 5. 推薦 Commit 訊息

```text
feat(core,dev): implement full zip single-file packaging and 4-stage atomic reload pipeline

- Enforce strict plaintext space dichotomy (only source/ and modules/ are unpacked)
- Standardize single-file {version}.zip for build/, release/, and .mirror/ caches
- Implement 4-stage atomic reload pipeline (Stage 1: self-healing fetch -> Stage 2: clean & extract -> Stage 3: config governance & template purge -> Stage 4: dependency injection)
- Default provider URL set to official GitHub release gateway with standard library stream unzip bootstrap
- Decouple release.root and release URI schemes to dev module contributes
- Deliver 100% 7-dimension documentation across docs/ (ZIP_PACKAGE_SPEC, RELEASE_PIPELINE, DESIGN_NOTES DN-12/13)
- Pass 100% full regression tests (74/74 passed)
```
