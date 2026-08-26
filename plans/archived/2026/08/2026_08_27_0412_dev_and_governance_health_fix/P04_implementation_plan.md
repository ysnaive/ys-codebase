# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 (dev 測試動態解算)、FR-02 (PlanVerifier 標頭別名)、FR-03 (docs/README.md 索引) 在 P02 與 P03 均有具體設計。
- [x] **邊界防護**：EC-01 ~ EC-03 均有對應常數別名比對與防禦處理。
- [x] **依賴純淨**：100% 採用 Python 標準庫，零新增第三方依賴。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/README.md` | Modify | 補齊 `agents-workflow` 模組導覽、生態註冊與即時版本號矩陣 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：未來若 `core` 模組再次升級至 `2.0.0.0` 或微調為 `1.0.2.0`，`dev` 模組的測試會再次破裂嗎？  
> 💡 **防護解法**：不會。因為測試中透過 `uri.read_json("module.source://core/manifest.json")` 即時讀取版本，並依標準 SemVer 規則計算前置 triplet 與 build 檔名，完全消除對特定靜態版本號的寫死依賴。

> ❓ **尖銳問題 2**：若未來新增其他類型的計畫報告（例如架構調研、測試驗證專題手冊），PlanVerifier 會不會誤報缺少標頭？  
> 💡 **防護解法**：`PlanVerifier` 建立了宣告式集合 `VALID_NAME_KEYS`、`VALID_DATE_KEYS`、`VALID_STATUS_KEYS`，已涵蓋通用與調研常用中英文鍵名，並可隨系統擴充集中治理。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：更新 `source/agents-workflow/agents_workflow/plans/verifier.py`，擴充 Header 別名集合並完善標頭檢查邏輯。
- [ ] **TASK-02**：更新 `source/dev/tests/test_builder.py`，改採動態版本解算驗證 `build_module` 與 `index.json`。
- [ ] **TASK-03**：更新 `source/dev/tests/test_release_pipeline.py`，改採動態版本解算驗證 release 打包與 Gate 2/3 守門。
- [ ] **TASK-04**：更新 `source/dev/tests/test_sandbox.py`，改採動態版本解算驗證 `hook.dev.py` 保留性。
- [ ] **TASK-05**：更新專案根目錄 `docs/README.md`，登載 `agents-workflow` 模組與校準全系統版本清冊。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：確定實作順序為 Verifier ➔ dev 測試 ➔ docs 知識庫，確保實作後立即能透過 CLI 工具鏈無縫驗收。
