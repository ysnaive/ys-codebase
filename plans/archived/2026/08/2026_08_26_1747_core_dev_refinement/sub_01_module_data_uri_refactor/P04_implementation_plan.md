# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01~P03：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中有 1:1 對應介面與拓撲階段。
- [x] **邊界防護**：EC-01 (`UndefinedModuleContextError`)、EC-02 (路徑穿越安全防衛)、EC-03 (舊協議向下相容重定向)、EC-04 (`--purge` 容錯)、EC-05 (歷史檔案平滑遷移) 均有完備錯誤處理契約。
- [x] **依賴純淨**：100% 依賴 Python 標準庫，解析延遲約束 $\le 0.05\text{ms}$，符合 NFR-01~03。
- [x] **測試前置**：P06 測試計畫已同步剛性定稿為 `Confirmed`，涵蓋 FT-01~07, ET-01~04, RT-01 與 UX-01~02。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據知識庫抽象維度規範，本子計畫結案時必須交付/更新以下 `docs/` 知識庫文檔：

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `docs/core/URI_SPECIFICATION.md` | Update | 方案 B 全量 Root 化標準協議體系、`@/` 當前模組自省語法與跨模組尋址規範。 |
| **維度 3** | `docs/core/LIFECYCLE_GOVERNANCE.md` | New | 模組資料生命週期治理規範：`storage` (Git)、`cache` (Ignored)、`config` (Tracked)、`remove --purge` 機制。 |
| **維度 4** | `docs/dev/SANDBOX_TESTING.md` | Update | 測試沙盒環境自 `temp://` 遷移至 `cache://sandbox/` 之架構說明。 |
| **維度 7** | `CHANGELOG.md` | Update | 全專案根目錄版本日誌追加本次 URI 重構與資料治理升級摘要。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若外部腳本或舊版設定仍調用了已廢除的 `storage.root://` 或 `module.root://`，系統是否會直接硬崩潰？**  
> 💡 **防護解法**：`core.uri.resolve()` 內建舊協議向下相容轉譯層（Deprecation Redirection）。當檢測到已廢除的 `*.root://` 協議時，自動剥除 `.root` 重定向至新版標準協議，並發出非致命的 `DeprecationWarning`，保證外部工具與自定義腳本平滑過渡。

> ❓ **尖銳問題 2：執行 `remove <mod> --purge` 時，若模組刻意建立指向系統關鍵目錄的軟連結 (Symlink)，是否可能導致越界誤刪？**  
> 💡 **防護解法**：`engine.act_delete` 在執行物理刪除前，強制使用 `os.path.realpath()` 進行實體目錄沙盒邊界校驗，若真實路徑不在目標模組專屬的 `storage/{module}/` 或 `config/{module}/` 範圍內，立即阻斷並報警，杜絕任何符號連結逃逸風險。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (基礎解算引擎)**：重構 `source/core/core/uri.py`（方案 B、`@/` 自省展開、`UndefinedModuleContextError`、廢除 temp/root）與 `source/core/manifest.json`。
- [ ] **TASK-02 (微內核狀態與生命週期)**：重構 `source/core/core/engine.py`（互斥鎖遷移至 cache、消除 hardcoded storage、落實 `--purge`）、`installer.py` 與 `cli.py`。
- [ ] **TASK-03 (開發工具鏈與測試沙盒)**：重構 `source/dev/manifest.json`、`source/dev/dev/testing/sandbox.py`、`case.py` 與 `dev/dev/` 工具鏈（消除 `*.root` 與 `temp`）。
- [ ] **TASK-04 (工作流資產與發布修復)**：修復 `source/agents-workflow/agents_workflow/publisher.py` 中的 `release_manifest.json` 路徑至 `storage://@/`，重構 `compiler.py` 快取路徑與模板協議。
- [ ] **TASK-05 (物理空間清理與歷史遷移)**：物理刪除歷史誤建的 `yscb://storage/core/agents-workflow/` 與 `yscb://.temp/` 目錄。
- [ ] **TASK-06 (測試套件升級與全量驗證)**：更新全模組測試套件斷言，實機執行全量回歸測試 (`python yscb.py dev test --all`) 達成 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿方案 B 與四步閉環實作計畫**：確認 Phase 1~3 規格與依賴拓撲無環無漏，同意剛性定稿 `P04_implementation_plan.md` 與 `P06_test_plan.md`，獲准進入 Phase 5 實作階段。
