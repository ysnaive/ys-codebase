# 需求規格說明書 (Requirements Specification)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Dev 模組測試案例整併與檔案收斂** | 整併零散之 `test_tester_sync.py` 與 `test_tester_throttle.py` 至 `test_tester.py`；消除重複之格式化與 mock 測試，維持單一組件測試檔案高內聚。 | P0 | [P00:DR-02] |
| **FR-02** | **Core 模組同質測試收斂與冗餘清理** | 整併 `test_cli_help.py` 與 `test_cli_guild.py` 為統一之 CLI 路由測試；收斂 `test_pip_manager_sdk.py` 之細碎解析測試；整併 `test_contributes_jit.py` 與 `test_contributes.py` 之重複 JIT mock。 | P0 | [P00:DR-02] |
| **FR-03** | **高負重多步沙盒測試遷移至 WORKFLOW 分類** | 將反覆建立/銷毀實體沙盒、涉及多進程子命令或高磁碟 I/O 之耗時測試案例（耗時 $\ge 0.5\text{s}$），顯式標註 `@require(Requirement.WORKFLOW)`，自日常預設測試集合中移出。 | P0 | [P00:DR-02] |
| **FR-04** | **100% 契約防護與零測試覆蓋丟失** | 被合併或精簡之案例必須完整保留核心斷言邏輯（正向、負向、異常拋出），確保重構後全系統能力契約 0 降級、0 功能遺失。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 跨分類跑測相容性 | 執行 `dev test <mod> --workflow` 或 `--all-types` 時，所有被遷移至 WORKFLOW 的重型測試必須能被正常收集並 100% 通過。 |
| **EC-02** | 測試檔整併後之動態收集 | 刪除或整合測試檔案後，`TestDiscovery` 動態收集與 Auto-Contract 動態合成 100% 正常運作，無殘留路徑或匯入錯誤。 |
| **EC-03** | 測試環境隔離防護 | 合併同質測試案例時，嚴格維護 `YSCBTestCase` 之環境隔離，禁止案例間變數互相污染。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 日常預設測試（LOGIC + ENV）跑測時間顯著下降：`dev` 模組預設測試執行時間降低 30% 以上（目標 $\le 4.5\text{s}$）。 |
| **NFR-02** | 測試質量 | `core` 與 `dev` 在全量模式下（`--all-types`）自動化測試 100% 通過（0 Failure, 0 Error）。 |
| **NFR-03** | 程式碼維護性 | 測試檔案總數減少，測試方法內聚度提升，消除重複冗長的 Mock 設置樣板代碼。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `Requirement.WORKFLOW` 是 YSCB 測試框架正式支援的 4 大分類之一，日常 `dev test <mod>` 預設僅執行 `LOGIC | ENV`，唯有附加 `--workflow` 或 `--all-types` 時才會納入執行，非常適合收容端到端沙盒測試。
- **`[!CAUTION]`** 在合併測試檔案（如刪除舊測試檔）時，務必同步更新相關模組的測試指針與文件引用，避免產生無效鏈接。
