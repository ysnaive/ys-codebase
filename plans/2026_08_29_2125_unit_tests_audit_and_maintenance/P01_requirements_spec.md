# 需求規格說明書 (Requirements Specification)

> 功能名稱：`unit_tests_audit_and_maintenance`  
> 建立日期：2026-08-29  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core` 模組測試套件整併 | 將 `test_semver_v4.py` 合併入 `test_semver.py`，統整 4 段式 SemVer 解析、比較、升級與約束求解測試，並安全移除 `test_semver_v4.py`。 | P0 | [P00:DR-03] |
| **FR-02** | `dev` 模組測試套件純化 | 排查 `test_sandbox.py` 與 `test_tester.py`，整併重複的虛擬沙盒生命週期斷言；精簡 `test_scaffold.py` 與 `test_builder.py` 之重疊邏輯。 | P0 | [P00:DR-03] |
| **FR-03** | `agents-workflow` 測試套件精簡 | 移除已由 `test_compiler.py` 完全覆蓋的孤立 `test_basic.py`；收斂 `test_targets.py` 與 `test_publisher.py` 之重複發布目標驗證邏輯。 | P0 | [P00:DR-03] |
| **FR-04** | `knowledge-db` 測試套件整併 | 將 `test_parsers_deep.py` 邊界案例整併至 `test_parsers.py`，收斂 AST 解析測試；整合 `test_thesaurus.py` 與 `test_tokenizer.py`，提升檢索模組測試凝聚力。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 測試整併過程中遺漏關鍵邊界防線 | 嚴禁在合併或刪除測試檔案時刪除任何獨特之邊界防禦案例（如 SemVer 異常格式、Zip Slip 路徑穿越、動態 Token 語法錯誤等）；重構後測試方法數量雖可精簡，但防禦斷言覆蓋率必須 100% 保持。 |
| **EC-02** | 測試類別命名或繼承偏離規範導致測試未被發現 | 所有測試類別必須明確繼承 `YSCBTestCase`，測試方法嚴格以 `test_` 為前綴，確保 `dev test` 測試發現引擎 (`TestDiscovery`) 100% 識別與收集。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 執行效能與耗時 | 全生態系 4 大模組在獨立沙盒中執行全量單元測試 (`dev test --all`) 總耗時維持於 $\le 15$ 秒內。 |
| **NFR-02** | 品質與合規性 | 重構後 4 大模組所有測試 100% 通過（0 Failure / 0 Error），`dev check` 靜態合規檢查 100% Passed。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：各模組測試套件均運行於 `cache://dev/sandbox/` 隔離虛擬沙盒中。在清理測試時，切勿引入任何對主機本機環境路徑的硬編碼依賴。
