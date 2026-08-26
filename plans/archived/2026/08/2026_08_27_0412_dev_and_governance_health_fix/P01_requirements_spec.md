# 需求規格說明書 (Requirements Specification)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev` 測試套件版本動態解算 | 重構 `test_builder.py`、`test_release_pipeline.py`、`test_sandbox.py` 中對 `core` 模組建置/發布產物的斷言，透過 `core.uri` 動態自目標 `manifest.json` 讀取版本號組裝預期產物路徑，使 `dev test dev` 30/30 (100% Ready) 全數通過。 | P0 | [P00:DR-01] |
| **FR-02** | `PlanVerifier` 調研標頭語意相容 | 在 `agents_workflow.plans.verifier.PlanVerifier` 中擴充標頭別名支援：認列 `調研主題`、`topic` 作為 `功能名稱` 的合法別名；認列 `調研狀態`、`research_status` 作為 `狀態` 的合法別名，使 `plan verify` 稽核調研報告 (RXX) 正常通過。 | P0 | [P00:DR-02] |
| **FR-03** | `docs/README.md` 全域知識地圖校準 | 更新專案根目錄 `docs/README.md`，在 §2 知識庫地圖與 §3 模組清冊中追加 `agents-workflow` 模組登記與手冊連結，並校準全模組版本號為即時狀態（`core@1.0.1.0`, `dev@1.0.0.1`, `agents-workflow@1.0.1.1`）。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 目標模組 Manifest 不存在或版本缺失 | 測試案例中具備防禦性預設版本解算邏輯，或拋出明確的斷言失敗訊息而非語法例外。 |
| **EC-02** | 調研報告 Header 包含非標準全形冒號或多餘空格 | `PlanVerifier.parse_plan_header` 既有清洗邏輯相容全形/半形冒號，擴充之 key mapping 自動去除前後空白與小寫正規化。 |
| **EC-03** | 舊版僅包含 `> 調研主題：...` 的 RXX 報告 | `PlanVerifier` 成功辨識並標記為通過，不再報 `Header 缺少 [功能名稱]` 與 `Header 缺少 [狀態]` 警告/錯誤。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性與依賴 | 100% 採用 Python 標準庫，零新增第三方依賴，不破壞既有 Public API 簽名與 CLI 指令。 |
| **NFR-02** | 測試覆蓋率 | `dev` 模組測試套件 30/30 100% 通過，全系統回歸測試無衰退。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：在自引用空間中，所有模組源碼修改必須嚴格限制在 `ys_codebase/source/` 空間，嚴禁直接修改 `modules/` 運行端目錄。
- **`[!CAUTION]`**：`dev` 模組的 `test_release_force_override_behavior` 依賴在庫 release 版本進行 Gate 2/3 驗證，測試中應動態讀取當前最高在庫版本進行斷言。
