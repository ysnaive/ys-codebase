# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：2026_10_14_1554_downstream_onboarding_and_ux_guidance  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書與文檔變更矩陣中有完整對應介面
- [x] **邊界防護**：EC-01 ~ EC-04 均具備具體容錯與向後相容處理策略
- [x] **依賴純淨**：100% Python 標準庫實現，純 ASCII 終端標籤符合 NFR-01 / NFR-02 約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **專案總綱** | `README.md`, `docs/README.md` | Modify | 補齊 5 大模組全景（納入 `server`）、`yscb.py init` 標準起手流程、修正 `knowledge-db` 與 `agents-workflow` 安裝教學 |
| **模組手冊** | `ys_codebase/source/{core,dev,server,knowledge-db,agents-workflow}/README.md`, `docs/{core,dev}/README.md` | Modify | 為 5 大模組隨包手冊統一補齊 5 分鐘 Quickstart、正確組態設定指南與 Cookbook |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-27]` 宣告式模組 Onboarding 引導與 `!undefined` URI 自癒提示架構決策 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本計畫發布摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：在 `Installer.cmd_install` 中新增 `_print_onboarding_guide` 是否會在單元測試沙盒或 `core` 自癒升級時造成非預期異常或破壞測試斷言？  
> [*] **防護解法**：`_print_onboarding_guide` 全程包裹於 `try...except Exception: pass` 防護網內，僅在 `manifest.json` 存在有效非空 `onboarding` 陣列時輸出純 ASCII `[*] Next Steps for '<module>':` 提示，不改變 `cmd_install` 回傳碼與既有 `[core:install] Successfully installed ...` 核心斷言字串。

> [?] **尖銳問題 2**：擴充 `UndefinedURIError` 預設錯誤訊息是否會影響 `test_uri.py` 的異常斷言？  
> [*] **防護解法**：`UndefinedURIError` 完整保留原有訊息前綴 `Semantic URI '{scheme}://' is undefined (!undefined). Provider: '{provider}', Config Binding: '{binding}'. Please configure it in config://{provider}/config.project.json.`，僅於句尾附加 `Quick fix: <cli_cmd>`，確保所有正则與子字串斷言 100% 相容。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `core.uri` 之 `format_undefined_uri_hint`、`UndefinedURIError` 自癒訊息擴充與 `core/scripts/cli.py:uri_check` 之 `[Quick Fix]` 彙整輸出（FR-05）
- [ ] **TASK-02**：實作 `core.installer:Installer._print_onboarding_guide`、`yscb.py` 之 `_print_init_next_steps`、`dev.checker` 之 `onboarding` 欄位校驗，並為 5 大模組 `manifest.json` 注入 `onboarding` 清單（FR-03, FR-04）
- [ ] **TASK-03**：全面翻新根目錄 `README.md`、`docs/README.md` 與 5 大模組隨包 `ys_codebase/source/*/README.md`（同步對齊 `docs/core/README.md`、`docs/dev/README.md` 與 `docs/core/DESIGN_NOTES.md` `[DN-27]`）（FR-01, FR-02）
- [ ] **TASK-04**：編寫並執行單元測試（`test_uri.py`, `test_remote_zip_bootstrap.py`, `test_checker.py`），執行 Dogfooding 打包安裝與全生態系回歸驗證

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：定稿採用 `manifest.json` 選填欄位 `"onboarding": List[str]` 結合 `format_undefined_uri_hint()` 的雙重引導架構，並同步更新 7 份核心 `README.md`。

