# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：主流 AI 開發平台 release_target 矩陣擴充、同路徑並聯渲染告警與宣告式環境嗅探  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 同實體路徑多 `release_target` 並聯去重渲染 (`Union Rendering`) | 當多個已啟用之 `release_target` 指向相同實體輸出路徑（如 `project://AGENTS.md` 或 `project://.agents/skills/`）時，`ReleasePublisher` 按目標實體路徑聚合 Target 群組，對不同之 `__%{agent_tool.*}__` 宿主專有名詞與 `__#{...}__` 路由超連結以 `" / "` 執行確定性去重並聯渲染，杜絕後執行 Target 無聲覆寫前一個 Target 內容 | P0 | [P00:DR-01] |
| **FR-02** | 同實體路徑多 `release_target` 物化碰撞告警 (`[WARNING]`) | 於 `ReleasePublisher.release` 物化期間，若偵測到 $\ge 2$ 個啟用之 Target 共用同一實體輸出路徑（如 `AGENTS.md` 或 `.agents/skills/`），除了完成並聯渲染外，於終端輸出醒目 `[WARNING]`，列出共用路徑與對應 Target 名稱，並提示開發者可於 `config/agents-workflow/config.local.json` 設定個人專屬 `"release_targets"` 覆蓋 | P0 | [P00:DR-01] |
| **FR-03** | 子目錄 `agents_md` 相對連結基準路徑對齊 (`copilot` 等平台支援) | 當 Target 之 `agents_md` 位於專案子目錄（如 `copilot` 之 `project://.github/copilot-instructions.md`）時，`ReleasePublisher` 在執行 Stage 2 URI 展開時以 `os.path.dirname(agents_md_abs)` 為 `cur_doc_dir`，確保 `.github/copilot-instructions.md` 內的技能路由相對連結精準指向 `./skills/...` | P0 | [P00:DR-03] |
| **FR-04** | 執行期 CLI 環境變數嗅探與方言對照宣告化 (`TODO-06`) | 將 `core/locale.py` 中 `detect_active_host_dialect` 硬編碼之環境變數前綴對照表正規化為宣告式規則（支援由 `contributes` 或結構化平台規則表驅動），使新擴充之 Target 均可透過宣告式環境變數規則自動嗅探並映射至對應或通用方言詞庫 | P1 | [P00:DR-02] |
| **FR-05** | 8 大預設 `release_target` 矩陣擴充與「外殼 vs. 模型」選型文檔同步 | 於 `agents-workflow/contributes/agents-workflow.json` 完整提供 8 大預設 Target（`antigravity`、`claude`、`codex`、`cursor`、`copilot`、`windsurf`、`opencode`、`roo`），並同步更新 `docs/agents-workflow/{README.md,user_guide.md}` 說明客戶端外殼選型與 `config.local.json` 覆蓋指引 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 同時啟用 `antigravity`（`.agents/skills/`）與 `cursor`（`.cursor/skills/`），兩者 `agents_md` 均為 `project://AGENTS.md` | `AGENTS.md` 的技能路由連結在 Stage 2 渲染時，針對同一連結文字或緊鄰路徑輸出並聯路徑或保留雙方可達連結，同時輸出 `[WARNING]` 提示 `AGENTS.md` 由 `antigravity, cursor` 共用 |
| **EC-02** | 同時啟用 `antigravity` 與 `codex`，兩者共用 `.agents/skills/` 且專有名詞相同與相異並存 | 相同專有名詞自動去重為單一詞彙（不重複輸出 `A / A`），相異專有名詞輸出為 `A / B`（如 `read_file / exec_command`） |
| **EC-03** | 停用 (`release-target --remove`) 其中一個共用 `AGENTS.md` 的 Target，但另一個共用 `AGENTS.md` 的 Target 仍處於啟用狀態 | `AGENTS.md` 仍屬活躍啟用 Target 之受管產物，不得從 `AGENTS.md` 執行 `_soft_unmerge_agents_text` 剝離託管區塊，僅重新以剩餘活躍 Target 渲染更新 |
| **EC-04** | 新擴充之 Target（如 `cursor`、`windsurf`、`copilot`、`opencode`、`roo`）未單獨定義全套專有名詞 JSON 檔案 | 自動安全回退至通用/預設工具詞庫（如 `antigravity` / `en` 基礎詞庫），絕不拋出 `FileNotFoundError` 或留下未替換之 `__%{...}__` |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與冪等性 | 單一或多重 Target 發布時，Stage 0/Stage 4 Diff 短路機制維持 100% 冪等，第二次無變更執行 `release` 時 `Written files: 0` |
| **NFR-02** | 向後相容性 | 既有單一 `antigravity`、`claude`、`codex` Target 的物化內容與路徑 100% 向下相容 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 依據 `[DN-AW-06]`，清理陳舊 `agents_md` 時必須先執行 `_soft_unmerge_agents_text`，且僅在無任何活躍 Target 指向該 `agents_md` 時才可剝離。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[contributes/agents-workflow.json (8 release_targets)] + [core/locale.py (Declarative Dialect Rules)]
   │
   ▼
[ArtifactCompiler.resolve_stage2_uri(content, cur_doc_dir, target_names: Union[str, List[str]])]
   ├── __%{agent_tool.*}__: 對 target_names 逐一查詢 get_host_noun，按序去重並以 " / " 串接
   └── __#{uri}__: 若 target_names 對同一導出資產有不同相對路徑，按序去重生成並聯連結或以 cur_doc_dir (如 .github/) 為基準計算
   │
   ▼
[ReleasePublisher.release()]
   ├── 1. 收集所有活躍 Target 之檔案映射，偵測共用實體路徑 (shared dest_path -> List[target_name])
   ├── 2. 若存在 len(sharing_targets) >= 2，輸出 [WARNING] 提示考慮於 config.local.json 覆蓋
   └── 3. 針對每個實體輸出路徑，傳入對應之 sharing_targets 執行並聯 Stage 2 渲染並原子寫入
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/locale.py` | Modify | 將 `detect_active_host_dialect` 硬編碼環境變數對照表重構為宣告式規則（支援內建與 `contributes` 擴充），並支援新 Target 名稱之安全詞庫回退 |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 擴充 `cursor`、`copilot`、`windsurf`、`opencode`、`roo` 共 8 大預設 `release_target` |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `resolve_stage2_uri` 支援傳入 `target_name: Union[str, List[str]]`（或多重 `target_contexts`）以進行 `__%{...}__` 專有名詞與跨 Target 路由去重並聯渲染 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 支援同實體路徑多 Target 聚合渲染、子目錄 `agents_md` 之 `cur_doc_dir` 對齊，以及共用路徑時輸出 `[WARNING]` 提示 `config.local.json` 覆蓋 |
| `ys_codebase/source/agents-workflow/tests/test_targets.py` | Modify | 新增 8 大預設 Target、`.github/copilot-instructions.md` 子目錄相對連結、同路徑多 Target 並聯渲染與 `[WARNING]` 輸出測試 |
| `ys_codebase/source/core/tests/test_locale.py` | Modify | 新增宣告式環境變數嗅探與新平台回退測試 |
| `docs/agents-workflow/README.md` | Modify | 更新 8 大預設 `release_target` 清單 |
| `docs/agents-workflow/user_guide.md` | Modify | 更新 §2.4 多平台 Release Targets 矩陣、「客戶端外殼 vs. 底層模型」選型指引與 `config.local.json` 覆蓋說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** **按實體目標路徑聚合 Target 群組 (`Path-Centric Target Grouping`)**：`ReleasePublisher` 在建構期望物化清單時，記錄每個 `dest_abs_path` 被哪些活躍 Target 共同投影 (`path_owners: Dict[str, List[str]]`)。寫入前對 `len(owners) > 1` 的路徑匯總發出一次清晰 `[WARNING]`，並將 `owners` 傳入 `compiler.resolve_stage2_uri` 完成並聯去重渲染。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/locale.py
DEFAULT_DIALECT_DETECTION_RULES: List[Dict[str, Any]]
def get_dialect_detection_rules() -> List[Dict[str, Any]]: ...
def detect_active_host_dialect(env: Optional[Mapping[str, str]] = None) -> str: ...

# ys_codebase/source/agents-workflow/agents_workflow/compiler.py
class ArtifactCompiler:
    def resolve_stage2_uri(
        self,
        content: str,
        cur_doc_dir: str,
        target_map: Optional[Dict[str, str]] = None,
        target_name: Optional[Union[str, List[str]]] = None,
        extra_target_maps: Optional[List[Dict[str, str]]] = None,
    ) -> str: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：未知或未單獨配置詞庫之 `target_name` 自動回退至預設詞庫 (`antigravity` / `en`)，不拋出例外。
- **階段決策紀錄**：`[P03:DR-01]` `resolve_stage2_uri` 向下相容單一 `str` 與 `List[str]` 之 `target_name`，並支援 `extra_target_maps` 處理 `AGENTS.md` 被不同 `skill` 目錄之 Target（如 `.agents/skills` 與 `.cursor/skills`）共用時的路徑並聯。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：當 `antigravity` 與 `cursor` 同時啟用時，`AGENTS.md` 中的 `[development-sop](__#{module://.../SKILL.md}__)` 如何並聯？解法：當 `extra_target_maps` 提供額外映射且解析出的相對路徑不同時，自動將 `[Label](path1)` 擴展為 `[Label](path1) ([target2](path2))`（若路徑相同如 `antigravity` 與 `codex` 皆為 `.agents/skills/...` 則去重維持單一 `[Label](path1)`）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新 §4 支援 8 大預設 `release_target` |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 更新 §2.4 8 大平台矩陣表、「外殼 vs. 模型」選型指引與 `config.local.json` 覆蓋說明 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 更新同路徑多 Target 並聯渲染與子目錄 `agents_md` 基準對齊說明 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `compiler.py`, `publisher.py`, `locale.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_03` 發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_03` 規格與實作拆解無誤，進入實作階段。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `contributes/agents-workflow.json` 8 大預設 `release_target`，並實作 `compiler.py` 與 `publisher.py` 之子目錄 `agents_md` 基準對齊、同路徑多 Target 並聯去重渲染與 `[WARNING]` 告警
- [x] **TASK-02**：重構 `core/locale.py` 為宣告式環境變數嗅探規則（支援 8 大平台與 `contributes` 擴充）
- [x] **TASK-03**：編寫 `test_targets.py` 與 `test_locale.py` 單元與邊界測試並通過全套回歸驗證
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差（實作 100% 遵循 P00~P04 規格契約） | - |
