# 實作任務清單 (Task Breakdown)

> 功能名稱：跨平台宿主環境專有名詞庫、多平台並發自動嗅探與首輪 Dogfooding 實機驗證 (`sub_02_host_nouns_and_dogfooding`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `core/locale.py` 實作 `detect_active_host_dialect()`、`_get_all_registered_locale_modules()` 與無前綴全域穿透查找（詳見 `P04_implementation_plan_auto.md` §4）。
- [x] **TASK-02**：建立 `agents-workflow/locales/{definition,zh,nouns-antigravity,nouns-claude,nouns-codex}.json` 並於 `contributes/core.json` 註冊 `"locales"`。
- [x] **TASK-03**：擴充 `agents-workflow/agents_workflow/{compiler,publisher}.py` 支援 Stage 2 `` `__%{key}__` `` 專有名詞按 `target_name` 展開與指紋追蹤，並更新 `yscb-cli-guide/SKILL.md`。
- [x] **TASK-04**：建立 `knowledge-db/locales/{definition,zh}.json`，更新 `scripts/cli.py` 與 `knowledge-db-search/SKILL.md`，並完成三模組測試與 `@build` 熱部署驗證。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

