# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：第三方真實使用者原生情境測試、問題排查與框架加固 (Native Consumer Testing & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01~P03：[P01](./P01_requirements_spec.md), [P02](./P02_architecture_plan.md), [P03](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉審查核對清單 (Cross-Validation Checklist)

- [x] **FR 覆蓋完整性**：P01 中 FR-01 ~ FR-05 於 P03 API 規格書中皆有對應介面與簽名（`dev.builder`, `dev.releaser`, `core.engine`, `core.installer`, `yscb.py`）。
- [x] **EC 錯誤處理對齊**：P01 中 EC-01 ~ EC-04 於 P02/P03 均具備顯式防禦（Zip 完整性校驗、本地同構解包、30s Timeout 逾時防護、遠端 404 精準報錯）。
- [x] **追溯鏈剛性對齊**：`P00 議題` ➔ `P01 (FR/EC)` ➔ `P02/P03 (API/DR)` ➔ `P04 (TASK)` ➔ `P06 (FT/ET/RT)` 實現 100% 雙向追溯。
- [x] **零第三方依賴**：所有新增 Zip 打包、串流下載與解包 100% 基於 Python 3.10+ 標準庫 (`zipfile`, `urllib.request`, `shutil`)。

---

## 2. 靈魂拷問 (Stress Test & Edge Case Scrutiny)

> **架構審查員提問 1**：  
> 「全面改為單檔 `{version}.zip` 之後，`dev test` 執行測試時，是否每次都需要解包？會不會造成測試變慢？」

**架構解析與防護回答**：
- **解包開銷微乎其微**：`core` 與 `dev` 模組 Zip 體積僅數十 KB，使用 Python 內建 `zipfile` 在記憶體/本機磁碟解包耗時小於 5 毫秒。
- **純淨運行空間**：解包至沙盒 `modules/<mod>/` 後，Python 直譯器直接載入明文 `.py` 檔案執行，執行期完全 0 開銷。
- **保證**：測試沙盒獲得完全隔離且與生產環境 100% 一致的乾淨代碼結構。

---

> **架構審查員提問 2**：  
> 「在遠端自舉時，如果網路中斷下載了半截的損壞 Zip 檔案，會不會把半套殘留檔案寫入 `modules/` 導致系統損壞？」

**架構解析與防護回答**：
- **原子暫存與完整性雙重驗證**：
  1. 下載時一律寫入暫存檔 `.tmp.zip`。
  2. 解包前強制調用 `zipfile.is_zipfile()` 與 `zf.testzip()` 進行 CRC32 校驗。
  3. 若校驗失敗，立即拋出例外並刪除 `.tmp.zip`，絕不對 `modules/` 進行任何解包操作。
- **保證**：遠端自舉具備強原子性（All-or-Nothing）。

---

> **架構審查員提問 3**：  
> 「發布同 `X.Y.Z` 的新 Revision（例如發布 `1.0.0.2.zip`）時，舊版 `1.0.0.1.zip` 是如何被清理的？」

**架構解析與防護回答**：
- **單檔原子清理**：`dev.builder.package_release` 掃描 `release/<module>/` 下所有 `*.zip` 檔案，比對 `parse_semver(filename)`。凡前三段 `major.minor.patch` 與目標版本相同但 revision 不同的舊 zip，直接透過 `os.remove` 刪除，並同步自 `index.json` 的 `versions` 清冊中移除。
- **保證**：發布庫中針對相同 `X.Y.Z` 永遠只保留單一最新 Revision 的 Zip 檔案。

---

## 3. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 知識庫文檔路徑 | 知識維度 | 預排更新內容與主題 | 對應 P03/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`docs/core/ZIP_PACKAGE_SPEC.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/ZIP_PACKAGE_SPEC.md) | 維度 3 | **[NEW]** 全面 Zip 單檔打包標準、目錄結構、同構自舉協定與 CRC32 校驗規範。 | P03 §1.2 / FT-04, FT-05 |
| [`docs/dev/RELEASE_PIPELINE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/RELEASE_PIPELINE.md) | 維度 3 | 更新 `dev release` 單檔 `.zip` 打包與同 X.Y.Z 單檔淘汰章節。 | P03 §1.1 / FT-02, FT-03 |
| [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | 維度 5 | 登記 `DN-12`（明文空間嚴格二分法與 Provider 同構 Zip 規範）。 | P02 §4 |

---

## 4. 具體實作任務矩陣 (Task Breakdown Matrix)

| 任務編號 | 目標模組 / 檔案 | 實作細節與核心職責 | 預估行數 |
| :--- | :--- | :--- | :---: |
| **TASK-01** | `source/dev/dev/builder.py` | 1. `package_release`: 打包產出純淨 `release/<mod>/<ver>.zip`，淘汰舊 Revision.zip，更新 `index.json`。<br/>2. `build_module`: 打包產出 `build/<mod>/<ver>.build.zip`（含 tests），更新 `index.json`。<br/>3. 全程不落地散裝目錄。 | ~100 |
| **TASK-02** | `source/dev/dev/releaser.py` | 發布流水線對齊單檔 Zip 產物與發布交易防護（失敗時刪除已產出的 .zip）。 | ~40 |
| **TASK-03** | `source/core/core/engine.py` | 實作 `act_extract_zip_to_module` 與 `act_fetch_module_zip`，解包後自動清理 `config.*.json` 模板。 | ~80 |
| **TASK-04** | `yscb.py` | 1. `DEFAULT_PROVIDER_URL` 設為官方遠端 GitHub URL。<br/>2. 實作 `_fetch_and_extract_zip` 並於 `cmd_init` 完成原生遠端自舉。 | ~60 |
| **TASK-05** | `source/core/core/installer.py` | `cmd_install` / `cmd_update` 接入遠端 Zip 套件下載與解包。 | ~50 |
| **TASK-06** | `source/dev/dev/testing/sandbox.py` | 沙盒建立時自 `build/<mod>/<ver>.build.zip` 解包至 `modules/<mod>/`。 | ~40 |
| **TASK-07** | `source/core/tests/test_remote_zip_bootstrap.py` **[NEW]**<br/>`source/dev/tests/test_builder.py` | 建立單檔 Zip 打包、CRC32 校驗、解包自舉與 config 模板剝除單元測試。 | ~120 |

---

## 5. 決策紀錄清單 (Decision Registry)

- `[P02:DR-01]` 全系統明文空間二分法（僅 `source/` 與 `modules/` 明文，其餘全單檔 `{version}.zip`）。
- `[P02:DR-02]` 本地與遠端 100% 同構自舉與安裝管線（單一 Zip 解包管線）。
- `[P02:DR-03]` 發布端單檔淘汰與 Index 同步機制。
- `[P02:DR-04]` Zip 解包期配置模板自動剝除與純粹化。
