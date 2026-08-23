# 需求規格書 (Requirements Specification)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md) / [R01_architecture_migration.md](./R01_architecture_migration.md) / [R02_dogfooding_pipeline_guardrails.md](./R02_dogfooding_pipeline_guardrails.md)  
> 狀態：Confirmed  
> 擴充項目：none (本計畫產出 dogfooding_pipeline_ext)  
> 模板版本：v1.4  

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | SOP 工作流定式工具指引聯動 | 既有 SOP 文件與定式 CLI 命令 | 微調 `Review.md` (引入 `ext list/show` 與 `docs audit`)、`DocumentationStandards.md` (追加工具鏈章節)、`NewPlan.md` (引入 `docs new-topic` 與 `archive`) | 更新後之工作流指南檔案 | P00 期望狀態 1 |
| **FR-02** | `NewPlan.md` Phase 0 剛性伴隨建立 `changelog.md` 規範 | Phase 0 執行步驟定義 | 修改 Phase 0 步驟 1/2，明確規定開立計畫目錄時必須【同時】建立 `P00_semantic_requirements.md` 與 `changelog.md`，並自 Phase 0 第一秒記錄事件 | 修正後之 `NewPlan.md` | P00 痛點 3、期望狀態 1 |
| **FR-03** | `AGENTS.md` 行為準則與特化規範更新 | 專案準則與 CLI 路由器 | 1. 補齊定式作業 CLI 優先清單 (`<verify\|scan\|search\|archive\|docs\|ext>`)<br>2. 於第 4 節寫入 Dogfooding 三層空間與防呆鐵律 | 更新後之 `AGENTS.md` 與 `AGENTS.template.md` | P00 期望狀態 1、期望狀態 2 |
| **FR-04** | 建立 Dogfooding 專案特化擴充 (`dogfooding_pipeline_ext.md`) | R02 調研結論與 Stage 1~4 流水線 | 建立 `extensions/dogfooding_pipeline_ext.md`，定義源碼修改 ➔ 打包構建 ➔ 回歸測試 ➔ 自引用更新之全生命週期 Checklist | 新建之 `dogfooding_pipeline_ext.md` | P00 期望狀態 2 |
| **FR-05** | `verify_plan.py` 定式驗證工具加固 | Dev Plan 目錄檔案清單 | 移除 `changelog.md` 的略過邏輯，檢查其是否存在並校驗標頭格式，若缺失則報錯阻斷 | 加固後之 `verify_plan.py` | P00 期望狀態 3 |
| **FR-06** | Dogfooding 標準流水線構建、回歸與自引用同步 | 源碼修改完成之工具庫 | 1. 執行 `installer build --all`<br>2. 執行 `python test/run_regression.py`<br>3. 執行 `installer install --all --force` 與 `--ide-antigravity`<br>4. 驗證全域知識庫與 CLI | 100% 通過之回歸日誌與同步之自引用環境 | P00 期望狀態 4 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | 零依賴性 | 腳本與工具鏈修改 100% 基於 Python 3.8+ 標準庫，嚴禁引入任何第三方套件 | 靜態代碼檢查與乾淨環境測試 |
| **NFR-02** | 向後相容與無損軟合併 | `AGENTS.md` 軟合併更新不可破壞專案特化規則（第 4 節） | 執行 `test_23_agents_md_soft_merge_three_states` 單元測試 |
| **NFR-03** | 測試覆蓋率 | 全量 23 項單元測試與下游真實專案沙盒 E2E 回歸測試維持 100% 通過 | 執行 `python test/run_regression.py` |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | Dev Plan 目錄遺漏 `changelog.md` | `verify_plan.py` 掃描時立即精確報錯：`[ERROR] 缺少必備計畫變更日誌: changelog.md`，阻斷驗收通過 | FR-05 |
| **EC-02** | Agent 試圖直接編輯 `modules/` 已安裝產物 | 規範與 Extension 提示嚴格攔截，要求 Agent 一律將編輯目標重定向至 `ys_codebase/source/<module>/` | FR-03, FR-04 |
| **EC-03** | IDE 指令生成器重複執行 | `--ide-antigravity` 在生成前自動清理舊指令並更新 `config.local.json`，防止指令殘留或堆疊 | FR-06 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

> 執行 `python yscb_cli.py agents-workflow ext list` 盤點 `sop_ext://` 下所有可用擴充，逐項評估本計畫之適用性：

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `dogfooding_pipeline_ext` | `always` | 🎯 **本計畫產出目標** | 本計畫即為建立並落地此 Extension，將在實作階段產出並於 Phase 7 驗收。 |

> **標頭同步**：本計畫產出為 `dogfooding_pipeline_ext` 本體，頂部標頭宣告 `> 擴充項目：none (本計畫產出 dogfooding_pipeline_ext)`。

---

## 外部研究與調研參照

| 主題 | 摘要 | 來源 | 可信度 |
| :--- | :--- | :--- | :---: |
| **架構轉型與地毯式掃描** | 完備性驗證 100% Passed，收斂 4 份 SOP 文件微調與 `verify_plan.py` 加固 | [R01_architecture_migration.md](./R01_architecture_migration.md) | 高 |
| **Dogfooding 流水線規範** | 三層空間邊界與四步標準閉環流水線（源碼 ➔ build ➔ regression ➔ install） | [R02_dogfooding_pipeline_guardrails.md](./R02_dogfooding_pipeline_guardrails.md) | 高 |

---

## Decision Records

### [REQ:DR-01] 確立 Dogfooding 雙層防禦體系
- **議題**：如何在自引用代碼庫中防止 Agent 編輯已安裝產物並保證四步標準流水線執行？
- **結論**：採用「`AGENTS.md` 專案特化規範 (靜態公理) + `extensions/dogfooding_pipeline_ext.md` (動態 Checkpoint)」雙層防禦。
- **理由**：靜態公理在 Session 啟動時建立心智模型，動態 Extension 在 Phase 1~7 各關卡剛性攔截。

### [REQ:DR-02] 確立 `changelog.md` 伴隨 Phase 0 剛性初始化與 `verify_plan.py` 加固
- **議題**：為何 `changelog.md` 容易被 Agent 遺忘，如何從規範與工具雙向解決？
- **結論**：修改 `NewPlan.md` Phase 0 步驟 1/2 強制伴隨初始化；加固 `verify_plan.py` 納入存在性檢查。
- **理由**：徹底消除時序滯後與工具檢查盲區，保證全生命週期決策 100% 留痕。
