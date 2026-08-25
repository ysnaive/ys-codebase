# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01~P03：[P01](./P01_requirements_spec.md), [P02](./P02_architecture_plan.md), [P03](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉審查核對清單 (Cross-Validation Checklist)

- [x] **FR 覆蓋完整性**：P01 中 FR-01 ~ FR-12 於 P03 API 規格書中皆有對應介面與簽名（`core.semver`, `core.context`, `core.uri`, `core.engine`, `core.contributes`, `core.installer`, `dev.sandbox`, `dev.runner`）。
- [x] **EC 錯誤處理對齊**：P01 中 EC-01 ~ EC-06 於 P02/P03 均具備顯式防禦（非標準 URI 拋出 `ValueError`、畸形 SemVer 拋錯、依賴無解拋錯、快照自動建立目錄、Provider 嚴格目錄比對、CM 例外安全）。
- [x] **追溯鏈剛性對齊**：`P00 議題` ➔ `P01 (FR/EC)` ➔ `P02/P03 (API/DR)` ➔ `P04 (TASK)` ➔ `P06 (FT/ET/RT)` 實現 100% 雙向追溯。
- [x] **零第三方依賴**：所有重構 100% 維持純 Python 3.10+ 標準庫實現。

---

## 2. 靈魂拷問 (Stress Test & Edge Case Scrutiny)

> **架構審查員提問 1**：  
> 「在移除 `yscb.py:load_config` 的 `while True` 向上爬目錄樹後，如果使用者在專案深層子目錄執行 CLI 指令，會不會找不到設定檔而報錯？」

**架構解析與防護回答**：
- **物理拓撲錨定**：`yscb.py` 永遠與其所在的 `yscb.config.json` 處於同一個目錄（工具庫根目錄），因此 `load_config` 僅探測同層目錄是 100% 剛性正確的。
- **跨目錄工作區支援**：若使用者在非根目錄工作區執行，外部透過 `YSCB_HOST_DIR` 或呼叫端直接錨定目標 `yscb.py`。
- **沙盒邊界保護**：此變更徹底終結了沙盒內執行時因缺少設定檔而靜默向上逃逸偷取外層宿主設定的致命隱患！

---

> **架構審查員提問 2**：  
> 「`core.semver` 解析器如何處理 prerelease（如 `1.0.0-beta.1` 與 `1.0.0`），會不會誤判正式版比測試版舊？」

**架構解析與防護回答**：
- **標準 2.0.0 優先級規則**：SemVer 2.0.0 規範剛性定義：具有 prerelease 標記之版本優先級低於不帶 prerelease 之正式版（即 `1.0.0-beta.1 < 1.0.0`）。
- **四元組數值比較**：`compare_semver` 在 `major, minor, patch` 數值相等時，若一方無 prerelease 則無 prerelease 者較大；若雙方皆有 prerelease 則以字典序比較 prerelease 標記，保證 100% 遵循 SemVer 2.0.0 規範。

---

> **架構審查員提問 3**：  
> 「快照擴充納入 `config.root://` 後，若還原時模組設定檔被外部進程暫時佔用，如何保證原子性？」

**架構解析與防護回答**：
- **安全覆蓋流程**：`act_restore_snapshot` 先驗證快照完整性，接著採用逐檔寫入暫存檔後原子替換（Atomic Rename/Replace）的方式還原 `config/`，最後調用 `act_reload` 從不可變 `mirror/` 重新物化 `modules/`，杜絕半殘狀態。

---

## 3. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

> 依據 7 大抽象知識維度與使用者指示，預排 Phase 7 需 1:1 同步交付更新之知識庫清單：

| 知識庫文檔路徑 | 知識維度 | 預排更新內容與主題 | 對應 P03/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`docs/core/ARCHITECTURE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/ARCHITECTURE.md) | 維度 1 | 微內核常量自定位物理拓撲圖、`_get_host_config` 設計意圖與零 I/O Fast-Path 保證。 | P03 §1.3 / FT-05 |
| [`docs/core/SEMVER.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/SEMVER.md) | 維度 2 | **[NEW]** SemVer 2.0.0 版本運算器專題手冊（四元組解析、排序與範圍約束規格）。 | P03 §1.1 / FT-01, FT-02 |
| [`docs/core/SNAPSHOT_AND_ROLLBACK.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/SNAPSHOT_AND_ROLLBACK.md) | 維度 3 | **[NEW]** 雙層組態快照與不可變 Mirror 原子還原流程專題手冊。 | P03 §1.4 / FT-04 |
| [`docs/core/API_REFERENCE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/API_REFERENCE.md) | 維度 4 | 登錄 `core.semver`、`core.context` SSOT 與 `core.uri` Context Manager 介面清單。 | P03 §1.1~1.3 / FT-03 |
| [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | 維度 5 | 登記 `DN-07` (OS 原子鎖保護) 與 `DN-08` (剛性拓撲零猜測邊界)。 | [P03:DR-01~07] |
| [`docs/dev/TESTING_FRAMEWORK.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/TESTING_FRAMEWORK.md) | 維度 2 | 更新 Contract/Custom 分離統計與失敗清單排版手冊。 | P03 §1.5 / FT-08 |

---

## 4. 實作任務清單 (Implementation Task Matrix)

| 任務編號 | 實作項目 | 目標檔案 | 對應 FR / EC | 依賴前置 |
| :--- | :--- | :--- | :--- | :---: |
| **TASK-01** | `ExecutionContext` SSOT 與 SemVer 2.0.0 運算器實作 | `source/core/core/context.py`<br/>`source/core/core/semver.py` (NEW) | FR-05, FR-07<br/>EC-02, EC-03 | 無 |
| **TASK-02** | `core.uri` 命名重構、嚴格 resolve 與 Context Manager 實作 | `source/core/core/uri.py` | FR-03, FR-06, FR-07, FR-10<br/>EC-01, EC-06 | TASK-01 |
| **TASK-03** | 剛性拓撲回歸：清除 6 大軟相容手段 | `yscb.py`<br/>`source/core/core/contributes.py`<br/>`source/core/core/installer.py` | FR-01, FR-02, FR-04<br/>EC-01 | TASK-02 |
| **TASK-04** | 雙層快照還原、Provider 嚴格比對與 SemVer 升級整合 | `source/core/core/engine.py`<br/>`source/core/core/installer.py` | FR-05, FR-06, FR-08, FR-09<br/>EC-03, EC-04, EC-05 | TASK-01~03 |
| **TASK-05** | 沙盒動態版本讀取與測試報表精準分類/失敗清單 | `source/dev/dev/testing/sandbox.py`<br/>`source/dev/dev/testing/runner.py` | FR-04, FR-11, FR-12 | TASK-02~04 |
| **TASK-06** | 單元測試套件撰寫與全量 100% 綠燈回歸驗證 | `source/core/tests/test_semver.py` (NEW)<br/>`source/core/tests/test_robustness.py` (NEW) | FT-01~FT-08<br/>ET-01~ET-04<br/>RT-01 | TASK-01~05 |

---

## 5. 決策紀錄整合 (Decision Records Master List)

- `[P00:DR-01]`：回歸 R01~R05 剛性拓撲，全面清除 6 大軟相容手段與跨空間穿透。
- `[P00:DR-02]`：建立純標準庫 SemVer 2.0.0 運算器，終結 `"1.10.0" < "1.9.0"` 字串排序 Bug。
- `[P00:DR-03]`：`_find_host_config` 重命名為 `_get_host_config` 並補齊微內核物理拓撲註解。
- `[P00:DR-04]`：`ExecutionContext` 採方案 B 收斂於 `core.context` 作為唯一 SSOT。
- `[P00:DR-05]`：`act_snapshot` 納入 `config.root://`，達成雙層組態一致性回滾。
- `[P00:DR-06]`：`core.uri` 提供 `module_scope` 與 `host_scope` Context Manager。
- `[P00:DR-07]`：沙盒動態讀取真实 manifest 版本；`dev.runner` 精準計數並獨立輸出失敗清單。

---

## 6. 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：Phase 4 實作計畫定稿、靈魂拷問審查與 P06 測試計畫無誤，指示進入 Phase 5 開始實作
