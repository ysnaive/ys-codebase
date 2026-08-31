# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與 `ReleasePublisher` 中均有清晰對應介面與方法。
- [x] **邊界防護**：EC-01 (多 Target 共享同檔)、EC-02 (空字串跳過)、EC-03 (路徑異常容錯)、EC-04 (全空跳過) 均有具體防禦處置。
- [x] **依賴純淨**：零新增外部依賴，符合 NFR-01 (0 I/O 短路) 與 NFR-02 (純 LF 換行) 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新 Release Target 與 `agents_md` 欄位說明，移除 `enable_agents_md` 敘述。 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 更新發布章節與組態開關範例。 |
| **規格手冊** | `source/agents-workflow/contributes.format.md` | Modify | 增補 `release_target.agents_md` 官方規格宣告說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當多個啟用中的 Target（如 antigravity 與 codex）同時設定 `agents_md: "project://AGENTS.md"`，停用其中一個 Target 時會發生什麼？**  
> 💡 **防護解法**：`ReleasePublisher` 的 Step 1 (Pruning) 是以「全局所有當前啟用 Targets 的 `current_published_set` 聯集」作為存留基準。當 `antigravity` 被移除但 `codex` 仍啟用時，`project://AGENTS.md` 依然存在於 `current_published_set` 中，因此不會被誤刪；只有在所有設定該檔案的 Target 皆被停用時，該檔案才會被安全清理。

> ❓ **尖銳問題 2：若專案根目錄既有 `AGENTS.md` 中包含使用者自行定義的特殊規範與註解，重構後的軟合併是否會破壞它？**  
> 💡 **防護解法**：`_soft_merge_agents_text` 透過正則精確定位 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 區間，僅替換兩標籤內部的標準文字；若檔案不存在則自動包覆標籤建立。非 YSCB 區塊（例如開頭或結尾的自訂文字）100% 原樣保留。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：更新 `source/agents-workflow/contributes/agents-workflow.json` 與 `contributes.format.md`，為 `antigravity`、`claude`、`codex` 加入 `agents_md` 宣告。
- [ ] **TASK-02**：更新 `source/agents-workflow/agents_workflow/initializer.py`，移除 `enable_agents_md` 預設組態寫入。
- [ ] **TASK-03**：重構 `source/agents-workflow/agents_workflow/publisher.py`：
  - 實作 `_soft_merge_agents_text` 純文字演算法。
  - 將 Target 之 `agents_md` 納入 Stage 0 指紋計算。
  - 改造 Stage 2 / Step 4 軟合併邏輯與雙軌 Manifest 追蹤，移除 `enable_agents_md` 讀取邏輯。
- [ ] **TASK-04**：更新單元測試套件 `source/agents-workflow/tests/test_publisher.py` 與 `test_targets.py`，覆蓋 FT-01~05、ET-01~02。
- [ ] **TASK-DOC**：同步更新 `docs/agents-workflow/` 下的文檔手冊。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立完全由 `release_target[].agents_md` 驅動軟合併與雙軌 Manifest 追蹤，徹底淘汰全域 `enable_agents_md` 組態。
