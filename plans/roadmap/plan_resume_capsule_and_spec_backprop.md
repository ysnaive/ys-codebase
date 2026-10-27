# 技術路線圖：熱上下文恢復膠囊與後期規格反向回寫檢核 (Roadmap)

> 主題：熱上下文恢復膠囊與後期規格反向回寫檢核 (`plan_resume_capsule_and_spec_backprop`)  
> 歸檔日期：2026-10-27  
> 狀態：Ready  
> 目標範疇：`agents-workflow`（`agents_workflow/plans/scanner.py`、`status.py`、`verifier.py`、`assets/skills/{continue,development-sop}/`）  
> 前置解鎖條件：無  
> 模型：Unknown  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **未預期上下文壓縮（Context Compaction）時缺乏熱恢復膠囊**：目前 `plan status --resume` 雖已具備斷點階段領航與 `handoff.md` 原子閱後即焚機制，但若 Agent 在長任務中途遭遇 IDE / 平台強制壓縮上下文，當時並未預先執行 `/pause` 產出 `handoff.md`，重連後若僅靠階段領航提示，仍需翻讀多個前期檔案才能找回核心設計決策與進度。
- **後期修訂（Revision / P05 實作微調）易引發前期規格腐敗**：當計畫在 `P05` 實作期間或後續 `Revision` 調整了函式簽名、配置結構或架構細節時，若僅更新程式碼與 `revision_log.md` / `P05_task.md` 而未反向同步 `P02_architecture_plan.md` 與 `P03_api_spec.md`，會導致歸檔後的 `P02`/`P03` 與最終實作脫節。

### 1.2 現況與影響範圍評估
- `PlanScanner.execute_resume()` (`scanner.py`) 目前僅在存在 `handoff.md` 時輸出快照內文，無 `handoff.md` 時僅輸出階段狀態與下一步 SOP 參考檔路徑。
- `PlanVerifier` (`verifier.py`) 與 `development-sop` 尚未針對後期實作偏差或 `revision_log.md` 強制執行前期規格（`P02`/`P03`）反向回寫檢核。

### 1.3 核心根因
1. 缺少零 LLM 成本的確定性跨檔摘要抽取器（Deterministic Context Capsule Extractor），無法在無 `handoff.md` 時從既有 `P00`/`P02`/`P05`/`fast_track_plan.md` 即時合成精簡恢復摘要。
2. 缺少後期修訂對前期規格（`P02`/`P03`）的雙向一致性守門與反向回寫檢核項目。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：背景 LLM 子代理滾動摘要** | 每次階段推進後調用旁路子代理生成隱藏摘要檔 | 摘要語意較自然 | 消耗額外 API Token 與延遲，違反 ADR-02 零旁路代理原則 | ⭐️⭐️ |
| **方案 2：CLI 確定性熱上下文膠囊 + Verifier 反向回寫檢核** | 由 `scanner.py` 透過純 Python 正則/結構解析抽取 `P00` (DR)、`P02` (異動表)、`P05` (待辦進度) 合成 300~500 tokens 膠囊；並於 `verifier.py` 及模板加入規格反向回寫檢核 | 100% 零 API 成本、毫秒級回應、確保歸檔規格與最終代碼 100% 對齊 | 需針對標準模板章節結構編寫穩健抽取邏輯 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（旁路 LLM 摘要） | 方案 2（CLI 確定性膠囊 + 反向回寫） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 中（受限於各宿主環境子代理支援度） | 高（100% Python 標準庫解析既有 Markdown 結構） |
| **後續維護難度 (Maintenance)** | 高（Prompt 與多代理狀態同步複雜） | 低（與 `PlanStatusResolver` 及模板結構單向綁定） |
| **可靠性 (Reliability)** | 中（LLM 摘要可能幻覺或遺漏關鍵簽名） | 極高（確定性抽取 `DR-XX`、異動檔案表與 `[ ]` 任務項） |
| **落地難度 (Implementation)** | 高 | 低 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：於 scanner.py / status.py 實作 build_recovery_capsule(plan_dir)
# 自動提取：
# - P00 / fast_track_plan 之 DR 決策摘要
# - P02 之架構異動檔案表
# - P05 / fast_track_plan / revision_log 之已完成 [x] 計數與接下來 3 筆未完成 [ ] 任務

# 步驟 2：整合至 `python yscb.py agents-workflow plan status --resume` 輸出區塊

# 步驟 3：於 P06/P07/revision_log 模板與 verifier.py 增補「前期規格反向回寫 (Back-propagation Check)」檢核邏輯
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 在不改變現有 `handoff.md` 閱後即焚語義的前提下，為 `plan status --resume` 加上無 `handoff.md` 時的自動結構化膠囊輸出，並強化後期規格同步紀律。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（熱恢復膠囊引擎）**：於 `agents_workflow/plans/status.py` 與 `scanner.py` 實作跨階段關鍵段落抽取（控制在 300~500 tokens 內）。
2. **Stage 2（反向回寫守門與模板同步）**：更新 `P05`、`P07`、`revision_log` 模板與 `verifier.py`，強制要求實作期間若有 API 或架構變更須反向更新 `P02`/`P03`。
3. **Stage 3（沙盒單元測試與發布）**：通過 `dev check agents-workflow` 與 `dev test agents-workflow` 並熱部署更新。

