# 測試計畫 (Test Plan)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Passed  
> 擴充項目：none (本計畫產出 dogfooding_pipeline_ext)  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
|:---|:---|:---|:---|:---|:---:|
| **FT-01** | 功能 | FR-01 | 檢查 `Review.md`、`DocumentationStandards.md`、`NewPlan.md` 是否已完整納入 `ext list/show`、`docs init/audit/new-topic` 與 `archive` 命令指引 | 所有定式指令語法精確無誤且包含範例 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 檢查 `NewPlan.md` Phase 0 步驟 1/2 是否明確規定開立計畫目錄時必須【同時】建立 `P00` 與 `changelog.md` | 流程描述清晰無歧義，徹底消除時序滯後 | ✅ Passed |
| **FT-03** | 功能 | FR-03 | 檢查 `AGENTS.md` 與 `AGENTS.template.md` 之定式作業清單是否包含 `<docs\|ext>`，且第 4 節包含 Dogfooding 三層空間與防呆鐵律 | 規範完整，軟合併定界標記無損 | ✅ Passed |
| **FT-04** | 功能 | FR-04 | 執行 `python yscb_cli.py agents-workflow ext list` 與 `show dogfooding_pipeline_ext` | 成功發現並印出 `dogfooding_pipeline_ext` 內容與 Stage 1~4 Checklist | ✅ Passed |
| **FT-05** | 功能 | FR-05 | 執行 `python yscb_cli.py agents-workflow verify` 驗證當前計畫目錄 | `verify_plan.py` 成功檢驗 `changelog.md` 存在性，100% 合規通過 | ✅ Passed |
| **FT-06** | 功能 | FR-06 | 執行 `python yscb_cli.py installer build --all` ➔ `python yscb_cli.py installer install --all --force` ➔ `python yscb_cli.py agents-workflow --ide-antigravity` | 打包產物更新、自引用模組覆蓋、IDE 工作流 8 個指令重新生成成功 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | 檢查 `verify_plan.py` 對缺少 `changelog.md` 的阻斷邏輯 | 具備精確 `[ERROR] 缺少必備計畫內部變更日誌: changelog.md` 攔截 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 檢查 `dogfooding_pipeline_ext.md` 與 `AGENTS.md` 是否具備嚴格的 `modules/` 唯讀警告與源碼重定向指引 | 邊界定義明確，無混淆漏洞 | ✅ Passed |
| **RT-01** | 回歸 | 全域 | 執行 `python test/run_regression.py` 執行 23 項單元測試與下游真實沙盒 E2E 回歸 | 23 項單元測試與下游沙盒 E2E 回歸 100% 通過 (ALL PASSED, 2.709s) | ✅ Passed |
| **PT-01** | 效能 | NFR-01 | 檢查所有腳本之 imports，確認零第三方套件依賴 (Zero External Dependency) | 100% 使用 Python 3.8+ 標準庫 | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
|:---|:---|:---|:---|:---:|
| **UX-01** | IDE Slash Commands 生成驗證 | 重新生成後，檢查 `.agents/workflows/` 下的指令檔案是否包含最新 JIT 地圖與更新內容 | 開發者確認 IDE 命令正常加載 | ✅ Passed |
| **UX-02** | 知識庫說明文件超連結檢查 | 檢查 `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md` 與 `CONTRIBUTING.md` 中更新的 CLI 指令與路徑 | 連結與指令語法排版清晰可讀 | ✅ Passed |

---

## 3. Bug 修復記錄 (Defect Log)

> 僅在測試過程中發現缺陷時填寫，無則填「無」。

*（無任何缺陷）*

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已實機執行 `python test/run_regression.py` 並全部通過 (ALL PASSED, 23/23 tests)
- [x] **開發者 UX / 手動測試確認**：開發者明確回覆「驗證通過」，允許進入 Phase 7
