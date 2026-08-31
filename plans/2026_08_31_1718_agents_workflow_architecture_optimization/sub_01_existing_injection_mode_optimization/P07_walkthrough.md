# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **宣告式 `release_target.agents_md` 規範投影**：將規則檔（如 `project://AGENTS.md`、`project://CLAUDE.md`）之目標路徑下放至各 Release Target 宣告中，不再硬編碼全域輸出。
  - **徹底淘汰全域 `enable_agents_md` 開關**：移除 `config.project.json` 與 `initializer.py` 中之舊設定，由啟用 Target 自行決定是否投影及投影至何處（支援 `agents_md: ""` 略過輸出）。
  - **純文字軟合併與雙軌 Diff 優化**：重構 `ReleasePublisher`，實作 `_soft_merge_agents_text` 確保自定義規則不被破壞，並納入 Stage 0 指紋計算與雙軌 Manifest 追蹤。
  - **Gitignore 防護**：`.gitignore` 自動同步精確忽略非規則資產，確保常駐規範檔案不被誤忽略。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/agents-workflow/contributes/agents-workflow.json` | Modify | 為 `antigravity`、`claude`、`codex` 加入 `agents_md` 宣告 |
| `source/agents-workflow/contributes.format.md` | Modify | 補充 `release_target.agents_md` 規格手冊 |
| `source/agents-workflow/agents_workflow/initializer.py` | Modify | 移除 `enable_agents_md` 預設組態寫入 |
| `source/agents-workflow/agents_workflow/publisher.py` | Modify | 實作純文字軟合併、動態 Target `agents_md` 解算、移除舊開關邏輯 |
| `source/agents-workflow/tests/test_publisher.py` | Modify | 增補 FT-07~09 測試案例並優化組態隔離 |
| `source/agents-workflow/tests/test_targets.py` | Modify | 優化測試環境隔離與組態重設 |
| `config/agents-workflow/config.project.json` | Modify | 移除過時之 `enable_agents_md` 欄位 |
| `docs/agents-workflow/README.md` | Modify | 更新 Release Target 與 `agents_md` 說明 |
| `docs/agents-workflow/user_guide.md` | Modify | 更新發布與組態治理章節 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`agents-workflow` 44/44 (100%) 通過，全生態系 275/275 (100%) 通過。
- **實機 UX / 人工驗證**：實機執行 `python yscb.py agents-workflow release`，短路與軟合併機制運作正常，標記區間完整工整。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | ✅ 已交付 | 更新 `release_target.agents_md` 欄位說明與發布機制 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | ✅ 已交付 | 更新發布與組態治理說明，移除 `enable_agents_md` |
| **規格手冊** | `source/agents-workflow/contributes.format.md` | ✅ 已交付 | 規範 Target `agents_md` 屬性格式 |
| **發布日誌** | `CHANGELOG.md` | ✅ 已交付 | 追加本次架構演進變更紀錄 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow): support declarative release_target agents_md projection and remove global enable_agents_md
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：計畫文件全部合規，已通過驗證。
