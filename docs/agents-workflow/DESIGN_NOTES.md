---
target: "Agents-Workflow"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/agents-workflow/agents_workflow/compiler.py"
  - "yscb://source/agents-workflow/agents_workflow/publisher.py"
  - "yscb://source/agents-workflow/agents_workflow/initializer.py"
  - "yscb://source/agents-workflow/config.project.json"
related_docs:
  - "./README.md"
  - "./FACTORY_PIPELINE.md"
  - "./user_guide.md"
last_updated: "2026-10-15"
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
