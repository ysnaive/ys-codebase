# 實作任務清單 (Task Breakdown)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `source/core/core/validator.py`（輕量型別 DSL 解析、通配比對、遞迴結構、Levenshtein 拼寫建議、Meta-Check）。
- [x] **TASK-02**：實作 `source/core/core/commands/contributes_cmd.py` 與 `source/core/contributes/core.json` 指令註冊（`contributes list`、`contributes check`）。
- [x] **TASK-03**：重構加固 `source/core/core/contributes.py`（整合 Validator、JIT 快照納入 `_format.json`、排除 `_` 開頭特殊檔、過濾髒資料並導出 Public SDK）。
- [x] **TASK-04**：更新 `source/dev/dev/checker.py`（新增 `ContributesCheckPass`）與 `source/dev/dev/scaffold.py`（生成包含 `_format.json` 與 `_manifest.md` 之骨架）。
- [x] **TASK-05**：5 大模組生態落地（`core`, `server`, `dev`, `agents-workflow`, `knowledge-db` 建立 `_format.json` 與 `_manifest.md`，並清理舊 `phases` 殘留欄位）。
- [x] **TASK-06**：編寫單元測試覆蓋 FT-01 ~ FT-08。
- [x] **TASK-07**：執行全生態系測試回歸 (FT-09) 與文檔決策留痕（`docs/core/DESIGN_NOTES.md` 之 `DN-23` 與 `docs/dev/DESIGN_NOTES.md` 之 `DN-DEV-09`）。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | `Minor` | 原設 `MAX_RECURSION_DEPTH = 10` 在多層巢狀子命令（如 `config.cmd.list.options.filter.mod.args`）超出深度上限。 | 放寬至 `MAX_RECURSION_DEPTH = 20`，既防止循環引用無窮迴圈又滿足深層命令結構校驗。 |
| **TASK-03** | `Medium` | 運行期聚合時若直接剔除未知擴充點，會使測試沙盒動態 JIT 時間戳注入無聲失效。 | 實施 Tolerant Ingress 原則：未知鍵記錄 `ERROR` 供靜態阻斷，但運行期仍保留於快照字典中相容動態擴充。 |
| **TASK-04** | `Minor` | `dev check` 原 `contributes/core.json` 警告被目錄存在性取代導致既有測試失敗。 | 保留對依賴 core 之模組缺少 `contributes/core.json` 發出 WARN 提示，達成 100% 回歸相容。 |
