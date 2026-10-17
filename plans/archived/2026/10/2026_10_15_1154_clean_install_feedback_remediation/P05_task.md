# 實作任務清單 (Task Breakdown)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Passed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `yscb.py` 常數與自更新解算函式（FR-01, EC-01）
  - [x] 宣告 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL`
  - [x] 實作 `_resolve_self_update_target_url(custom_url=None)`
  - [x] 更新 `cmd_self_update` 調用
- [x] **TASK-02**：補齊 `agents-workflow/contributes/core.json` 契約並改寫 `scripts/cli.py:release_target`（FR-02, FR-03, EC-02）
  - [x] `core.json` 定義 `--proj` / `--project` 旗標與 `target` 參數
  - [x] `release_target` 同步支援 `--add` / `add`、`--remove` / `remove`
- [x] **TASK-03**：於 `agents-workflow/agents_workflow/publisher.py` 實作軟剝離保護（FR-05, EC-03, EC-04）
  - [x] 實作 `_soft_unmerge_agents_text(existing_text)`
  - [x] 於 `release_all` 之陳舊檔案清理流程接入軟剝離保護
- [x] **TASK-04**：同步校準文檔與 Onboarding 引導至 `contribute.json`（FR-04）
  - [x] `README.md` (3.3 節)
  - [x] `ys_codebase/source/knowledge-db/README.md`
  - [x] `ys_codebase/source/knowledge-db/manifest.json` (`onboarding`)
  - [x] `docs/knowledge-db/contributes_guide.md`
- [x] **TASK-05**：撰寫單元/整合測試與驗證（FT-01 ~ FT-06, RT-01）
  - [x] `tests/test_cli_router.py` (FT-01)
  - [x] `tests/test_targets.py` (FT-02, FT-03)
  - [x] `tests/test_publisher.py` (FT-04, FT-05, FT-06)
  - [x] 模組編譯與安裝 Dogfooding（`agents-workflow@build`, `knowledge-db@build`）
  - [x] 全庫回歸測試（`python yscb.py dev test --all`）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

