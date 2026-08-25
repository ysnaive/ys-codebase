# Fast Track 變更計畫 (Fast Track Plan)

> 功能名稱：處理現有檔案狀況與舊代碼隔離備份 (Quarantine & Legacy Backup)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00：[P00_semantic_requirements.md](../P00_semantic_requirements.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## FT-1：變更說明

### P00 語意需求摘要（引用自 P00）

- **計畫類型**：Refactor / Quarantine
- **核心訴求**：為全新的微內核架構重構建立純淨的源碼與運行端工作空間，防止歷史自引用腳本與舊版業務模組（gents-workflow）干擾新內核的獨立構建。
- **P00 關鍵情境 / 復現步驟摘要**：
  > 「gents-workflow 模組：暫不在本次開發範圍，重構與測試期間移至暫存區隔離，防止干擾。」（P00 排除範疇）
  > 「將 modules/agents-workflow/ 與 source/agents-workflow/ 完整移入暫存隔離目錄（.quarantine/），備份歷史檔案至備份區。」（R05 §3.1）

### 修改動機

現有 codebase 包含歷史巨型起手單檔（yscb_installer.py, yscb_cli.py）以及舊版自引用模組（gents-workflow）。在全新微內核架構（yscb.py 宿主與 source/core 模組）構建前，必須先建立乾淨隔離的現場，避免名稱衝突與自引用干擾，並保留歷史代碼以供後續遷移（sub_08）使用。

### 修改內容

將所有舊版代碼、舊版運行產物、歷史測試與舊知識庫全數移至 .quarantine/ 封存，徹底消除 Agent 認知干擾與自引用衝突：
1. 確保 .gitignore 包含 .quarantine/ 忽略規則。
2. 將 docs/ 完整移至 .quarantine/docs_legacy/（避免舊架構文檔誤導重構實作）。
3. 將 modules/ 完整移至 .quarantine/modules/。
4. 將 ys_codebase/ 完整移至 .quarantine/ys_codebase_legacy/。
5. 將 	est/ 完整移至 .quarantine/test_legacy/。
6. 將 extensions/ 完整移至 .quarantine/extensions_legacy/。
7. 將專案根目錄下的舊起手腳本與組態（yscb_cli.py, yscb_installer.py, yscb_config*.json）移至 .quarantine/legacy_scripts/。

### 受影響的檔案和函式

| 檔案路徑 | 影響範圍 | 說明 |
| :--- | :--- | :--- |
| project://.gitignore | 配置新增 | 確保 .quarantine/ 目錄受 Git 忽略 |
| project://docs/ | 移動封存 | 移至 .quarantine/docs_legacy/ |
| project://modules/ | 移動封存 | 移至 .quarantine/modules/ |
| project://ys_codebase/ | 移動封存 | 移至 .quarantine/ys_codebase_legacy/ |
| project://test/ | 移動封存 | 移至 .quarantine/test_legacy/ |
| project://extensions/ | 移動封存 | 移至 .quarantine/extensions_legacy/ |
| project://yscb_*.py, yscb_config*.json | 移動封存 | 移至 .quarantine/legacy_scripts/ |

### 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| sop_ext 清單 | on_demand | ❌ 排除 (Excluded) | 本子計畫為檔案目錄整理與備份隔離，不涉及特化擴充規則 |

### Decision Records

---

**[FT:DR-01] [NEW] 建立 .quarantine/ 完整保留歷史代碼供後續子計畫遷移**
- 結論：不直接刪除 gents-workflow、舊代碼與舊文檔，而是完整目錄結構保留至 .quarantine/。
- 理由：確保後續 sub_07、sub_08、sub_09 執行文檔重建與模組化遷移時，具備 100% 完整的歷史邏輯可供參考。

### 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：目前討論已完整，無其他新議題

---

## FT-2：實作清單

- [x] 1. 於 .gitignore 新增 .quarantine/ 忽略規則
- [x] 2. 建立 .quarantine/ 結構（modules/, legacy_scripts/, docs_legacy/ 等）
- [x] 3. 搬移隔離 docs/、modules/、ys_codebase/、	est/、extensions/
- [x] 4. 搬移隔離根目錄舊版起手腳本與組態檔至 .quarantine/legacy_scripts/
- [x] 5. 檢查確認工作空間處於 100% 純淨綠地狀態

### 偏差記錄

| 等級 | 偏差內容 | 處理方式 |
| :--- | :--- | :--- |
| Minor | 經討論將 docs/、	est/、extensions/ 全數納入封存，防止 Agent 認知干擾 | 更新 FT-1 範疇並完成移動封存 |

---

## FT-3：品質與 UX 審查

### 代碼清理

- [x] 移除所有 debug 輸出、未使用的變數、被註解掉的死代碼

### 測試與 UX 驗證

- [x] Agent CLI 自動化測試結果：實機檢視根目錄僅存保護清單目錄，.gitignore 規則生效，0 殘留
- [x] 開發者 UX / 手動測試確認：開發者指示執行封存並確認乾淨狀態

### 命名規範

- [x] 所有新增/修改的命名符合專案命名規範

### 文檔與知識庫同步 (詳見 DocumentationStandards.md)

- [x] 新增或修改的 public API 已加上標準文檔註解
  → 操作：N/A（本子計畫為檔案隔離備份，無 API 修改）
- [x] 涉及的模組/命名空間/套件對應之 docs/ 文件已更新
  → 操作：舊 docs/ 已完整封存至 .quarantine/docs_legacy/，將於 sub_07 全新綠地重建
- [x] 根目錄 CHANGELOG.md 已按 global_changelog.md 模板追加本次 Plan 之高階變更摘要
  → 操作：待主計畫整體結案時統一追加
- [x] docs/README.md 根層知識地圖已同步更新
  → 操作：N/A
- [x] 若發現坑點或工程妥協，已紀錄至對應模組之 DESIGN_NOTES.md
  → 操作：N/A

### Commit 訊息

`	ext
refactor(quarantine): isolate all legacy modules, scripts, test, and docs to .quarantine

- 封存 docs/ 至 .quarantine/docs_legacy/ 防止 Agent 認知干擾
- 封存 modules/、ys_codebase/、test/、extensions/ 至 .quarantine/
- 封存根目錄舊版起手腳本與組態至 .quarantine/legacy_scripts/
- 更新 .gitignore 加入 .quarantine/ 規則
- 為全新微內核架構 (sub_02, sub_03) 建立 100% 純淨綠地環境
`

### 變更摘要

完成現有檔案、模組、測試與舊知識庫的完整隔離與封存，專案根目錄達到 100% 綠地狀態，為後續 sub_02（宿主單檔 yscb.py）與 sub_03（核心模組 source/core）的純淨實作做好完整準備。

### Workflow 回顧

- **本次流程是否順暢**：是，精準識別 docs 認知干擾風險並迅速完成封存。
- **是否應該升級為 Full Track**：否（純檔案移動與備份隔離）
