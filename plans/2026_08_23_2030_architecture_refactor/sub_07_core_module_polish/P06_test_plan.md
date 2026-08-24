# 測試計畫書 (Test Plan)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 測試案例矩陣 (Test Cases Matrix)

| 測試編號 | 測試項目 | 驗證目標 | 執行方式 | 預期結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | `project://` 顯式配置解算 | 驗證 `config/core/config.project.json` 配置 `project_root` 時正確解算 | `test_uri.py` | 成功輸出相應之絕對路徑 | ✅ Passed |
| **FT-02** | `config://` 顯式專案目錄協議 | 驗證 `config.root://` ➔ `yscb://config/` 與 `config://` ➔ `yscb://config/{mod}/` | `test_uri.py` | 路徑解析指向 `config/`（非 `.config/`） | ✅ Passed |
| **FT-03** | 模組預設組態初次自動分發 | 驗證全新安裝模組時自動將預設組態部署至 `yscb://config/{mod}/` | `test_engine.py` | 目標 `config/` 目錄成功建立且內容相符 | ✅ Passed |
| **FT-04** | 模組組態既有增量缺失補齊 | 驗證已存在組態時，自動增量補齊新鍵且原有用戶自訂值 100% 不變 | `test_engine.py` | 缺失鍵成功補齊，舊有自訂值完整保留 | ✅ Passed |
| **FT-05** | 命名空間 Hook 事件廣播調度 | 驗證 `act_broadcast_event` 精準觸發各模組之 `hook.{emit_mod}.py` | `test_engine.py` | 目標 hook 函式成功被調用並傳入 Context | ✅ Passed |
| **FT-06** | 語意 URI 動態佔位符與協議解析 | 驗證 `type: "config"` 協議與佔位符動態 handler 函式解算 | `test_uri.py` | 正確讀取組態並呼叫 handler 完成替換 | ✅ Passed |
| **ET-01** | `project_root` 未配置或未定義 | 驗證未配置 `project_root` 時之零 Fallback 阻斷防護 | `test_uri.py` | 精準拋出 `ValueError`，拒絕猜測 | ✅ Passed |
| **ET-02** | 接收端 Hook 函式執行過程崩潰 | 驗證 Hook 拋出未捕獲例外時之隔離防護 | `test_engine.py` | 捕獲 Exception 記錄 Warning，不中斷廣播 | ✅ Passed |
| **ET-03** | 缺失 Hook 檔案或未定義目標 event | 驗證模組無對應 hook 時之靜默略過 | `test_engine.py` | 正常略過，Exit Code 0，無任何異常拋出 | ✅ Passed |
| **ET-04** | 動態佔位符 Handler 不存在或無法載入 | 驗證 handler 錯誤時之防禦報錯 | `test_uri.py` | 拋出明確之 `ImportError` / `AttributeError` | ✅ Passed |
| **PT-01** | 動態解析與全模組 Hook 廣播效能 | 驗證 URI 動態解算與事件廣播效能 | 計時斷言 | 單次解算與廣播開銷 $\le 5\text{ms}$ | ✅ Passed |
| **RT-01** | 全量回歸測試守門 | 驗證 Core 18 + Dev 13 標準測試無 Regression | `dev test --all` | 31/31 測試全數 Passed (0.358s) | ✅ Passed |

---

## 2. 雙階段驗證流程與檢核關卡 (Two-Stage Verification & Checkpoints)

### 2.1 雙階段驗證時序 (Two-Stage Verification Workflow)

- [x] **Stage 0（建置與安裝部署物化 - 前置守門）**：
  1. 原始碼修改完成後，執行 `python yscb.py dev build --all --clean`；
  2. 部署至 `modules/` 與 `.mirror/` 運行端，保證運行環境與源碼一致。
- [x] **Stage 1（隔離沙盒前置試跑）**：
  1. 將專案結構複製至 `./sandbox/` 獨立驗證（31/31 Passed）；
  2. 觀察全套流程無誤後，正式刪除 `./sandbox/` 臨時目錄。
- [x] **Stage 2（正式環境全量自動化驗收）**：
  1. 於專案環境執行 `python yscb.py dev test --all --verbose`；
  2. 驗證全量 Auto-Contract (6/6) 與持久化測試 (25/25) **100% 通過 (31/31 Passed, 0.358s)**。
- [x] **開發者 UX / 手動測試確認**：開發者於控制台實機執行 `python yscb.py dev test --all --verbose` 驗證通過 (Status: PASSED 100% Ready)，正式結案。
