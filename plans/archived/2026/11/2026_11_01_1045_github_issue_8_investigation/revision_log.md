# 修訂紀錄書 (Revision Log)

> 功能名稱：GitHub Issue #8 四大跨模組缺陷與架構完善修復 (server / knowledge-db / agents-workflow)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1045_github_issue_8_investigation  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 專案入口 `README.md`、`dev` 隨包手冊與技能文檔對齊及專案限定 `@build` 模組跨機自舉支援
- **修訂類別**：Docs
- **涉及檔案**：
  - `README.md`
  - `ys_codebase/source/dev/README.md`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/SKILL.md`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/cli_and_commands.md`
  - `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md`
  - `yscb.py`
  - `ys_codebase/source/core/core/engine.py`
  - `ys_codebase/source/core/core/installer.py`
  - `ys_codebase/source/core/tests/test_distribution_lifecycle.py`
- **修訂摘要**：
  - 全面更新專案入口 `README.md`，對齊最新五大模組架構、8 大 AI 平台 `release_target` 投影表、Scheme B 語意 URI、22 個 Skills 清單與常用 CLI 速查表。
  - 更新 `dev` 模組隨包手冊（`ys_codebase/source/dev/README.md`）、`yscb-module-dev` 與 `bump-revision` 技能文檔，補齊 `dev test -q --sync`、`dev release` 雙軌釋出元數據、`dev index-patch` 與 `index.json` 雙軌帳本說明。
  - 新增給下游自建模組之最佳實踐建議：「對於小範圍特化之專案限定模組（In-tree Project-Specific Modules），建議長期維持以 `@build` 版自部署使用，免去版本遞增與 `release/` 釋出維護問題」，並同步於 `yscb.py`、`core/engine.py` 與 `core/installer.py` 補強同三元組 `.build` 版本對本地 `source/<mod>` 之自動打包自舉相容性。
- **驗證結果**：
  - `python yscb.py dev check` 通過，`core` (`214/214, 100.0%`) 與 `dev` (`82/82, 100.0%`) 沙盒測試全數通過並完成 `@build` 熱同步與工作流發布。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_01_1045_github_issue_8_investigation` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

