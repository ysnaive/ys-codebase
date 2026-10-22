# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：工作流審計全面修復 (Workflow Audit Remediation)  
> 建立日期：2026-10-17  
> 所屬主計畫：2026_10_17_1133_workflow_optimization  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | `PlanStatusResolver` 準確從 Blockquote 解析標頭狀態，內文任意處出現 "Completed" 不受干擾 | FR-01 | `pytest tests/test_plans_status.py -k test_header_status` |
| **FT-02** | 單元測試 | `PlanArchiver` 攔截標頭為 In Progress 但正文含 Completed 之 Fast Track 計畫 | FR-02 | `pytest tests/test_plans_status.py -k test_archiver_ft_in_progress` |
| **FT-03** | 單元測試 | `PlanScanner` 在 P05 進行中且 P06 為 Confirmed 時正確回報 Phase 5 而非 Phase 6 | FR-03 | `pytest tests/test_plans_status.py -k test_scanner_p05_with_p06_confirmed` |
| **FT-04** | 單元測試 | `PlanScanner` 正確識別 Research Track，並依 R 檔狀態顯示 Concluded 或 Draft | FR-04 | `pytest tests/test_plans_status.py -k test_scanner_research_track` |
| **FT-05** | 單元測試 | `PlanVerifier` 正確將 `R01_xxx.md` 映射至調研模板，即便檔名無 "research" 字樣 | FR-05 | `pytest tests/test_plans_status.py -k test_verifier_research_mapping` |
| **FT-06** | 單元測試 | `PlanVerifier` 收緊測試 ID 判定為正則 `\b(FT\|ET\|RT)-\d{2}\b`，僅含 FP-03 時判定失敗 | FR-06 | `pytest tests/test_plans_status.py -k test_verifier_test_id_regex` |
| **FT-07** | 單元測試 | `PlanVerifier` 動態推導佔位符，成功攔截 `[調研主題/所屬功能]` 等未替換模板佔位符 | FR-07 | `pytest tests/test_plans_status.py -k test_verifier_dynamic_placeholders` |
| **FT-08** | 單元測試 | `PlanArchiver` 目的地衝突時不刪除 `handoff.md` | FR-08 | `pytest tests/test_plans_status.py -k test_archiver_handoff_preserved_on_conflict` |
| **FT-09** | 靜態測試 | `PlanVerifier` 死代碼清理無未引用之 `VALID_CHANGELOG_TYPES` 且 docstring 對齊 | FR-09 | `pytest tests/test_plans_status.py -k test_verifier_deadcode_clean` |
| **FT-10** | 靜態檢核 | `AgentsStandards.md` 模板指針包含 `development-sop/SKILL.md` 語意標籤 | FR-10 | `python yscb.py dev check` |
| **FT-11** | 靜態檢核 | 資產庫中 Fast Track 步驟皆已更名為 `FP-01/02/03` | FR-11 | `python yscb.py dev check` |
| **FT-12** | 靜態檢核 | P06 狀態機手冊與卡片皆對齊 Draft -> Confirmed -> In Progress -> Passed -> Completed | FR-12 | `python yscb.py dev check` |
| **FT-13** | 靜態檢核 | `continue/SKILL.md` 判定順序、Research 分支與 P07 列對齊 | FR-13 | `python yscb.py dev check` |
| **FT-14** | 靜態檢核 | Research 調研命名規範 `R{NN}_{topic}.md` 統一對齊 | FR-14 | `python yscb.py dev check` |
| **FT-15** | 靜態檢核 | Revision 4 大熔斷條件與 Bug Fix 排除規則寫入 `plan_modes.md` | FR-15 | `python yscb.py dev check` |
| **FT-16** | 靜態檢核 | `revision_log.md` 重開與封存修訂規則對齊 | FR-16 | `python yscb.py dev check` |
| **FT-17** | 靜態檢核 | `plan_modes.md` 移除 verify 強制檢核附掛修訂之描述 | FR-17 | `python yscb.py dev check` |
| **FT-18** | 靜態檢核 | `fast_track_plan.md` 模板包含 4 守門檢核表且移除寫死 Completed | FR-18 | `python yscb.py dev check` |
| **FT-19** | 靜態檢核 | `auto/SKILL.md` 允許 P00 Confirmed 觸發 | FR-19 | `python yscb.py dev check` |
| **FT-20** | 靜態檢核 | `revision_log.md` 模板 CHANGELOG 同步依比例原則限使用者感知變更 | FR-20 | `python yscb.py dev check` |
| **FT-21** | 靜態檢核 | `development-sop` 追溯鏈表登記 `[FP-0X:DR-XX]` 與 `[REV-XX:DR-XX]` | FR-21 | `python yscb.py dev check` |
| **FT-22** | 靜態檢核 | Umbrella 詞彙統一為 Pre-planned / Incremental，狀態選項標準化 | FR-22 | `python yscb.py dev check` |
| **FT-23** | 靜態檢核 | Roadmap 描述統一為每主題一檔 `{topic}.md` | FR-23 | `python yscb.py dev check` |
| **FT-24** | 靜態檢核 | 關鍵守門標記一致化（P06 UX、禁止擅自發布、禁止擅自歸檔） | FR-24 | `python yscb.py dev check` |
| **FT-25** | 靜態檢核 | `context-init/SKILL.md` 移除懸空引用條款並修正 CLI 敘述 | FR-25 | `python yscb.py dev check` |
| **FT-26** | 靜態檢核 | `P07_walkthrough.md` 模板移除預填 PASS 與已登記 DN | FR-26 | `python yscb.py dev check` |
| **FT-27** | 靜態檢核 | `agents-workflow.json` 與 `_manifest.md` 元數據同步 | FR-27 | `python yscb.py dev check` |
| **FT-28** | 靜態檢核 | `assets/` 41 檔全文件自檢修復項（F-01~F-07）零硬編碼 `docs/`/`plans/` 且 Stage 1/2 編譯零告警 | FR-10~FR-27 | `python yscb.py dev check` |
| **RT-01** | 全量回歸 | `agents-workflow` 全模組既有單元測試 100% 通過 | NFR-03 | `python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `PlanStatusResolver` 準確從 Blockquote 解析標頭狀態，內文 Completed 完全不干擾 | 2026-10-17 11:55 |
| **FT-02** | `Passed` | `PlanArchiver` 準確攔截標頭為 In Progress 但正文含 Completed 之 Fast Track 計畫 | 2026-10-17 11:55 |
| **FT-03** | `Passed` | `PlanScanner` 在 P05 進行中且 P06 為 Confirmed 時正確回報 Phase 5 而非 Phase 6 | 2026-10-17 11:55 |
| **FT-04** | `Passed` | `PlanScanner` 正確識別 Research Track，並依 R 檔狀態顯示 Concluded 或 Draft | 2026-10-17 11:55 |
| **FT-05** | `Passed` | `PlanVerifier` 正確將 `R01_xxx.md` 映射至調研模板，即便檔名無 "research" 字樣 | 2026-10-17 11:55 |
| **FT-06** | `Passed` | `PlanVerifier` 收緊測試 ID 判定為正則 `\b(FT\|ET\|RT)-\d{2}\b`，僅含 FP-03 時判定失敗 | 2026-10-17 11:55 |
| **FT-07** | `Passed` | `PlanVerifier` 動態推導佔位符，成功攔截 `[調研主題/所屬功能]` 未替換佔位符 | 2026-10-17 11:55 |
| **FT-08** | `Passed` | `PlanArchiver` 目的地衝突時不刪除 `handoff.md`，上下文獲得完整保護 | 2026-10-17 11:55 |
| **FT-09** | `Passed` | `PlanVerifier` 死代碼清理無未引用之 `VALID_CHANGELOG_TYPES` 且 docstring 對齊 | 2026-10-17 11:55 |
| **FT-10** | `Passed` | `AgentsStandards.md` 模板指針指向 `development-sop/SKILL.md` 佔位符 | 2026-10-17 12:01 |
| **FT-11** | `Passed` | 資產庫中 Fast Track 步驟皆已更名為 `FP-01/02/03` | 2026-10-17 12:01 |
| **FT-12** | `Passed` | P06 狀態機手冊與卡片皆對齊 Draft -> Confirmed -> In Progress -> Passed -> Completed | 2026-10-17 12:01 |
| **FT-13** | `Passed` | `continue/SKILL.md` 判定順序、Research 分支與 P07 列對齊 | 2026-10-17 12:01 |
| **FT-14** | `Passed` | Research 調研命名規範 `R{NN}_{topic}.md` 統一對齊 | 2026-10-17 12:01 |
| **FT-15** | `Passed` | Revision 4 大熔斷條件與 Bug Fix 排除規則寫入 `plan_modes.md` | 2026-10-17 12:01 |
| **FT-16** | `Passed` | `revision_log.md` 重開與封存修訂規則對齊 | 2026-10-17 12:01 |
| **FT-17** | `Passed` | `plan_modes.md` 移除 verify 強制檢核附掛修訂之描述 | 2026-10-17 12:01 |
| **FT-18** | `Passed` | `fast_track_plan.md` 模板包含 4 守門檢核表且移除寫死 Completed | 2026-10-17 12:01 |
| **FT-19** | `Passed` | `auto/SKILL.md` 允許 P00 Confirmed 觸發 | 2026-10-17 12:01 |
| **FT-20** | `Passed` | `revision_log.md` 模板 CHANGELOG 同步依比例原則限使用者感知變更 | 2026-10-17 12:01 |
| **FT-21** | `Passed` | `development-sop` 追溯鏈表登記 `[FP-0X:DR-XX]` 與 `[REV-XX:DR-XX]` | 2026-10-17 12:01 |
| **FT-22** | `Passed` | Umbrella 詞彙統一為 Pre-planned / Incremental，狀態選項標準化 | 2026-10-17 12:01 |
| **FT-23** | `Passed` | Roadmap 描述統一為每主題一檔 `{topic}.md` | 2026-10-17 12:01 |
| **FT-24** | `Passed` | 關鍵守門標記一致化（P06 UX、禁止擅自發布、禁止擅自歸檔） | 2026-10-17 12:01 |
| **FT-25** | `Passed` | `context-init/SKILL.md` 移除懸空引用條款並修正 CLI 敘述 | 2026-10-17 12:01 |
| **FT-26** | `Passed` | `P07_walkthrough.md` 模板移除預填 PASS 與已登記 DN | 2026-10-17 12:01 |
| **FT-27** | `Passed` | `agents-workflow.json` 與 `_manifest.md` 元數據同步 | 2026-10-17 12:01 |
| **FT-28** | `Passed` | `assets/` 41 檔全文件自檢修復項（F-01~F-07）全數落實，0 硬編碼殘留且編譯 100% 通過 | 2026-10-17 12:21 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow` 97/97 測試 100% 通過 | 2026-10-17 12:21 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py agents-workflow plan status` 驗證 ASCII 矩陣格式正常 | `[測試通過]` | 開發者完成全文件原始碼自檢確認並指示推進至 P07 (2026-10-17 12:15) |

> Claude Opus 5.5
