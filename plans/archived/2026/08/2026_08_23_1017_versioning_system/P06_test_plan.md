# 測試計畫 (Test Plan)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Passed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
|:---|:---|:---|:---|:---|:---:|
| **FT-01** | 功能 | FR-01 | 測試 `SemVer` 解析各種合法版本（如 `"1.2.3"`, `"v2.0.0-alpha.1+build.10"`）與富比較運算符（`<`, `<=`, `==`, `!=`, `>=`, `>`）。 | 正常解析各欄位，比較結果 100% 正確。 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 測試 `VersionConstraint` 比對（精確 `==1.0.0`、區間 `>=1.0.0, <2.0.0`、Caret `^1.2.3`、Tilde `~1.2.0`、萬用字元 `*`）。 | 約束匹配邏輯 100% 符合 SemVer 規範。 | ✅ Passed |
| **FT-03** | 功能 | FR-03 | 測試 `python yscb_cli.py version status` 掃描全專案模組。 | 輸出 Markdown 表格，正確識別 source / build / installed 三態版本。 | ✅ Passed |
| **FT-04** | 功能 | FR-04 | 測試 `python yscb_cli.py version check-update` 比對更新。 | 正確比對本機安裝 vs 最新可用版本，列出變更級別與 Migration 需求。 | ✅ Passed |
| **FT-05** | 功能 | FR-05 | 測試 `python yscb_cli.py version bump <module> <major\|minor\|patch>`。 | 依專案適配公理正確遞進 `manifest.json` 版本號（Major 歸零 Minor/Patch，Minor 歸零 Patch）。 | ✅ Passed |
| **FT-06** | 功能 | FR-06 | 測試模組相依性相容防呆（在 `manifest.json` 宣告 `core >= 2.0.0`，嘗試安裝不相容版本）。 | 不相容時阻斷安裝並提示衝突；相容時正常安裝。 | ✅ Passed |
| **FT-07** | 功能 | FR-07 | 測試資產分級覆蓋：自訂 `config.project.json` 欄位在升級後保留，新欄位預設值順利注入；`AGENTS.md` 特化規則無損。 | 自訂配置未被沖刷，新欄位已補齊，特化規範保留。 | ✅ Passed |
| **FT-08** | 功能 | FR-08 | 測試 `MigrationRunner` 鏈式線性增量遷移（以 `@runner.step("1.1.x")` 註冊步階，模擬 `1.0.0 ➔ 1.3.0` 升級）。 | 依序線性執行 `1.1.x ➔ 1.2.x ➔ 1.3.x` 步階，不跳號、不遺漏。 | ✅ Passed |
| **FT-09** | 功能 | FR-09 | 測試五階段升級失敗自動快照回滾（模擬 `_migration.py` 拋出異常）。 | 立即阻斷並從 `.yscb_cache/backup/` 快照 100% 還原舊目錄。 | ✅ Passed |
| **FT-10** | 功能 | FR-10 | 測試 `verify_plan.py` 抽象動態調用 `sop_ext://dogfooding_pipeline_verify.py`。 | 成功觸發特化驗證腳本，完成發布版本與三態一致性稽核。 | ✅ Passed |
| **FT-11** | 功能 | Task-09 | 測試 Installer 自舉升級（`installer self-update`）與起手腳本原子安全替換。 | 成功比對遠端/快取最新腳本版本，並以 `.tmp` 原子安全替換根目錄起手腳本。 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | 測試輸入非法版本字串（如 `"1.a.2"`, `""`, `None`）。 | 拋出明確 `ValueError` / `InvalidVersionError`。 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 測試版本字串帶前綴 `v`（如 `"v2.1.0"`）或前後空格。 | 寬容解析為標準 `SemVer("2.1.0")`。 | ✅ Passed |
| **ET-03** | 邊界 | EC-03 | 測試短格式版本字串（如 `"1.0"`）。 | 寬容補齊為 `SemVer("1.0.0")`。 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 測試相依約束解析未指定版本（如 `dependencies: ["core"]`）。 | 自動視為萬用字元 `*`，保持完全向後相容。 | ✅ Passed |
| **ET-05** | 邊界 | EC-08 | 測試 Plan 宣告了未包含 `_verify.py` 的 Extension。 | `verify_plan.py` 安全略過，不報錯崩潰。 | ✅ Passed |
| **RT-01** | 回歸 | 全域 | 執行全專案既有單元測試 `python test/run_regression.py`。 | 維持 36/36 + E2E 測試 100% Passed。 | ✅ Passed |
| **RT-02** | 回歸 | CLI | 驗證既有 CLI 指令（`installer list/status/self-update`, `agents-workflow verify/scan/ext`）。 | 既有功能無任何破壞性變更。 | ✅ Passed |
| **PT-01** | 效能 | NFR-01 | 執行 10,000 次 SemVer 解析與比較基準測試。 | 總耗時 36.24ms (< 100ms)，無記憶體洩漏。 | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
|:---|:---|:---|:---|:---:|
| **UX-01** | 版本狀態矩陣終端排版 | 執行 `python yscb_cli.py version status` | Markdown 表格對齊清晰，清楚列出 `installer (CLI)` 與各模組版本及 `[SYNCED]` 標籤。 | ✅ Passed |
| **UX-02** | 一鍵檢查更新終端指引 | 執行 `python yscb_cli.py version check-update` | 明確提示可更新模組、變更級別、Migration 警告與 Installer 升級指引。 | ✅ Passed |
| **UX-03** | 依賴衝突錯誤終端可讀性 | 刻意觸發相依不滿足之安裝 | 終端錯誤訊息友好，清晰指出衝突模組與版本缺口。 | ✅ Passed |
| **UX-04** | 安裝器自舉升級互動體驗 | 執行 `python yscb_cli.py installer self-update` | 終端顯示檢查更新、提示當前已為最新或執行安全升級。 | ✅ Passed |

---

## 3. Bug 修復記錄 (Defect Log)

| 缺陷 ID | 發現階段 | 缺陷描述 | 根因分析 | 修復處置 | 驗證結果 |
|:---|:---|:---|:---|:---|:---:|
| **BUG-01** | Phase 5 測試 | `VersionConstraint` 解析 `">= 2.0.0"` 帶空格時因正則分割產生空字串導致報錯 | `re.split(r"[, ]+")` 將運算符與版本號拆散 | 改用逗號分割條件，並使用 `re.match(r"^(\^\|~\|>=...)?\s*(.+)$")` 提取 | ✅ Passed |

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已實機執行 `python test/run_regression.py` 並全部通過（36/36 單元測試 + E2E 下游沙盒 100% Passed）
- [x] **開發者 UX / 手動測試確認**：開發者手動驗證 UX 通過，核准標記 Passed 並推進至 Phase 7


