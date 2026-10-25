# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-05` 在 `P03_api_spec.md` 與 `P06_test_plan.md` 中均有 1:1 對應驗證項
- [x] **邊界防護**：`EC-01` ~ `EC-03` 涵蓋常駐 Server 重入、組態與環境污染防禦、未知子命令熱派發攔截
- [x] **依賴純淨**：符合 `NFR-01`（43 支核心測試檔 100% Passed、0 Unknown）與 `NFR-02`（`.modules/` 剛性隔離與零反向依賴）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/{core,dev,server,knowledge-db}/README.md` | Audit | 核驗四大模組中觀手冊已在 `sub_01` ~ `sub_04` 完成同步且與現況 100% 一致 |
| **專題手冊** | `ys_codebase/source/{core,dev,server,knowledge-db}/README.md` | Modify / Audit | 清理 `ys_codebase/source/server/README.md` §2.2 多餘舊版 JSON 殘留片段，核驗各模組源碼 README 與 CLI / SDK 契約 100% 一致 |
| **設計決策** | `docs/{core,dev,server,knowledge-db}/DESIGN_NOTES.md` | Audit | 核驗 `sub_01` ~ `sub_04` 新增之 `DN-XX` 條目完整無缺漏 |
| **微觀註解** | `ys_codebase/source/dev/dev/tester.py` | Modify | 修正 `_run_op_test` 不再從父進程 `YSCB_TEST_QUIET` 繼承 `quiet_mode`，確保 `dev test --all -q` 下內聯 `op-test` 單元測試隔離 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時登記 `sub_05` 與主計畫 `2026_10_23_1122` 結案摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若常駐 Server 啟動時先前已有殘留進程或 Worker，是否會影響端到端驗收的準確性？  
> [*] **防護解法**：驗收流程第一步顯式執行 `server stop` 確保乾淨狀態，再執行 `server start` 驗證冷啟動 Hook 預熱與 `ServiceManager` 自動拉起 `knowledge-db-watcher`，最後執行 `server stop` 驗證優雅停機。

> [?] **尖銳問題 2**：本主計畫涵蓋之 8 份 Roadmap 儲備是否可能仍有殘留檔案留在 `plans/roadmap/`？  
> [*] **防護解法**：逐一核驗 `sub_01` ~ `sub_04` 目錄下之 `roadmap.md`（每份皆由模組加固 + 測試純化 2 份 Roadmap 合併而成，共 8 份），並掃描 `plans/roadmap/` 確認無任何 `core_*`、`dev_*`、`server_*`、`knowledge_db_*` 殘留檔案。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：核驗四大模組（`core`、`dev`、`server`、`knowledge-db`）`@build` 部署同步狀態、8 份已消費 Roadmap 儲備閉環歸檔與 42 支純化測試檔規模（`FR-04`, `FR-05`, `NFR-01`）。
2. **TASK-02**：執行跨模組靜態合規檢查（`contributes check`、`dev check --all`）、全生態系沙盒回歸測試（`dev test --all -q`）與常駐 Server 託管／多層子命令熱派發端到端驗證（`FR-01`, `FR-02`, `FR-03`, `EC-01`~`EC-03`, `NFR-02`）。
3. **TASK-DOC**：完成三層文檔最終對齊審計（`docs/`、源碼 `README.md`、`DESIGN_NOTES.md`），確認全模組文檔與實作 100% 同步（`FR-05`）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 本子計畫為全主計畫之收官驗收與文檔對齊階段（共 2 個核心驗收任務 + `TASK-DOC`），所有驗證均透過標準 `yscb.py` CLI 實機執行，零生產源碼侵入修改。
