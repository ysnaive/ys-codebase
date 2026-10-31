# 技術調研報告：YS-Codebase 母倉全模組實測與 Code-Optimizer 優化診斷 (R01_ys_codebase_report.md)

> 調研主題：基於母倉 5 大模組三代盲審重構 (R01->R02->R03) 與 Session-Trace 遙測之 `/code-optimizer` 實測優化診斷  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1605_code_optimizer_skill (sub_01_empirical_optimization)  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  - 在完成 [`code-optimizer`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md) 初版建置後，我們隨即於母倉開立 [`2026_10_30_1641_code_optimize`](../../../2026_10_30_1641_code_optimize/umbrella_overview.md) 分類型主計畫，針對全倉 5 大核心模組（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）以 **`Mode A`（收斂期 / 允許破壞性清理）** 進行了大規模實戰檢驗。
  - 實測過程經歷了三個世代的完整閉環：
    1. **第一代 (`R01` 診斷 + 5 路子代理並行 `/auto` 實作)**：完成 `D1~D5` 初步病灶掃除與 `S1~S6` 重構，於 `P06` 統一編譯測試，發現並修復 1 處 `BM25Engine` 合併退化。
    2. **第二代 (`R02` 禁讀 `plans/` 無提示詞盲審 + P06 收斂修復)**：5 路全新盲審子代理在完全不讀歷史計畫文檔的條件下重新診斷源碼，抓出第一代子代理遺留的 **30+ 處「半調子 `S2` 1 行轉發殼層 / `staticmethod` 重綁定」**、1 處未綁定類別呼叫（`KnowledgeDBConfig.resolve_threads`）及若干殘留別名。
    3. **第三代 (`R03` 禁讀 `plans/` 無提示詞盲審 + S6 過度拆分評估)**：再次派發 5 路盲審子代理，抓出最後 4 個微觀缺陷（`lock.py` FD 洩漏防護、副檔名註冊對齊、37 處 `(M-0X/F-0X)` 審計編號註解噪音、`verifier.py` 單次正則匹配），同時暴露出當模組已高度收斂時，盲審子代理受 `500~800 行` 門檻驅動而在 `core`/`dev`/`server` 陷入 **「`S6` 過度拆分（Over-Splitting）」** 的結構性問題。
- **調研目標**：
  - 結合 `session-trace` 量化遙測（總步驟 `645`、工具呼叫 `375` 次、子代理 `17` 次、50 個變更檔案、28 個摩擦訊號）與三代盲審對比證據，精確定位 [`code-optimizer`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md) 及其 3 份 `references/` 的規範漏洞，作為後續與 `R02`、`R03` 下游實測報告交叉會診之基準。

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

針對母倉實測暴露出的 5 大核心技能缺陷，以下對比各維度的改進候選方案：

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **議題 1：S2 無狀態抽離殘留轉發殼層**<br/>**方案 1A（維持現狀）** | 僅要求將無狀態方法抽為模組級 `_func`，不規定原類別方法處置方式 | 規則字數最少 | 子代理為避免修改測試或同檔呼叫，在類別上留下大量 `_fn = staticmethod(_fn)` 或 1 行 wrapper（本次實測殘留 30+ 處） | ★☆☆☆☆ |
| **議題 1：S2 無狀態抽離殘留轉發殼層**<br/>**方案 1B（推薦：S2 零殘留轉發殼層鐵律 + 測試調用點同步）** | 於 `refactoring-playbook.md §2 (S2)` 明令禁止保留私有 `staticmethod` 綁定或 1 行轉發殼層，並強制同步更新同模組呼叫點與 `tests/` 單元測試 | 徹底消除類別表面積假性縮減，一次到位達成 `Mode A` / 內部私有方法收斂 | 子代理執行 `S2` 時需同步更新直接測 `instance._helper()` 的單元測試 | ★★★★★ |
| **議題 2：D1/S6 大檔案過度拆分**<br/>**方案 2A（僅調高行數門檻至 1200 行）** | 將 `diagnostic-matrix.md §1` 的 `500~800` 行改為 `1200` 行 | 修改最簡單 | 治標不治本：真正耦合正交職責的 600 行檔案會被漏放，而超過 1200 行的單一管線仍會被誤拆 | ★★☆☆☆ |
| **議題 2：D1/S6 大檔案過度拆分**<br/>**方案 2B（推薦：正交耦合判準優先 + S6 三大免拆守門 + 允許 `P0=0`）** | 移除純行數定罪，於 `refactoring-playbook.md §6 (S6)` 增設「共享交易鎖/狀態機、單一 `Report` 線性檢查管線、自指紋校驗/單檔契約」三大免拆守門，並明訂成熟模組允許宣告 `P0 = 0` | 精準區分「正交耦合巨石（應拆，如 `parsers/`）」與「高內聚狀態機/管線（禁拆，如 `engine.py`, `checker.py`, `master.py`）」 | 需在 `diagnostic-matrix.md` 與 `refactoring-playbook.md` 補充約 15 行結構化判準 | ★★★★★ |
| **議題 3：S3 同構合併遺失邊界條件**<br/>**方案 3A（推薦：S3 20% 差異分支不變量核對 + Mock/Dummy 同步掃描）** | 於 `refactoring-playbook.md §3 (S3)` 強制要求合併前列出「不相似 20%」的業務守門條件（如 `min_cov` 覆蓋率門檻），並在移除相容分支時同步掃描 `tests/` 內之 `Dummy*`/`Mock*` | 直接防止 `BM25Engine` 合併退化與 `DummyIndex` 簽名失步導致的 `GATE_BOUNCE` | 略微增加 `S3` 重構前的靜態比對步驟 | ★★★★★ |
| **議題 4：生產代碼殘留審計編號註解**<br/>**方案 4A（推薦：擴充紅線 4 禁寫診斷工單編號與變更歷史）** | 於 `SKILL.md §核心原則 紅線 4` 明確禁止將 `D1-XX`、`F-XX`、`M-XX`、`S1~S6` 或「移除某某舊邏輯」寫入源碼註解與 Docstring | 根除 `knowledge-db` 出現 37 處 `(M-0X / F-0X)` 註解污染的反模式 | 零額外成本 | ★★★★★ |
| **議題 5：跨代盲審 (`R{NN}`) 與並行延遲測試**<br/>**方案 5A（推薦：原生內建 `R{NN}` 零錨定盲審協議與 Umbrella 批次驗證）** | 於 `SKILL.md` 與 `exploration-and-delegation.md` 支援 `R{NN}_code_optimization_audit.md` 盲審模式（禁讀 `plans/` 既有文檔、雙軌評估 `Mode A/B`）及 Umbrella 子計畫延遲至 `P06` 統一跑測 | 將本次實測極高價值的「無偏見多代盲審收斂法」沉澱為標準能力，免除開發者手寫長 Prompt | 需擴充 `exploration-and-delegation.md` 約 15 行規範 | ★★★★★ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 母倉實測遙測數據與三代收斂軌跡 (PoC Empirical Metrics)

以下為 [`2026_10_30_1641_code_optimize`](../../../2026_10_30_1641_code_optimize/umbrella_overview.md) 全會話之 `session-trace` 量化指標與三代盲審收斂對照：

- **會話基礎遙測 (`Tier 1 + Tier 2`)**：
  - **總耗時與規模**：`2h 53m 37s` | `645` Steps | `17` 次子代理派發 | `50` 個 Git 變更檔案 | 全倉 5 大模組 `611` 個單元測試 100% 通過（`core` 206、`dev` 80、`server` 39、`knowledge-db` 151、`agents-workflow` 135）。
  - **Token 效率**：有效 Token `~583,676 (82.8%)` | 浪費 Token `~120,969 (17.2%)`（其中 `BlindReads` 佔 `64,803`，主要來自 `Steps 176~281` 主代理對全模組執行未分頁 `git diff` 導致輸出截斷至 `output.txt` 後連續讀取 9 次）。

| 模組子計畫 | 第一代 (`R01` + `/auto` 重構) 關鍵成果与遺留瑕疵 | 第二代 (`R02` 盲審 + P06 收斂) 抓出並修復之關鍵項目 | 第三代 (`R03` 盲審 + S6 評估) 最終微調與過度拆分判定 |
| :--- | :--- | :--- | :--- |
| **`sub_01` (`core`)** | 完成 `engine.py`/`cli.py`/`contributes.py` 階段聚合與 `S2` 抽離；**但遺留 7 處 `staticmethod` 重綁定與 `_deep_merge` 1 行 wrapper** | 抓出並清除 `AtomicEngine` 7 處 `staticmethod` 重綁定、`ContributesAggregator._deep_merge` wrapper、`_normalize_target_item` 雙重 `.strip()` | **抓出真實微觀缺陷**：[`lock.py`](../../../../ys_codebase/source/core/core/platform/lock.py) `InterProcessLock.acquire` 在 `_lock_fd` 失敗時未 `os.close(fd)`。<br/>**過度拆分誤報**：因 `engine.py` 1,007 行建議強拆 3 檔（判定駁回：共享 `InterProcessLock("engine")` 狀態機）。 |
| **`sub_02` (`dev`)** | 完成 `checker.py`/`builder.py`/`tester.py`/`publisher.py` `S1~S5` 重構；**但遺留 `Builder._should_ignore` wrapper 與 `_check_cli_help` 內部重複 helper** | 抓出並清除 `Builder._should_ignore` 1 行 wrapper、抽離 `_run_cli_help_probe`、合併 `_resolve_module_source_dir` 與 `tester._terminate_process_tree` | **過度拆分誤報**：因 `checker.py` 1,133 行建議拆為 4 個 `checker_*.py`，並建議拆分 `publisher.py`（判定駁回：`checker.py` 為單一 `CheckReport` 線性管線；`publisher.py` 含整檔 SHA-1 自指紋校驗，拆檔會破壞熱更新偵測）。 |
| **`sub_03` (`server`)** | 完成 `master.py`/`worker.py`/`client.py`/`watcher.py` 重構；**但遺留 `ModulesWatcher` 3 個 1 行 wrapper 與 `MasterDaemon.stop()` 死分支** | 抓出並清除 `ModulesWatcher` 3 個 1 行轉發方法、`MasterDaemon.stop()` 冗餘 `if self._server:` 分支、統一 `client.py` socket 讀取 helper | **過度拆分誤報**：因 `master.py` 784 行建議拆為 3 檔（判定駁回：所有方法高度耦合讀寫同一組 `_lock`、`workers` 與 `pending_requests` 狀態表）。 |
| **`sub_04` (`knowledge-db`)** | 完成 `parsers/` (9 檔) 與 `search/` (4 檔) `S6` 物理拆包；**但遺失 `BM25Engine` 50% `min_cov` 門檻、引入 `resolve_threads` 未綁定呼叫、寫入 37 處 `(M-0X/F-0X)` 註解** | 抓出並修復 `embedding.py` `KnowledgeDBConfig().resolve_threads()` 實例呼叫、刪除 `hybrid.py` 過時 `hasattr` 分支（期間觸發 `test_retrieval.py` `DummyIndex` `GATE_BOUNCE` 後修復） | **抓出真實微觀缺陷**：1. `css_parser.py` (`.sass`) / `spice_parser.py` (`.netlist`) / `knowledge-db.json` (`.spice`, `.net`) 副檔名註冊不一致；2. 源碼殘留 37 處 `(移除... M-0X / F-0X)` 審計編號噪音（全數清理完成）。 |
| **`sub_05` (`agents-workflow`)** | 完成 `plans/` 與 `session_trace` `S6` 拆包；**但在 `PlanVerifier` 遺留 11 個 1 行 wrapper、`SessionTraceEngine` 遺留 2 個 wrapper** | 抓出並清除 `PlanVerifier` 11 個 1 行轉發方法、`SessionTraceEngine` 2 個 wrapper、`PlanManager.promote_seed` 過時 alias 與 `_check_skill_frontmatter` 重複邏輯 | **抓出真實微觀缺陷**：[`verifier.py`](../../../../ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py) `_check_changelog_content` 雙重 `re.search` 改為單次 `m = re.search(...)`。<br/>**架構健康度確認**：`R03` 明確判定 `P0 = 0`，驗證 `S6` 架構已完美收斂。 |

---

### 3.2 六大實證摩擦根因解剖 (Six Empirical Root Causes)

1. **`[RC-01] S2 無狀態邏輯剝離之「半調子轉發殼層陷阱 (Half-Baked S2 Wrapper Trap)」`**：
   - **定位**：[`references/refactoring-playbook.md §2 (S2)`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/refactoring-playbook.md#L15-L21)
   - **解剖**：現行規範要求將不依賴 `self` 的輔助方法抽離為模組級 `_func_name`，但未禁止在原類別保留 `_func_name = staticmethod(_func_name)` 或 `def _func_name(self, ...): return _func_name(...)`。子代理為逃避更新同類別內部的 `self._func_name()` 呼叫或 `tests/` 裡的 `obj._func_name()` 測試，普遍選擇在類別上留一層 1 行轉發殼，導致第一波重構在 5 個模組留下超過 30 個無意義 wrapper。
2. **`[RC-02] D1 / S6 缺乏「高內聚狀態機與線性管線免拆守門 (Anti-Fragmentation Gate)」`**：
   - **定位**：[`references/diagnostic-matrix.md §1 (P0)`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/diagnostic-matrix.md#L11) & [`references/refactoring-playbook.md §6 (S6)`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/refactoring-playbook.md#L48-L62)
   - **解剖**：`diagnostic-matrix.md` 以「超過 `500~800` 行」作為 `P0` 首要判準，且未聲明「當模組已無正交職責混雜時，`P0` 應為 `0`」。這導致 `R03` 盲審子代理面對已收斂的 `engine.py` (1,007L)、`checker.py` (1,133L)、`master.py` (784L) 時，為強湊 `P0` 績效而提出破壞「行為局部性 (Locality of Behavior)」與「SHA-1 自指紋契約 (`publisher.py`)」的過度拆檔建議。
3. **`[RC-03] S3 同構路徑合併缺乏「20% 差異分支不變量核對」與「測試替身 (Dummy/Mock) 同步檢核」`**：
   - **定位**：[`references/refactoring-playbook.md §3 (S3)`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/refactoring-playbook.md#L23-L28) & [`SKILL.md §步驟 4`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md#L103-L108)
   - **解剖**：子代理在合併 `BM25Engine.search` 與 `search_aggregated` 時，只看到了 80% 相似的迴圈骨架，直接抹平了 `search_aggregated` 獨有的「複合詞 ≥ 50% sub-token 覆蓋率門檻 (`min_cov`)」；而在移除 `hybrid.py` 退避分支時，未同步檢查 `tests/test_retrieval.py` 中的 `DummyIndex.search` 回傳格式，引發測試退件。
4. **`[RC-04] 生產代碼「審計工單編號污染 (`F-XX / M-XX` Comment Pollution)」防線缺失`**：
   - **定位**：[`SKILL.md §核心原則 (紅線 4)`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md#L29)
   - **解剖**：紅線 4 雖禁止 `# Step 1` 與 `Phase 5 / FR-01` 註解，但未點名禁止 `/code-optimizer` 報告自身的診斷編號（`D1-XX`, `F-XX`, `M-XX`）與「移除某某舊邏輯」的變更說明，導致子代理在 `knowledge-db` 源碼留下 37 處 `(移除... M-08)` 等工單噪音。
5. **`[RC-05] 缺乏原生「跨代零錨定盲審協議 (`R{NN}` Blind Convergence Audit)」與「Umbrella 批次延遲測試協定」`**：
   - **定位**：[`SKILL.md §步驟 2 & §步驟 4`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md#L61-L119) & [`references/exploration-and-delegation.md §2`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/references/exploration-and-delegation.md#L29-L64)
   - **解剖**：本次開發者指導的「禁止讀取 `plans/` 已落檔文檔、不給引導性方向提示之 `R02/R03` 盲審法」以及「Umbrella 靜態隔離子計畫並行實作、跳過單模測試統一於 `P06` 驗證」，在實戰中展現了極高的缺陷捕獲率與時間效益，但現行技能僅寫死 `R01` 單次診斷，尚未將此二項高階工作流標準化。
6. **`[RC-06] 大型重構後之主代理 Diff 審查防截斷紀律 (`git diff --stat` First)`**：
   - **定位**：[`SKILL.md §步驟 4`](../../../../ys_codebase/source/agents-workflow/assets/skills/code-optimizer/SKILL.md#L109-L118)
   - **解剖**：多子代理完成 50 個檔案重構後，若主代理直接執行全模組 `git diff`，極易因輸出超過數萬字元而被宿主截斷至 `output.txt`，進而誘發分段讀取 `output.txt` 的 Context 浪費（本次浪費 `~64,803` Tokens）。應明訂大型重構驗收強制先走 `git diff --stat` 與 `knowledge-db search`，嚴禁對全模組跑裸 `git diff`。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **母倉實測推薦落地策略（待與 `R02` / `R03` 下游報告會診後合併執行）**：
  1. **強化 `references/refactoring-playbook.md`**：
     - **`§2 (S2)`**：新增「零殘留轉發殼層鐵律」，禁止保留私有 `staticmethod` 重綁定或 1 行 pass-through wrapper，強制同步更新同模組呼叫與 `tests/`。
     - **`§3 (S3)`**：新增「20% 差異分支不變量逐行核對表」，嚴禁在提取共用核心時抹平任一分支特有的邊界過濾門檻。
     - **`§6 (S6)`**：新增「反碎片化與三大免拆守門（共享鎖與狀態機、單一累加器線性管線、自指紋/單檔契約）」。
  2. **強化 `references/diagnostic-matrix.md`**：
     - **`§1 (P0)`**：將「多重正交職責混雜」置於行數之前，明確宣告高內聚成熟模組允許 `P0 = 0`，防止為湊表格而強拆檔案。
  3. **強化 `SKILL.md` 與 `references/exploration-and-delegation.md`**：
     - **紅線 4**：明確禁止在源碼註解與 Docstring 寫入 `D1-XX / F-XX / M-XX / S1~S6` 診斷編號或「已移除某舊邏輯」之變更歷史。
     - **步驟 2 & 委派契約**：原生支援 `R{NN}_code_optimization_audit.md` 跨代零錨定盲審收斂協議（禁讀 `plans/` 既有文檔）。
     - **步驟 4**：增補「`tests/` 內 `Dummy*`/`Mock*` 測試替身同步檢核」、「Umbrella 靜態隔離並行實作 + `P06` 統一編譯測試」與「`git diff --stat` 防截斷驗收紀律」。
- **後續行動與銜接**：
  - 本報告 (`R01_ys_codebase_report.md`) 現已固化落檔；請開發者提供另外兩個下游專案之實測報告以建立 `R02` 與 `R03`，待三份實測報告齊備後進行跨專案綜合檢視並拍板最終升級方案。

