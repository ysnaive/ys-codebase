# 實作任務清單 (Implementation Task List)

> 功能名稱：超薄宿主單檔實現 (Ultra-Thin Host Bootstrapper)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 任務清單 (按 P04 依賴拓撲排序)

- [x] **1. 常數與組態工具**：實作 `CONFIG_FILENAME`, `CORE_COMMANDS`, `DEFAULT_PROVIDER_URL` 與 `load_config`, `save_config` 工具函式
- [x] **2. 宿主自我更新引擎**：實作 `cmd_self_update`，包含遠端腳本檢索、`ast.parse` 語法校驗、`.bak` 備份與原子替換
- [x] **3. 泛用 CLI 派發器**：實作 `dispatch_module`，包含環境未初始化攔截、目標模組 `scripts/cli.py` 探測、`subprocess.run` 參數透傳與 Exit Code 傳遞
- [x] **4. 原生自舉初始化引擎**：實作 `cmd_init`，包含重複初始化防呆、根目錄與必要目錄結構建立、`yscb.config.json` 初始化寫入與 core 自動自舉觸發
- [x] **5. 4 層階梯式路由進入點**：實作 `main()`，支援 `init`、`self-update`、`CORE_COMMANDS` 7 大指令免前綴智能轉發與泛用模組派發

---

## 偏差紀錄 (Deviation Log)

| 等級 | 對應任務項 | 偏差內容 | 處理方式 |
| :--- | :--- | :--- | :--- |
| 無 | - | 無偏差，100% 依 P03/P04 簽章實作 | - |

---

## 編譯驗證紀錄 (Compilation Checkpoints)

| 時間點 | 驗證範圍 | 指令 | 結果 |
| :--- | :--- | :--- | :---: |
| 2026-08-24 20:02 | `project://yscb.py` | `python -m py_compile yscb.py` | ✅ 通過（0 Error / 0 Warning） |
