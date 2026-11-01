# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：PXX-05_auto 動態區段綜合模板與工作流工具鏈打磨 (`auto_plan_and_workflow_refinement`)  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `PXX-05_auto.md` 動態區段綜合模板與技能更新 | 建立 `assets/templates/PXX-05_auto.md` 模板並註冊於 `contributes/agents-workflow.json`，整合 `P01`~`P05` 五大核心契約章節（需求與邊界、架構與異動檔案、API 簽名契約、定稿審查與文檔衝擊、單一實作任務勾選清單與偏差表）；同步更新 `auto/SKILL.md` 與 `development-sop/SKILL.md`。 | P0 | [P00:DR-01] |
| **FR-02** | `P0{start}-05_auto.md` 跨階段動態解析與驗證器相容 | `PlanStatusResolver.resolve_phase_file` 支援將 `P01`~`P05` 動態解析至涵蓋該階段之 `P0[1-5]-05_auto.md`；`PlanVerifier` 支援動態依據起始階段 `min_phase` 篩選應檢核之模板章節（如 `P03-05_auto.md` 僅檢核 `§3`~`§5`），並向下 100% 相容傳統 `P01_*_auto.md` ~ `P05_*_auto.md`；`SessionTraceEngine.audit_plan_mtimes` 對指向同一綜合檔之階段豁免自我逆序比較。 | P0 | [P00:DR-01] |
| **FR-03** | `PlanSearcher` 子計畫去重修復、角色權重排序與 `--full`/`--json` | 修正 `search_drs` 去重鍵為 `(plan.name, rel_src_str, dr_id)` 防止 Umbrella 各 `sub_XX` 同名 DR 互相吞沒；支援無冒號之條列式 DR 提取；修正 `search_full_text` 之 `rel_path` 保留子計畫路徑；加入檔案角色權重與計畫時間衰減排序；於 `plan search` 新增 `--full`、左側截斷與 `--json` 輸出。 | P0 | [P00:DR-02] |
| **FR-04** | `plan status --resume` 無 `handoff.md` 確定性恢復膠囊與歸檔提示 | 於 `PlanScanner` 實作 `build_recovery_capsule(plan_dir)`，當未建立 `handoff.md` 時自動提取關鍵 DR、受影響檔案與未完成 Checkbox 進度；於 `render_matrix_ascii` 偵測到已 `Completed`/`Concluded` 之頂層計畫時輸出 `plan archive` 歸檔提醒。 | P0 | [P00:DR-03] |
| **FR-05** | `ArtifactCompiler` Stage 2 行內代碼塊反引號保留 (`[DN-AW-03]`) | 修正 `compiler.py:_replace_in_code_span`，當 `` `__${uri}__` `` 無自訂錨點且非超連結語境時，展開後保留外層反引號 `` `{resolved}` ``。 | P0 | [P00:DR-04] |
| **FR-06** | `PlanVerifier` 跨環境路徑可攜性 (`PORTABILITY`) 與偏差回寫 (`BACKPROP`) 警告 | 於 `_verify_markdown_file` 偵測非代碼塊內之硬編碼 `file:///` 或本機磁碟機路徑並發出 `PORTABILITY` (`WARN`)；於 `_check_cross_file_and_traceability` 偵測獨立 `P05_task.md` 記載 `Major`/`Critical` 偏差但 `P02`/`P03` 未同步更新時發出 `BACKPROP` (`WARN`)。 | P1 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 自中途階段（如 `P02` 已人工定案）啟動 `/auto` 產出 `P03-05_auto.md` | `resolve_phase_file` 對 `P01`/`P02` 優先返回既有之 `P01_requirements_spec.md`/`P02_architecture_plan.md`，對 `P03`~`P05` 返回 `P03-05_auto.md`；`PlanVerifier` 自動以 `min_phase=3` 豁免 `P03-05_auto.md` 中之 `§1 (P01)` 與 `§2 (P02)` 標題檢核。 |
| **EC-02** | 歷史封存或既有計畫仍使用 5 份 `P01_*_auto.md` ~ `P05_*_auto.md` | `resolve_phase_file` 與 `map_file_to_template` 維持傳統 `<stem>_auto.md` 分支，確保歷史計畫與既有測試 100% 無損通過。 |
| **EC-03** | Markdown 連結 `[text](`__${uri}__`)` 與有錨點 `` `__$(anchor){uri}__` `` 展開 | `_clean_md_link_match` 自動剝除超連結括號內之反引號，且有 `anchor` 之語法維持原無反引號契約，確保既有超連結與錨點語法零回歸。 |
| **EC-04** | 計畫檔案之 Fenced Code Block 或行內反引號中包含 `C:\` 或 `file:///` 範例字串 | `_verify_markdown_file` 僅針對剝除代碼塊與行內反引號後之 `non_code_lines` 進行 `PORTABILITY` 掃描，避免技術範例誤觸警告。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | 100% 使用 Python 標準庫 (`re`, `os`, `json`, `pathlib`)，不引入任何第三方套件。 |
| **NFR-02** | 技能精簡度 | `auto/SKILL.md` 全文維持 $\le 75$ 行，且所有技能與標準資產通過 Stage 1/2 編譯零警告。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 修改 `contributes/agents-workflow.json` 或 `assets/` 模板與技能後，必須先透過 `install agents-workflow@build --force` 更新 `.modules/agents-workflow` 運行空間，再執行 `agents-workflow release --force` 方能將新模板物化至 `.agents/.yscb/templates/`。
- **`[!NOTE]`** `compiler.py` 的 `_clean_md_link_match` 會在 `_replace_in_code_span` 之後執行，將 `](`path`)` 清理為 `](path)`，因此 `_replace_in_code_span` 對無錨點 `__${uri}__` 返回 `` `{resolved}` `` 可同時滿足「行內代碼保留反引號」與「Markdown 連結無反引號」雙重需求。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[assets/templates/PXX-05_auto.md] ──(compile & release)──> [.agents/.yscb/templates/PXX-05_auto.md]
                                                                 │
[PlanStatusResolver.resolve_phase_file] <──(P0[1-5]-05_auto.md)──┴──> [PlanVerifier._verify_markdown_file (min_phase)]
       │                                                                     │
       ├──> [PlanScanner.execute_resume -> build_recovery_capsule]           └──> [PORTABILITY / BACKPROP WARN]
       └──> [PlanSearcher.search_drs / search_full_text -> cli.plan_search (--full / --json)]
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/assets/templates/PXX-05_auto.md` | New | 建立 `Phase XX~05` 自動連續推進綜合規格與任務模板 |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 註冊 `PXX-05_auto.md` 模板資產導出 |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | 為 `plan search` 註冊 `--full` 與 `--json` CLI 選項契約 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 修正 `_replace_in_code_span` 對無錨點 `__${uri}__` 保留外層反引號 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Modify | `resolve_phase_file` 支援 `P0[1-5]-05_auto.md` 動態區段匹配 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_verifier_specs.py` | Modify | `map_file_to_template` 映射 `PXX-05_auto.md`；`load_template_header_specs` 支援 `min_phase` 過濾 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 支援 `P0[1-5]-05_auto.md` 階段過濾與章節檢核，新增 `PORTABILITY` 與 `BACKPROP` 警告 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | `audit_plan_mtimes` 排除指向同一 `PXX-05_auto.md` 檔案之自我逆序比較 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/searcher.py` | Modify | 修復 Umbrella `sub_XX` DR 去重鍵與 `rel_path`，新增檔案角色權重與時間排序 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Modify | 新增 `build_recovery_capsule` 確定性恢復膠囊與已結案計畫 `plan archive` 提示 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | `plan_search` 支援 `--full`、`--json` 與來源路徑左側截斷 |
| `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md` | Modify | 更新 `/auto` 為讀取 `PXX-05_auto.md` 並產出單一 `P{XX}-05_auto.md` |
| `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md` | Modify | 補齊 `PXX-05_auto.md` 模板指針與 `/auto` 說明 |
| `ys_codebase/source/agents-workflow/assets/skills/continue/SKILL.md` | Modify | 補充無 `handoff.md` 時之確定性恢復膠囊說明 |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 更新並驗證 `[DN-AW-03]` 行內代碼反引號保留測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 擴充 `PXX-05_auto.md`、`PlanSearcher`、恢復膠囊與 `PORTABILITY`/`BACKPROP` 單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `load_template_header_specs` 以頂層 `## N.` 編號映射 Phase `N`（`1`~`5`），當檢核 `P0{start}-05_auto.md` 且 `start > 1` 時，自動略過 `current_h2_phase < start` 之 H2/H3 標題，無須建立多份冗餘模板即可原生支援任意起始階段。
- **[P02:DR-02]** `PlanSearcher._score_plan_and_file` 採用 `(is_active, date_key, role_weight, fname)` 四元組降序排列，確保活躍計畫、近期計畫以及高價值定案文件（`P00`、`RXX`、`P07`、`fast_track_plan`、`umbrella_overview`）排在過程檔之前。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# agents_workflow/plans/_verifier_specs.py
def load_template_header_specs(
    template_name: str,
    templates_dir: Optional[Path],
    min_phase: int = 1,
) -> List[Tuple[str, str]]: ...

# agents_workflow/plans/verifier.py
class PlanVerifier:
    def get_resolved_template_header_specs(
        self, template_name: str, min_phase: int = 1
    ) -> List[Tuple[str, str]]: ...

# agents_workflow/plans/scanner.py
class PlanScanner:
    def build_recovery_capsule(self, plan_dir: Path) -> str: ...

# agents_workflow/plans/searcher.py
class PlanSearcher:
    @staticmethod
    def _score_plan_and_file(
        plan_dir: Path, md_file: Path, is_active: bool
    ) -> Tuple[int, str, int, str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `build_recovery_capsule` 與 `_score_plan_and_file` 對檔案讀取失敗或非預期格式採取容錯降級（回傳空字串或預設權重 `0`），絕不拋出未捕獲之 `OSError` 阻斷 `plan status` 或 `plan search`。
  - `PORTABILITY` 與 `BACKPROP` 診斷均歸類為 `PlanSeverity.WARN`，提供明確 `[Fix Hint: ...]` 指引但不硬性阻斷 `plan verify` 退出碼。
- **階段決策紀錄**：`[P03:DR-01]` `execute_resume` 回傳字典新增 `"recovery_capsule": str` 鍵，保持既有鍵值 100% 向後相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - [?] 若 `P01-05_auto.md` 同時涵蓋 P01 與 P06 追溯鏈所需之 `FR-XX`/`EC-XX`/`NFR-XX`，`PlanVerifier._check_cross_file_and_traceability` 是否能正常提取？
  - [*] 因為 `p01_path = PlanStatusResolver.resolve_phase_file(target_dir, "P01")` 會直接解析至 `P01-05_auto.md`，且 `_extract_requirement_ids` 掃描全檔提取 `FR/EC/NFR` 編號並與 `P06_test_plan.md` 比對，無須額外特判即可 100% 完美運作。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 於 Phase 7 同步更新 `/auto` 產物 `PXX-05_auto.md` 與 `plan search` / `plan status` 說明 |
| **專題手冊** | `docs/agents-workflow/PLANS_AND_LIFECYCLE.md` | Modify | 於 Phase 7 同步更新 `PXX-05_auto.md` 動態區段規範与恢復膠囊機制 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 於 Phase 7 核對 `[DN-AW-03]` 實作對齊並登記 `PXX-05_auto.md` 設計決策 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 已同步更新 `status.py`, `scanner.py`, `searcher.py`, `_verifier_specs.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 記錄本次變更摘要 |

- **決策定稿**：**[P04:DR-01]** 本計畫自身即採用 `P01-05_auto.md` 進行 Dogfooding 實機驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `PXX-05_auto.md` 模板並註冊於 `contributes/agents-workflow.json` 與更新 `auto`/`development-sop`/`continue` 技能手冊
- [x] **TASK-02**：實作 `status.py`、`verifier.py`、`_verifier_specs.py` 與 `session_trace.py` 對 `P0[1-5]-05_auto.md`、`PORTABILITY` 與 `BACKPROP` 之支援
- [x] **TASK-03**：實作 `searcher.py`、`scanner.py`、`cli.py` 與 `contributes/core.json` 之檢索去重排序、`--full`/`--json`、恢復膠囊與歸檔提醒，以及 `compiler.py` 反引號保留修復
- [x] **TASK-04**：於 `test_compiler.py` 與 `test_plans_toolchain.py` 擴充單元測試與邊界測試並通過沙盒驗證
- [x] **TASK-DOC**：同步更新微觀代碼 Docstrings（`docs/agents-workflow/` 與 `CHANGELOG.md` 將於 Phase 7 結案時對齊）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

