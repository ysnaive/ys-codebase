# 測試計畫說明書 (Test Plan)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：`Passed` (全量自動化與 UX 驗證 100% 通過)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試案例清單 (Test Cases)

| 測試編號 | 測試類別 | 測試情境描述 | 預期結果 | 對應需求 |
| :--- | :---: | :--- | :--- | :--- |
| **FT-01** | 功能測試 | 搜集階段自動注入 `__provider__` | Dict 與 List[Dict] 項目均自動包含 `"__provider__": "donor_name"` | FR-01 |
| **FT-02** | 功能測試 | 顯式宣告之 `__provider__` 不覆蓋 | 若 donor 已顯式指定 `__provider__`，引擎予以保留 | FR-01 |
| **FT-03** | 功能測試 | 依賴拓撲順序合併 | 按照已安裝模組之 Topological Order 依序合併配置項 | FR-02 |
| **FT-04** | 功能測試 | `core.contributes.get()` SDK 查詢 | 支援目標模組全字典查詢、特定 key 查詢與自愈快取重聚 | FR-03 |
| **FT-05** | 功能測試 | `core.contributes.get_for_current_module()` 查詢 | 自動定位當前 active module 上下文並返回 Contributes | FR-03 |
| **FT-06** | 功能測試 | JIT 熱補齊 `-y <path>` 流程 | 自動寫回 `config.project.json`、記憶體熱刷新並無縫返回實體路徑 | FR-04, FR-07 |
| **FT-07** | 功能測試 | JIT `--help` 協議清冊展開 | 展開目標協議綁定資訊並即時列出全系統可用 URI 協議清冊 | FR-05 |
| **FT-08** | 功能測試 | 連鎖未定義協議遞迴補齊 | 複合協議（如 `project://plans`）自動先遞迴補齊底層 `project://` | FR-06 |
| **ET-01** | 邊界測試 | 自引用協議死鎖防護 | 檢測到循環引用時立即拋出異常，不發生無窮遞迴 | EC-01 |
| **ET-02** | 邊界測試 | JIT 輸入 `-n` 拒絕補齊 | 輸出引導提示並以 exit code 1 優雅退出 | EC-02 |
| **ET-03** | 邊界測試 | 非 TTY / `interactive=False` 防護 | 拋出結構化 `UndefinedURIError`，不阻塞卡死 | FR-08 |
| **ET-04** | 邊界測試 | donor 模組 Manifest 損毀容錯 | 記錄警告並跳過該 donor，微內核全量聚合不中斷 | EC-04 |
| **RT-01** | 回歸測試 | 全模組回歸測試 | `python yscb.py dev test --all` 100% Passed (含 core, dev, agents-workflow) | 全需求 |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 成功驗證 Dict 與 List[Dict] 項目自動注入 `"__provider__": "donor"` | 2026-08-26 01:35:28 |
| **FT-02** | `Passed` | 成功驗證顯式宣告之 `__provider__` 予以保留不被覆蓋 | 2026-08-26 01:35:28 |
| **FT-03** | `Passed` | 成功驗證已安裝模組依拓撲順序有序合併 | 2026-08-26 01:35:28 |
| **FT-04** | `Passed` | 成功驗證 `core.contributes.get()` 支援全字典與特定 key 查詢 | 2026-08-26 01:35:28 |
| **FT-05** | `Passed` | 成功驗證 `get_for_current_module()` 在 module_scope 下正確定位 | 2026-08-26 01:35:28 |
| **FT-06** | `Passed` | 成功驗證 JIT `-y <path>` 自動寫回 `config.project.json` 並熱重載 | 2026-08-26 01:35:28 |
| **FT-07** | `Passed` | 成功驗證 `list_registered_schemes_summary()` 與 `uri list` 列出 module.mirror 與 module.release 全系統協議清冊 | 2026-08-26 01:44:13 |
| **FT-08** | `Passed` | 成功驗證未定義 `project://` 在非互動模式拋出 `UndefinedURIError` | 2026-08-26 01:35:28 |
| **ET-01** | `Passed` | 成功驗證自引用循環協議觸發 `CyclicURIDependencyError` 阻斷死鎖 | 2026-08-26 01:35:28 |
| **ET-02** | `Passed` | 成功驗證 `-n` 取消流程以 exit code 1 優雅退出 | 2026-08-26 01:35:28 |
| **ET-03** | `Passed` | 成功驗證非 TTY / 靜態環境拋出結構化 `UndefinedURIError` | 2026-08-26 01:35:28 |
| **ET-04** | `Passed` | 成功驗證 donor Manifest 格式錯誤時安全跳過不中斷聚合 | 2026-08-26 01:35:28 |
| **RT-01** | `Passed` | 協議高度對稱化後全系統回歸測試 97/97 案例 100% Passed (14.170s) | 2026-08-26 01:44:32 |

---

## 3. 手動與 UX 驗證項目 (Manual & UX Verification)

| 驗證編號 | 驗證情境 | 驗收標準 | 驗收狀態 |
| :--- | :--- | :--- | :---: |
| **UX-01** | 終端 JIT 提示選單格式 | `[module]` 前綴清晰，`yscb://` 基準明確，選項清晰易讀 | `Pending` |
| **UX-02** | `--help` 全系統協議清冊 | 輸出格式化表格對齊，清晰展示協議 Token 與當前解析路徑 | `Pending` |
