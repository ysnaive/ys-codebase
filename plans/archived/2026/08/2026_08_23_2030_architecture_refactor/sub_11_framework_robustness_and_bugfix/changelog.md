# 計畫變更紀錄 (Changelog)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
> 模板版本：v1.0  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
|---------|------|------|
| 2026-08-25 (Phase 0: 語意需求結案) | `PHASE` | **Phase 0 結案確認**：開發者正式宣告 P00 確認結案（狀態: Confirmed）。裁決採用 Level 1 (Full Track)。 |
| 2026-08-25 (Phase 1: 規格轉譯) | `PHASE` | **產出 P01 需求規格說明書**：完成 FR-01 ~ FR-12 及 EC-01 ~ EC-06 邊界定義，經開發者審查確認（狀態: Confirmed）。 |
| 2026-08-25 (Phase 2: 架構規劃) | `PHASE` | **產出 P02 架構規劃書**：完成模組劃分、SemVer 升級循序圖、雙層快照還原循序圖、受影響檔案矩陣與決策紀錄 [P02:DR-01~07]，經開發者審查確認（狀態: Confirmed）。<br>**前置草擬 P06 測試計畫書**：定義 FT-01~08, ET-01~04, RT-01 全量測試矩陣（狀態: Draft）。 |
| 2026-08-25 (Phase 3: 介面合約) | `PHASE` | **產出 P03 API 規格與介面合約說明書**：定義 `core.semver` 簽名、`core.context` SSOT、`core.uri` CM 作用域、`core.engine` 雙層快照/還原合約、實作依賴拓撲及專案知識庫 1:1 文檔衝擊清單，經開發者審查確認（狀態: Confirmed）。 |
| 2026-08-25 (Phase 4: 實作計畫與測試定稿) | `PHASE` | **產出 P04 實作計畫書**：完成交叉審查清單、三大靈魂拷問、TASK-01~06 任務矩陣與決策紀錄整合，經開發者審查確認（狀態: Confirmed）。<br>**剛性定稿 P06 測試計畫書**：FT-01~08, ET-01~04, RT-01 測試清冊剛性定稿（狀態: Confirmed）。 |
| 2026-08-25 (Phase 5: 編碼實作) | `PHASE` | **全量實作 TASK-01 ~ TASK-06 落地**：<br>1. `core.context` SSOT 與 `core.semver` 2.0.0 運算器新建完成。<br>2. `core.uri` 命名重構 (`_get_host_config`)、嚴格 `resolve` 攔截、`module_scope` / `host_scope` CM 作用域上線。<br>3. 清除 6 大軟相容手段（`yscb.py` 移除向上爬樹、`contributes.py` 移除穿透、`installer.py` 移除後門）。<br>4. `core.engine` 雙層快照還原、Provider 嚴格版本比對、SemVer 依賴求解升級完成。<br>5. `dev.sandbox` 動態版本繼承與 `dev.runner` Contract/Custom 分類統計與失敗清單上線。<br>6. **Hermetic Clean Build 加固**：`dev.builder` 預設強制清空目標版本目錄並使用 `semver` 排序 `index.json`，徹底排除 `tests/` 與 `.yscbignore` 污染。<br>7. 完成 Stage 2 (Build) 與 Stage 4 (Dogfooding Sync) 重新部署。 |
| 2026-08-25 (Phase 6: 測試驗證) | `PHASE` | **全量回歸測試 100% 綠燈**：實機執行 `python yscb.py dev test --all`，全量 59/59 測試全數通過（`core` 35/35, `dev` 24/24），完成 P06 測試清冊與詳細執行日誌回填。UX / 手動驗證 Checkpoint 經開發者審查確認通過（狀態: Passed）。 |
| 2026-08-25 (Phase 7: 結案審查) | `PHASE` | **產出 P07 成果審查說明書與知識庫 1:1 交付**：<br>1. 交付專題手冊 `docs/core/SEMVER.md`、`docs/core/SNAPSHOT_AND_ROLLBACK.md`、`docs/core/API_REFERENCE.md`。<br>2. 更新 `docs/core/README.md`、`docs/core/DESIGN_NOTES.md` (登錄 DN-07, DN-08) 與 `docs/dev/testing_guide.md`。<br>3. 更新全域 `CHANGELOG.md` 與主計畫 `umbrella_overview.md`。子計畫正式標記為結案（狀態: Completed）。 |

---

## 類型標籤說明

| 標籤 | 用途 |
|------|------|
| `PHASE` | Phase 轉換（含 Checkpoint 通過） |
| `DECISION` | Deep Discussion 結論 |
| `DEVIATION` | 偏差處理記錄 |
| `SUB-PLAN` | 子計畫新增 |
| `SUB-DONE` | 子計畫完成 |
| `CONTEXT` | 跨 Conversation 的新增指示或偏好調整 |
| `EXTENSION` | 專案擴充機制的執行記錄 |
