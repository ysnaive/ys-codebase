---
target: "Agents-Workflow"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/agents-workflow/agents_workflow/compiler.py"
  - "yscb://source/agents-workflow/agents_workflow/publisher.py"
  - "yscb://source/agents-workflow/agents_workflow/initializer.py"
  - "yscb://source/agents-workflow/agents_workflow/roadmap.py"
  - "yscb://source/agents-workflow/config.project.json"
related_docs:
  - "./README.md"
  - "./FACTORY_PIPELINE.md"
  - "./user_guide.md"
last_updated: "2026-10-25"
---

# 設計決策與工程妥協 (Design Notes)

本文件專注記錄 `agents-workflow` 模組在實作中採取的**工程妥協、反直覺設計與防坑邊界（知識庫維度 ⑤）**。常規架構與操作指引請參閱 [README.md](./README.md)、[FACTORY_PIPELINE.md](./FACTORY_PIPELINE.md) 與 [user_guide.md](./user_guide.md)。

---

## 登錄索引表

| 編號 | 原編號對照 | 決策 / 妥協與防坑主題 | 影響範圍 | 狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **[DN-AW-01]** | 原 `DN-AW-02` + `DN-AW-04` | 5-Step 編譯狀態機防自指死鎖與 `make_purge_regex` 整行空白換行吞噬 | 工廠編譯器 (`compiler.py`) | `Active` |
| **[DN-AW-02]** | 原 `DN-AW-05` | `config.project.json` 靜態模板剛性保持 `"!undefined"` 與預設值延遲物化 | 組態治理、`WorkflowInitializer` | `Active` |
| **[DN-AW-03]** | 原 `DN-AW-08` + `DN-AW-13` | Stage 2 `EXACT_REGEX` 反引號剝除 vs 行內保留、`FT-14` 裸標籤契約與沙盒 URI 回退 | 工廠編譯器 (`compiler.py`) | `Active` |
| **[DN-AW-04]** | 原 `DN-AW-10` + `DN-AW-13` | JIT 變更偵測零外部依賴與目錄型資產（Skill 資料夾）遞迴排序聚合 SHA-1 | 發布引擎 (`publisher.py`) | `Active` |
| **[DN-AW-05]** | 原 `DN-AW-14` | `compiler.py` 對舊版 `type: "workflow"` 自動無縫轉譯為 `"skill"` 與遺留目錄清理 | 工廠編譯器、發布引擎 | `Active` |
| **[DN-AW-06]** | 原 `DN-AW-11` + `DN-AW-16` | `AGENTS.md` / `CLAUDE.md` 單向覆寫防殭屍技能復活與移除 Target 軟剝離保護 | 發布引擎 (`publisher.py`) | `Active` |
| **[DN-AW-07]** | 原規劃 `DN-AW-17` | Plans 工具鏈標頭解析 SSOT、時序防呆與動態佔位符正則推導設計 | Plans 工具鏈 (`status.py`, `scanner.py`, `archiver.py`, `verifier.py`) | `Active` |
| **[DN-AW-08]** | 新增 | 模型紀錄規則：唯一來源為平台宣告、嚴禁由檔案反推、不確定填 `Unknown`、事件粒度記入 changelog | 規範資產 (`AgentsStandards.md`)、標頭模板、`changelog.md` 模板 | `Active`（待下游驗證） |
| **[DN-AW-09]** | 新增 | 來源資產換行符 LF 正規化與物化清單 `cache://` 本地隔離防 Git 污染 | 發布引擎 (`publisher.py`) | `Active` |
| **[DN-AW-10]** | 新增 | ACI 四步執行管線時序、伴隨檔模型防回溯與 `P01` 刪除線/代碼塊預過濾設計 | Plans 工具鏈 (`verifier.py`, `scanner.py`, `status.py`) | `Active` |
| **[DN-AW-11]** | 新增 | 雙層儲備消耗 (`Consume-on-Promote`)、`TODO.md` 單調遞增編號計數器與 `ORIGIN_SEED_FILES` 種子白名單防坑設計 | 儲備與計畫工具鏈 (`roadmap.py`, `status.py`, `scanner.py`, `verifier.py`) | `Active` |
| **[DN-AW-12]** | 新增 | 唯讀 Subagent 零劇透盲審傳址、純靜態禁跑測、Single-Writer 鐵律與多路線圖合流追加合併防坑設計 | 技能資產 (`research`, `discuss`, `phase_06`, `phase_07`, `roadmap.py`) | `Active` |
| **[DN-AW-13]** | 新增 | 跨模組多捐贈者導覽錨點 (`HOW_TO_*_MODULES`)、兩階段漸進式隨包手冊調度與跨模組 `_resolve_source_path` Sibling Fallback 防坑設計 | 工廠編譯器 (`compiler.py`)、教練技能 (`how-to-config-yscb`, `how-to-yscb`) | `Active` |
| **[DN-AW-14]** | 新增 | `/skill-creator` 三軌擴充防膨脹、`AGENTS_SKILL_ROUTING` 表格列結構隔離與教學範例 Fenced Code Block 編譯器正則保護 | 技能資產 (`skill-creator/SKILL.md`, `references/extension-guide.md`) | `Active` |

---

### [DN-AW-01] (原 DN-AW-02 + DN-AW-04) 5-Step 編譯狀態機防自指死鎖與 `make_purge_regex` 整行空白換行吞噬
- **工程背景與坑點**：
  1. 當注入片段本身包含同名 Token，或多個模組對同一錨點連續執行 `below` / `above` 追加時，若在當輪直接對注入內容遞迴正則替換，極易引發無窮自指死鎖或殘留未解算標籤。
  2. 錨點標籤行（如 `__@{TOKEN_NAME}__`）在解算完畢後若僅單純替換掉標籤字串本身，會導致生成出的 Markdown 文件在原錨點位置遺留多餘的空白縮排行與空行，破壞 Markdown 表格或列表結構。
- **妥協與防禦設計**：
  1. **單輪字面量展開 + Step 3 從 Step 1 快照挖空**：5-Step 狀態機在 Step 1 先擷取當輪現存 Token 快照，Step 2 執行注入時將新內容視為原子字面量（禁止本輪自指展開，留待下一輪 Iteration 處理），並在 Step 3 嚴格依據 Step 1 快照精準挖空已處理之錨點標籤，徹底保證多輪展開的收斂性。
  2. **吞噬整行空白與換行 (`make_purge_regex`)**：標籤抹除正則強制採用 `r"([ \t]*__@\{\s*" + re.escape(token_name) + r"\s*\}__[ \t]*\r?\n?)"`，在抹除標籤時一併吞噬行首縮排空白與行尾換行符。

> [!CAUTION]
> 切勿將 `make_purge_regex` 簡化為僅匹配 `__@{...}__` 本身，否則所有包含未注入插槽的模板與 Skill 產物都會殘留空白斷行，導致 Markdown 表格斷裂與排版劣化；亦嚴禁移除 Step 1 快照機制改為原地遞迴替換，否則將失去自指死鎖防護。

---

### [DN-AW-02] (原 DN-AW-05) `config.project.json` 靜態模板剛性保持 `"!undefined"` 與預設值延遲物化
- **工程背景與坑點**：
  若為求方便而將預設推薦路徑（如 `project://plans`、`project://docs`）直接寫死在模組源碼的 `config.project.json` 靜態模板中，會導致任何尚未初始化的新專案在載入模組時即被隱式綁定預設路徑，破壞微內核「未配置即 `!undefined`」的零臆測與延遲物化契約。
- **妥協與防禦設計**：
  1. 模組內的 `config.project.json` 靜態模板中，`paths` 下所有欄位（`plans`, `archived`, `docs`, `roadmap`）必須嚴格保持 `"!undefined"`。
  2. 所有推薦預設路徑統一封裝於 `WorkflowInitializer` (`initializer.py`) 內部，僅當使用者或 Agent 顯式執行 `agents-workflow init --default` 時，才由初始化器原子寫入專案組態並刷新 Core URI 快取。

> [!WARNING]
> 嚴禁在模組源碼的 `config.project.json` 中將 `"!undefined"` 改為具體預設路徑字串，否則將破壞微內核未初始化偵測契約與對應的沙盒隔離測試。

---

### [DN-AW-03] (原 DN-AW-08 + DN-AW-13) Stage 2 `EXACT_REGEX` 反引號剝除 vs 行內保留、`FT-14` 裸標籤契約與沙盒 URI 回退
- **工程背景與坑點**：
  1. Markdown 連結若寫為 `` [Link](`__#{uri}__`) ``，若 Stage 2 對所有匹配 `CODE_SPAN_REGEX` 的片段無差別包回外層反引號，會產生 `[Link](`../path.md`)` 導致 CommonMark 超連結失效；反之，若對命令列 `` `python __${uri}__ run` `` 剝除反引號，則會破壞行內代碼塊格式。
  2. 在單元測試或未執行 `init` 的空沙盒環境中，`workflow.docs://` 等協議處於 `!undefined` 狀態，若直接調用 `core.uri.resolve()` 並任由例外拋出，將導致 Stage 2 整批編譯崩潰。
- **妥協與防禦設計**：
  1. **Standalone vs Inline 二分法**：在 `compiler.resolve_stage2_uri` 中以 `EXACT_REGEX`（`LOCAL_URI_EXACT_REGEX` / `PROJECT_URI_EXACT_REGEX`）識別「整個反引號內僅含單一佔位符」的獨立路徑，解算後**直接剝除外層反引號**；若反引號內含有前後綴指令文字（Inline），則僅替換內部佔位符並**保留外層反引號**。
  2. **`FT-14` 裸標籤原樣保留契約**：任何未被反引號包裹的裸露佔位符（由 `UNENCLOSED_TAG_REGEX` 偵測）一律不予展開，原樣保留並輸出 `[compiler:warning]` 警示。
  3. **未配置沙盒 URI 安全回退**：當 Stage 2 解析 `workflow.*://` 遭遇未定義或無法解析的沙盒環境時，捕獲例外並安全降級回退為專案相對路徑，防止編譯管線崩潰。

> [!CAUTION]
> 嚴禁移除 `UNENCLOSED_TAG_REGEX` 裸標籤攔截或將裸露佔位符納入自動替換，否則文檔中作為教學說明展示的裸語法字串會被意外竄改（違反 `FT-14` 合約）；修改 `resolve_stage2_uri` 時亦必須維持 Standalone 剝除反引號與沙盒回退保護。

---

### [DN-AW-04] (原 DN-AW-10 + DN-AW-13) JIT 變更偵測零外部依賴與目錄型資產（Skill 資料夾）遞迴排序聚合 SHA-1
- **工程背景與坑點**：
  1. CLI 每次啟動前的 `ensure_jit_release` 若引入外部 `watchdog` 等檔案監控依賴，會破壞 YSCB 核心模組「零外部 pip 依賴」的微環境純淨性；而每次全量重算檔案雜湊則會造成冗餘 I/O。
  2. 進入純 Skill 架構後，導出資產常為包含 `SKILL.md` 與 `references/` 子目錄的**資料夾**。若 `_get_source_file_sha1` 直接對資產路徑呼叫 `open()`，遇到目錄型 Skill 將拋出 `IsADirectoryError` 或被迫返回固定偽雜湊，導致每次 CLI 執行都誤判為 Dirty 而重跑完整發布。
- **妥協與防禦設計**：
  1. **零外部依賴 Stat-First 快取**：嚴禁引入 `watchdog`，完全基於標準庫 `os.stat` 之 `(st_mtime_ns, st_size)` 搭配 `source_sha1_cache.json` 進行極速變更偵測。
  2. **目錄遞迴排序聚合 SHA-1 (`_get_source_file_sha1`)**：當 `_get_source_file_sha1` 偵測目標路徑為目錄時，自動遞迴並以確定性字典序排序遍歷目錄下所有子檔案，將各檔案之相對路徑與內容 SHA-1 聚合計算出單一目錄級 SHA-1 指紋。

> [!CAUTION]
> 嚴禁在 `manifest.json` 重新引入 `watchdog` 等外部套件；修改 `_get_source_file_sha1` 時必須保留對 `os.path.isdir()` 的遞迴排序聚合邏輯，否則任何對 Skill 內部 `references/*.md` 的修改都將無法觸發 JIT 自動同步（或引發 `IsADirectoryError` 崩潰）。

---

### [DN-AW-05] (原 DN-AW-14) `compiler.py` 對舊版 `type: "workflow"` 自動無縫轉譯為 `"skill"` 與遺留目錄清理
- **工程背景與坑點**：
  雖然 `agents-workflow` 已全面廢除 `workflow` 資產分類並統一收斂為 `skill`（`_format.json` Schema 僅允許 `standard | template | skill`），但外部或下游專案的舊版模組 `contribute.json` 與歷史測試案例可能仍宣告 `"type": "workflow"`，且升級前的專案工作區可能殘留舊版 `.agents/workflows/` 或 `.claude/commands/` 實體目錄。
- **妥協與防禦設計**：
  1. **載入期無縫轉譯**：`compiler.py` 在搜集 `export` 資產時，若偵測到 `type == "workflow"`，自動在記憶體中將其無縫轉譯為 `type = "skill"` 並補齊標準 Skill 屬性，確保下游舊版配置零報錯平滑相容。
  2. **遺留目錄自動清理**：`publisher.py` 在執行原子發布 Pruning 階段時，自動探測並物理清除歷史遺留之 `.agents/workflows/` 與 `.claude/commands/` 目錄。

> [!WARNING]
> 切勿因為 `_format.json` 已移除 `"workflow"` 列舉，就連帶刪除 `compiler.py` 中將 `"workflow"` 自動轉譯為 `"skill"` 的相容分支，否則未同步升級之外部模組與向後相容測試將立即中斷。

---

### [DN-AW-06] (原 DN-AW-11 + DN-AW-16) `AGENTS.md` / `CLAUDE.md` 單向覆寫防殭屍技能復活與移除 Target 軟剝離保護
- **工程背景與坑點**：
  1. **啟用時合併坑點（殭屍技能復活）**：若 `_soft_merge_agents_text` 嘗試用「啟發式文字比對」去猜測並保留 `<!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->` 區塊內的自訂表格列，在數學上無法區分「使用者手動新增的列」與「官方新版已廢棄除役的舊技能列」，必然導致已被官方刪除的舊技能永遠殘留復活。
  2. **停用時刪除坑點（誤刪使用者自訂規範）**：當使用者透過 `release-target --remove` 停用某個 Target 時，`AGENTS.md` 或 `CLAUDE.md` 會進入待移除清單 `files_to_remove`。若直接呼叫 `os.remove()`，會將開發者在託管區塊外部撰寫的專案特化規範一併物理抹除，造成嚴重資料遺失。
- **妥協與防禦設計**：
  1. **託管區塊純粹單向覆寫 (`_soft_merge_agents_text`)**：對於 `<!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->` 內部區塊，強制執行 100% 中央標準庫單向覆寫（專案特化技能路由一律改由 `config/agents-workflow/contribute.json` 注入 `AGENTS_SKILL_ROUTING` 錨點），區塊外部的使用者自訂章節則 100% 原樣保留。
  2. **停用時非破壞性軟剝離 (`_soft_unmerge_agents_text`)**：移除 Target 清理 `agents_md` 檔案時，強制先執行 `_soft_unmerge_agents_text` 剝離託管區塊。若剝離後仍有非預設樣板的使用者自訂文字，僅將自訂文字寫回檔案並保留於磁碟；唯有剝離後為空或僅剩未修改之預設佔位樣板時，才允許呼叫 `os.remove()`。

> [!CAUTION]
> 嚴禁在 `_soft_merge_agents_text` 的託管區塊內加入啟發式行級 Diff 保留邏輯（必引發殭屍技能殘留）；更**絕對禁止**在 `publisher.py` 清理陳舊 `agents_md` 檔案時繞過 `_soft_unmerge_agents_text` 直接調用 `os.remove()`，否則將直接摧毀開發者在根目錄 `AGENTS.md` / `CLAUDE.md` 中維護的專案自訂規範！

---

### [DN-AW-07] (原規劃 DN-AW-17) Plans 工具鏈標頭解析 SSOT、時序防呆與動態佔位符正則推導設計
- **工程背景與坑點**：
  1. 早期計畫工具鏈使用正文子字串比對 (`"Completed" in content`) 判定文件狀態，導致當使用者在需求、日誌或討論中提及 "Completed" 時引發嚴重的誤判（如提前推進 Phase、跳過守門或誤放行歸檔）。
  2. 靜態佔位符清單無法涵蓋模板中各種自訂佔位符（如 `[調研主題/所屬功能]`），導致殘留模板字串漏報。
  3. `archiver.py` 在清理暫時性 `handoff.md` 時若位於目標衝突檢查之前，在發生目標目錄已存在同名計畫時會提前抹除交接快照，造成使用者上下文永久遺失。
- **妥協與防禦設計**：
  1. **標頭 Blockquote 範圍約束 (SSOT)**：`PlanStatusResolver` 嚴格限制僅在 Markdown 前 35 行內的引用區塊 (`> key: val`) 提取狀態標頭，並進行正規化，正文任何處出現 "Completed" 100% 免疫。
  2. **模板動態佔位符推導**：`PlanVerifier.get_all_placeholder_patterns` 動態讀取模板檔案前 35 行之 Blockquote，提取包含 `|` 或中文字元的方括號模式並以 `re.escape` 安全轉譯，與靜態正則合併。
  3. **歸檔操作時序防禦**：`PlanArchiver` 強制將目標目錄衝突檢查 (`dest_dir.exists()`) 前置於任何檔案刪除動作，確保在發生目的地衝突時 `handoff.md` 100% 受到物理保護。

> [!CAUTION]
> 嚴禁改回正文全文字串匹配判定狀態；歸檔時序嚴禁將 `unlink()` 移至目標衝突檢查之前。

---

### [DN-AW-08] 模型紀錄規則：唯一來源為平台宣告，嚴禁由檔案反推
- **工程背景與坑點**：
  1. LLM 無法由權重得知自身名稱，僅依 context 內文字宣稱身分；context 混有他模型名稱時會答錯。
  2. 實戰事故（本機對話 `84facb53`）：模型切換為新模型後，因規則要求「與該檔建檔模型比對」而去讀計畫檔標頭，將檔案內的他模型名稱當成自身名稱，連續 5 次誤報，並因 context 壓縮摘要被固化。
  3. 原「內文尾行 `> {model}`」無法定位修訂範圍，亦破壞 Markdown 表格結構。
- **妥協與防禦設計**：
  1. **單一來源**：`> 模型：` 僅採當輪平台明確宣告之名稱，原樣照抄（含推理強度）；無法確認填 `Unknown`，不猜測。
  2. **禁止反推與比對**：不得從既有計畫檔、摘要或先前回覆推得模型，因此規則本身不再要求讀取他檔標頭。
  3. **事件粒度歸屬**：接手既有計畫時不改該檔 `> 模型：`，改於 `changelog.md` 新增含「模型」欄之事件列。
  4. **驗證器邊界**：`PlanVerifier` 僅檢查 `模型` 欄位存在，不驗證真偽；真偽無法由工具確認，需靠來源約束。
- **已知限制**：本期不含來源標記、開發者宣告與平台探針；對話壓縮摘要仍可能遺失宣告原文，待下游實戰回饋後再評估。

> [!CAUTION]
> 嚴禁恢復「由檔案標頭比對或推導當前模型」之規則；嚴禁驗證器對模型名稱做白名單校驗。

---

### [DN-AW-09] 來源資產換行符 LF 正規化與物化清單 `cache://` 本地隔離防 Git 污染

- **工程背景與坑點**：
  跨平台協作情境（Linux 與 Windows 交替開發）下：
  1. Windows Git 預設 `core.autocrlf=true` 會將檔案檢出為 CRLF，導致 `_get_source_file_sha1` 計算出的 SHA-1 與 Linux (LF) 不一致，造成 `fingerprint` 與 `combined_fingerprint` 頻繁漂移。
  2. 原先 Project 軌之發布狀態記錄於 `storage://agents-workflow/release_manifest.json`，而 `storage/` 屬版本庫追蹤範圍；一旦 fingerprint 漂移或觸發同步，自動改寫 `updated_at` 時間戳記，造成 Git 工作區非自願性陷入 Dirty（ping-pong diff）。
- **妥協與防禦設計**：
  1. **UTF-8 文字 CRLF $\to$ LF 正規化**：`_get_source_file_sha1` 讀取文字內容時統一將 `\r\n` 轉換為 `\n` 後再計算 SHA-1；遇到非 UTF-8 二進位檔案時安全降級維持 raw bytes 雜湊。
  2. **物化清單本地隔離 (`cache://`)**：將 Project 軌之狀態檔遷移至 `cache://agents-workflow/project_release_manifest.json`（已在 `.gitignore` 範圍內），並在發布階段自動遷移且物理刪除舊版 `storage://` 下的遺留檔案與目錄。
  3. **不以忽略規則掩蓋**：刻意不在 `.gitignore` 增列 `storage://` 下之任何規則（`storage://` 為受追蹤空間）；根治手段唯一為「運行期資產不寫入受追蹤空間」。升級後舊檔被刪除會產生一次性 `deleted` 差異，需提交一次。

> [!CAUTION]
> 計算來源資產 SHA-1 時嚴禁未經換行符正規化直接雜湊；嚴禁將運行期動態物化狀態清單寫入 `storage://` 等 Git 追蹤目錄。

---

### [DN-AW-10] ACI 四步執行管線時序、伴隨檔模型防回溯與 `P01` 刪除線/代碼塊預過濾設計

- **工程背景與坑點**：
  1. 若 `plan verify --phase P02 --log "..."` 在檢核主體檔 `P02_architecture_plan.md` 之前就無條件先建立伴隨檔 `P06_test_plan.md (Draft)` 或寫入 `changelog.md`，當 Agent 寫出的 `P02` 本身仍有未替換佔位符或語法缺失（`FAIL`）時，會在不合規的目錄留下半成品伴隨檔與錯誤的成功日誌；且當 Agent 修復後重跑指令時，若無防重入保護，會在 `changelog.md` 產生重複紀錄列。
  2. 自動初始化伴隨檔（`changelog.md` 或 `P06_test_plan.md`）時，若為了填充 `> 模型：` 而跨階段去搜尋目錄下更早期的 `P00_discuss.md` 標頭，會直接違反 `[DN-AW-08]` 模型紀錄「嚴禁跨檔回推舊階段模型」的鐵律。
  3. 在 `P01_requirements_spec.md` 中，開發者可能透過 Markdown 刪除線（如 `~~**FR-09**~~`）標記作廢需求，或在代碼塊/註解中舉例說明 `FR-99`；若直接以全文本正則提取需求 ID，會導致已作廢需求被誤判為未映射至 `P06` 的孤兒需求。
- **妥協與防禦設計**：
  1. **嚴格四步管線與首筆冪等防重入**：`PlanVerifier.verify_plan` 強制依序執行「Step 1 主體檔合規檢核 $\to$ Step 2 僅在 Step 1 為 0 `FAIL` 時自癒生成伴隨檔 $\to$ Step 3 雙檔協同與追溯差集檢核 $\to$ Step 4 僅在全數 `PASS` 時追加 `changelog.md`（並比對表格第一筆資料列之 `(類型, 摘要)` 實現冪等跳過）」。
  2. **伴隨檔模型來源單向約束 (`_resolve_companion_model`)**：僅允許取用 CLI 顯式傳入之 `--model` 或當下同階段主體檔（如 `--phase P02` 時僅讀 `P02_architecture_plan.md`）之標頭模型，否則一律填 `Unknown`，絕不回溯讀取前序階段檔案。
  3. **三層雜訊預剝除 (`extract_requirement_ids`)**：提取 `P01` 需求 ID 集合前，依序剝除 Fenced Code Blocks (`` ```[\s\S]*?``` ``)、HTML 註解 (`<!--[\s\S]*?-->`) 與 Markdown 刪除線 (`~~[\s\S]*?~~`)。

> [!CAUTION]
> 嚴禁將 `append_changelog_entry` 或 `_auto_heal_companions` 移至 Step 1 主體檔合規判定之前；嚴禁在 `_resolve_companion_model` 中加入回退搜尋 `P00_discuss.md` 等前序階段檔案之邏輯。

---

### [DN-AW-11] 雙層儲備消耗 (`Consume-on-Promote`)、`TODO.md` 單調遞增編號計數器與 `ORIGIN_SEED_FILES` 種子白名單防坑設計

- **工程背景與坑點**：
  1. **殭屍路線圖與歷史模型污染**：過去 `plans/roadmap/{topic}.md` 在立項後常留在原目錄，或僅手動修改狀態為 `Promoted`，導致儲備庫長期堆積已立項的殭屍檔案；而在執行 `roadmap promote` 移入計畫目錄並自動建立 `changelog.md` 時，若直接拿 `roadmap.md` 標頭裡數週前舊對話寫入的 `> 模型：` 來初始化當下 `changelog.md`，會違反 `[DN-AW-08]` 模型紀錄鐵律。
  2. **`TODO.md` 提取後之編號碰撞 (`Pop` Collision)**：`todo promote` 執行原子提取（Pop）會將已立項之 `TODO-XXX` 從 `plans/roadmap/TODO.md` 表格移除。若 `todo add` 僅依「目前表格內現存最大編號 + 1」計算新編號，當最後一筆（甚至全部）條目被 Pop 移除後，下一筆新增的待辦就會重複分配已被歷史計畫 `todo.md` 佔用的舊編號。
  3. **計畫內種子檔 (`roadmap.md` / `todo.md`) 誤觸 `PlanVerifier` 與 `PlanStatusResolver` 攔截**：當 `roadmap.md` 或 `todo.md` 被置入活躍計畫目錄（或 `sub_XX` 子計畫目錄）作為起源種子檔時：
     - 其標頭日期欄位可能為 `> 建立日期：` 或 `> 歸檔日期：`，狀態可能為 `Backlog` / `Ready` / `Seeded`。
     - 若放入 `sub_XX` 子目錄，種子檔本身並無 `> 所屬主計畫：` 標頭（因其為立項前儲備資產），若 `PlanVerifier` 對子目錄下所有 `.md` 無差別強制要求 `> 所屬主計畫：`，將導致 `FAIL` 误報。
     - `roadmap.md` 內文可能包含演進藍圖之參考勾選框 `- [ ]`，若因其狀態而觸發 `Completed` 未勾選阻斷，亦會造成假陽性。
- **妥協與防禦設計**：
  1. **物理移轉 (`Consume-on-Promote`) 與伴隨模型隔離**：`RoadmapManager.promote_roadmap` 強制使用 `shutil.move` 將 `plans/roadmap/{topic}.md` 物理移入目標計畫目錄並重命名為 `roadmap.md`（徹底清空儲備庫殘留），同時保留原 `roadmap.md` 標頭之歷史 `> 模型：` 不變，而新建之 `changelog.md` 則嚴格使用 CLI 傳入之當輪 `--model`（預設 `Unknown`），絕不讀取 `roadmap.md` 的舊模型。
  2. **標頭單調遞增計數器 (`> 最後分配編號：N`)**：在 `plans/roadmap/TODO.md` 頂部 Blockquote 維護 `> 最後分配編號：N`。每次 `todo add` 取 `max(header_last_id, max_existing_table_id) + 1` 並同步回寫標頭；即使表格內所有列均被 `todo promote` 提取清空，編號依然嚴格單調遞增、永不重複。
  3. **`ORIGIN_SEED_FILES` 種子白名單與 `Seeded` 狀態機**：於 `status.py`、`scanner.py` 與 `verifier.py` 統一註冊 `ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}`：
     - 當目錄僅含種子檔與 `changelog.md` 時，`PlanStatusResolver` 與 `PlanScanner` 將其識別為 `Seeded`（`Seeded (Pending Plan)`），引導原地補齊規格檔。
     - `PlanVerifier` 將 `backlog`, `proposed`, `ready`, `deferred`, `seeded` 納入合法狀態，對 `ORIGIN_SEED_FILES` 豁免 `sub_XX` 之 `> 所屬主計畫：` 檢查、豁免動態模板標題強制比對與 `Completed` 未勾選 Checkbox 檢查，僅保留基礎標頭與佔位符防呆。

> [!CAUTION]
> 嚴禁將 `TodoManager.add_todo` 的編號分配邏輯退化為僅掃描當前表格現存列（必在 `todo promote` 清空表格後發生 ID 碰撞）；嚴禁在 `RoadmapManager.promote_roadmap` 中讀取舊 `roadmap.md` 的 `> 模型：` 填入新生成的 `changelog.md`；嚴禁從 `verifier.py` 移除 `ORIGIN_SEED_FILES` 對 `sub_XX` 子計畫 `> 所屬主計畫：` 的豁免保護。

---

### [DN-AW-12] 唯讀 Subagent 零劇透盲審傳址、純靜態禁跑測、Single-Writer 鐵律與多路線圖合流追加合併防坑設計

- **工程背景與坑點**：
  1. **實作隔離的跨模組耦合反效果與 Subagent 污染計畫狀態機**：同一開發計畫內的多個任務或跨模組變更往往存在緊密相依與共享熱啟動上下文（Warm Context），若在 `Phase 05` 強行派發子代理隔離實作，反而造成重複探索與介面斷裂；此外，若允許 Subagent 直接編輯 `plans/` 下的檔案，極易損毀 `> 模型：` 標頭與微觀變更日誌。
  2. **Reviewer Subagent 提示詞錨定偏誤、重複跑測風暴與漏審新建檔案**：
     - 若主視窗在派發 Reviewer Subagent 時於提示詞中「摘要或劇透本次改了哪些檔案與邏輯」，會導致子代理產生確認偏誤（Confirmation Bias），僅順著主視窗描述檢查而忽略漏改處。
     - 若未明確禁止 Reviewer 執行實機指令或跑測，子代理常自行啟動測試套件或建置指令，不僅浪費雙倍執行時間，還可能改寫快取/編譯產物造成工作區狀態競爭。
     - 在尚未執行 `git commit` 前，新建檔案處於 `Untracked (??)` 狀態，單跑 `git diff HEAD` 無法檢出內容；若未設定硬性審查契約邊界，子代理亦常挑剔命名或排版微調。
  3. **多路線圖合流子計畫 `promote` 覆寫**：單一大型子計畫常需消費 2 份高度關聯的路線圖（如 `sub_03` 包含測試規範與 Subagent 隔離）。若 `RoadmapManager.promote_roadmap` 無差別使用 `shutil.move`，第 2 份路線圖將直接覆寫第 1 份已遷入的 `roadmap.md`。
- **妥協與防禦設計**：
  1. **廢棄實作隔離與 Single-Writer 鐵律**：`Phase 05` 編碼實作統一由主視窗 Agent 直接執行；`plans/` 檔案 100% 僅由主視窗集中寫入，唯讀子代理嚴禁修改任何專案與計畫檔案。
  2. **零劇透盲審傳址、純靜態唯讀禁跑測與三類硬性契約**：派發 Reviewer 時**嚴禁告知本次計畫實作內容，僅提供目標計畫路徑**由子代理自行讀取規格書並結合 `git status --short` 直讀 `Untracked` 新檔獨立探索；**明確告知子代理嚴禁進行實機/測試運行，僅可運行唯讀工具進行靜態檢查**；且嚴格限制僅回報敷衍修補/測試反模式、需求遺漏與文檔未同步三類硬性缺失，其餘情況強制回傳 `REVIEW_STATUS: PASSED`。
  3. **多路線圖合流追加合併 (`is_appended`)**：`RoadmapManager.promote_roadmap` 偵測到目標目錄已存在 `roadmap.md` 時，自動將新路線圖內容追加合併於分隔線之後並安全刪除來源檔案，伴隨 `changelog.md` 精確記載追加操作。

> [!CAUTION]
> 嚴禁允許 Subagent 修改 `plans/` 下任何檔案或執行實機/測試運行指令；嚴禁在派發 Reviewer Subagent 時於提示詞劇透本次實作內容；嚴禁 Reviewer Subagent 回報非三類硬性契約的主觀微調；嚴禁在 `RoadmapManager.promote_roadmap` 中直接以 `shutil.move` 覆寫既有 `roadmap.md`。

---

### [DN-AW-13] 跨模組多捐贈者導覽錨點 (`HOW_TO_*_MODULES`)、兩階段漸進式隨包手冊調度與跨模組 `_resolve_source_path` Sibling Fallback 防坑設計

- **工程背景與坑點**：
  1. **日常 `/context-init` 載入全模組教學與體檢矩陣的 Token 膨脹**：若將 `core`、`dev`、`server`、`knowledge-db` 的組態體檢清單與功能教學直接塞入 `AGENTS.md` 或 `context-init/SKILL.md`，每次日常開發對話都會無條件消耗上千 Token，且當未來新增或移除模組時，硬編碼於 `agents-workflow` 的教學清單會立即過時或產生死連結。
  2. **跨模組 `module://<mod>/...` 在沙盒或尚未安裝新版 `@build` 時之本地 Fallback 錯位**：`ArtifactCompiler._resolve_source_path()` 的 Step 2 本地自包含回退邏輯，原先在解析 `module://core/assets/config_guide.md` 時僅剝除 `<mod>/` 前綴後直接拼接至 `self.module_root`（即 `agents-workflow` 目錄）。當 `core` 新增的資產尚未同步至 `.modules/core/`（或處於獨立測試沙盒）時，回退至 `agents-workflow/assets/config_guide.md` 會導致讀取失敗或誤讀同名檔案。
  3. **`tokens` CLI 對 `name` / `value` 雙欄位顯示不一致**：部分模組（如 `knowledge-db`）在 `contributes/agents-workflow.json` 宣告 `token` 時使用 `"name"` 欄位，而 `scripts/cli.py:tokens()` 僅讀取 `tok.get("value", "")`，導致終端機輸出空白 Token 名稱。
- **妥協與防禦設計**：
  1. **專用主動指令型教練技能與多捐贈者 `mode: "below"` 聚合**：將組態體檢與功能導覽獨立為僅於顯式輸入時觸發的 `/how-to-config-yscb` 與 `/how-to-yscb`，並在 `AGENTS.md` 頂部僅保留精簡的 `PROJECT_ROLE_AND_BOUNDARIES` 錨點（未配置時自動抹除 0 殘留）。各模組透過 `HOW_TO_CONFIG_MODULES` 與 `HOW_TO_YSCB_MODULES` 貢獻 15~25 行精煉片段，底部以單反引號包覆之 `` [`<mod> 隨包手冊`](`__#{module://<mod>/README.md}__`) `` 實現「第一階段秒答、第二階段按需讀取隨包 `README.md`」。
  2. **跨模組 Sibling Directory Fallback**：於 `ArtifactCompiler._resolve_source_path()` Step 2 中，當 URI scheme 為 `module://` 且 `<mod>` 非當前 `self.module_root` 目錄名時，自動檢查同級目錄 `os.path.join(os.path.dirname(self.module_root), mod_name)` 是否存在，精準定位兄弟模組源碼資產。
  3. **Token 名稱雙欄位相容**：於 `scripts/cli.py:tokens()` 統一採用 `tok.get("value") or tok.get("name") or ""`，並於 `knowledge-db/contributes/agents-workflow.json` 同步補齊 `"value"`。

> [!CAUTION]
> 嚴禁將多模組詳細體檢表或教學長文注入 `AGENTS.md` 或 `context-init`；各模組注入 `HOW_TO_*_MODULES` 之片段中所有 `__#{...}__` 與 `__${...}__` 標籤在非代碼區塊內必須強制以單反引號包覆；嚴禁將 `_resolve_source_path` 的跨模組 `module://<other_mod>/` 回退路徑硬綁回 `agents-workflow` 自身目錄。

---

### [DN-AW-14] `/skill-creator` 三軌擴充防膨脹、`AGENTS_SKILL_ROUTING` 表格列結構隔離與教學範例 Fenced Code Block 編譯器正則保護

- **工程背景與坑點**：
  1. **下游專案濫建微型 Skill 導致路由表膨脹**：若使用者僅需在 `Phase 05` 或 `/context-init` 增加幾行專案注意事項，卻每次都建立一個全新的 `SKILL.md` 並掛入 `AGENTS_SKILL_ROUTING`，會導致 `AGENTS.md` 條件路由表迅速膨脹、降低全系統觸發精準度。
  2. **`AGENTS_SKILL_ROUTING` 與獨立區塊錨點的結構衝突**：全系統 22 個 Stage 1 Token 錨點中，21 個位於獨立段落行（支援注入 Markdown 標題與清單），唯獨 `AGENTS_SKILL_ROUTING` 位於 `AgentsStandards.md` 的 Markdown 表格內部；若向 `AGENTS_SKILL_ROUTING` 注入一般標題段落，會直接截斷並損毀 `AGENTS.md` 的技能路由表。
  3. **擴充教學文檔內含抽象語法範例觸發編譯器警告**：`skill-creator/SKILL.md` 與 `references/extension-guide.md` 需向 Agent 展示佔位符與語意 URI 寫法。若在一般段落或表格行內使用單反引號包覆虛構之教學範例（如不存在的 URI 或假 Token 名），`ArtifactCompiler` 在 Stage 1/2 會嘗試將其當作真實標籤解析並噴出 `[compiler:warning] Unresolved semantic URI tag`；若不加反引號裸寫，則會被 `check_unenclosed_tags` 攔截報出 `Unenclosed placeholder tag`。
- **妥協與防禦設計**：
  1. **三軌擴充智能分流 (`3-Track Extension Triage`)**：於 `skill-creator` 步驟 1 強制區分「軌跡 ① 純錨點注入（`snippets/<name>.md`，0 路由開銷）」、「軌跡 ② 被動環境攔截型 Skill」與「軌跡 ③ 功能特化型 Skill」，針對局部階段注意事項優先引導採用軌跡 ①。
  2. **22 個錨點結構屬性顯式標註與三步驗證守門**：於 `references/extension-guide.md` 明確標註 `AGENTS_SKILL_ROUTING` 的「Markdown 表格列」專屬屬性，並於步驟 4 強制執行 `contributes check` $\to$ `agents-workflow compile`（0 Error / 0 Warning）$\to$ `agents-workflow release` 三步驗證守門。
  3. **`LITERAL_FENCED_BLOCK_REGEX` (`<!-- yscb:literal -->`) 教學範例保護與真實 URI 雙軌寫法**：由於一般 Fenced Code Block（如狀態卡模板）內的語意 URI 仍需在 Stage 2 轉譯為相對路徑，若直接在教學區塊寫出 `__@{...}__`、`__#{...}__` 或 `__${...}__`，物化後教學語法會被 Stage 1 抹除或被 Stage 2 轉譯為相對路徑。因此於 `ArtifactCompiler` (`compiler.py`) 引入 `LITERAL_FENCED_BLOCK_REGEX`：凡在三反引號 Fenced Code Block 首行標註 `<!-- yscb:literal -->` 者，在 Stage 1 (`resolve_single_artifact`) 與 Stage 2 (`resolve_stage2_uri`) 均會先抽離保護、不予解析，並於 Stage 2 物化時自動剝除首行 `<!-- yscb:literal -->` 標記、100% 保留原始字面量教學語法；而在非字面量區塊之散文或表格中，則一律使用穿插型真實語意 URI（如 `` `__${config://agents-workflow}__/contribute.json` ``）以在物化後保留行內反引號。

> [!CAUTION]
> 在維護 `skill-creator/SKILL.md` 與 `references/extension-guide.md` 時，凡需在物化產物中原樣展示 `__@{...}__`、`__#{...}__`、`__${...}__` 字面量教學語法者，必須置於首行標註 `<!-- yscb:literal -->` 之 Fenced Code Block 內；向 `AGENTS_SKILL_ROUTING` 注入之片段必須嚴格保持 Markdown 表格列格式。





