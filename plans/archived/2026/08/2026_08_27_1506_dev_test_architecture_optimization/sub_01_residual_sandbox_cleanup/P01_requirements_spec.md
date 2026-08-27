# 需求規格說明書 (Requirements Specification)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 沙盒緩存滾動修剪 (Rolling Prune) | 當沙盒緩存目錄 (`cache://dev/sandbox/`) 內保留之 `sandbox_*` 目錄達到 4 個或以上（$\ge 4$）時，系統自動依時間戳排序刪除最舊的沙盒，使殘留沙盒數量嚴格限制於最多 3 個。 | P0 | [P00:DR-02] Case 1 |
| **FR-02** | 全模組通過全量清空 (Full-Pass Flush) | 當以 `--all` 旗標執行全模組回歸測試 (`dev test --all`) 且全部測試成功通過 (Exit Code 0) 時，系統自動清空 `cache://dev/sandbox/` 下的所有殘留歷史沙盒。 | P0 | [P00:DR-02] Case 2 |
| **FR-03** | 單模組通過常規清理與隔離 | 單模組跑測 (`dev test <mod>`) 通過時，僅清理當次生成的沙盒目錄，不觸發歷史沙盒全量清空，維持歷史除錯環境直至觸發 FR-01 修剪上限。 | P1 | [P00:DR-02] Case 2 排除項 |
| **FR-04** | 零選項內建生命週期管理 | 清理邏輯完全內建於 `SandboxProvisioner` 與 `Tester._run_test` 生命周期中，不新增額外 CLI 選項，對呼叫端透明。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `cache://dev/sandbox/` 目錄不存在或為空 | `prune_sandboxes()` 與 `cleanup_all_sandboxes()` 靜默返回 0，不拋出任何異常。 |
| **EC-02** | 沙盒目錄被檔案系統/子行程鎖定導致刪除失敗 | 捕獲 `OSError` / `PermissionError` 並輸出警告日誌，不中斷測試主流程。 |
| **EC-03** | 緩存目錄中存在非 `sandbox_*` 命名之檔案或資料夾 | 嚴格過濾僅匹配 `sandbox_*` 前綴之目錄，嚴禁誤刪其他快取資源。 |
| **EC-04** | 測試失敗或附加 `--keep-sandbox` | 不執行當次沙盒刪除，保留現場供排查，但仍受 FR-01 滾動上限（最多 3 個）約束。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 執行效能 | 修剪與清空操作執行耗時 $\le 50\text{ ms}$，不影響測試管線整體流暢度。 |
| **NFR-02** | 向下相容 | 保持既有 CLI 介面簽名與行為 100% 向下相容。 |
| **NFR-03** | 依賴約束 | 僅使用 Python 標準庫 (`os`, `shutil`, `sys`) 與微內核 `core.uri`，不引入任何外部第三方依賴。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 沙盒目錄結構固定位於 `cache://dev/sandbox/sandbox_{timestamp}`。
- **`[!CAUTION]`** 在 Windows 檔案系統中，若子行程未完全退出即嘗試刪除目錄可能拋出 `PermissionError`，需確保使用 `force=True` 或適當錯誤捕獲。
