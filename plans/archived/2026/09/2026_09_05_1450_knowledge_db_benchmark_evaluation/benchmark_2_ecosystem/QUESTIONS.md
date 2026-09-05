# Knowledge-DB 深度實戰評測題目集與驗證真值表 (Benchmark 2 Questions & Ground Truth)

本文件定義針對 `ys-codebase` 深度架構、模組生命週期、故障排除與實用開發情境的基準評測題目集（第二代 Benchmark 2）。  
題目完全脫離人為提示（無「查 callers」、「算 impact」等直接指令語意），全數採用**下游使用者與核心開發者真實遭遇之深度架構問題、疑難雜症排查與系統保障機制**。

---

## 📊 評測題目總覽 (Overview)

| 題號 | 難度分級 | 核心主題 | 測試焦點 | Ground Truth 目標檔案/核心機制 |
| :---: | :--- | :--- | :--- | :--- |
| **Q1.1** | **Level 1 (機制排查)** | `.agents` Workflow 被重置根因 | 發布投影定位、ReleasePublisher 4 步原子交易、SSOT 與修改路徑 | `source/agents-workflow/.../publisher.py`<br/>`ReleasePublisher`、Stage 2C 發布流水線 |
| **Q1.2** | **Level 1 (機制排查)** | 宿主跑測阻斷與沙盒硬校驗 | `SecurityError` 觸發條件、沙盒向上探測特徵演算法、目錄防污染 | `source/dev/dev/testing/case.py`<br/>`YSCBTestCase.setUp`、`SandboxContext` |
| **Q1.3** | **Level 1 (機制排查)** | 新模組 CLI 路由未生效 | `yscb.py` 分發路徑、三態隔離 (source ➔ build ➔ modules)、生效流程 | `yscb.py` (`dispatch_module`)<br/>`dev build` + `install @build` 閉環 |
| **Q2.1** | **Level 2 (架構運作)** | 2x2 組態矩陣合併與降級 | 雙層遞迴深層合併 (`_deep_merge`)、原子寫入語意、本機設定刪除降級 | `source/core/core/config.py`<br/>`ConfigManager`、`snapshot://` 快照備份 |
| **Q2.2** | **Level 2 (架構運作)** | `handoff.md` 凍結與恢復機制 | `/Pause` 現場凍結、`/Continue` 恢復順序與 Phase 比對、歸檔物理清理 | `docs/agents-workflow/user_guide.md`<br/>`source/agents-workflow/.../archiver.py` |
| **Q2.3** | **Level 2 (架構運作)** | 計畫封存 4 重守門防護 | PlanVerifier 剛性檢核、完成標記、CHANGELOG 登載約束、--force | `source/agents-workflow/.../archiver.py`<br/>`PlanArchiver.archive_plan` |
| **Q3.1** | **Level 3 (疑難雜症)** | 知識庫守護進程防抖與自癒 | 500ms 防抖鎖定、Space 監聽篩選、版本變更自我重啟、閒置釋放 | `source/knowledge-db/.../daemon.py`<br/>`HotReloadServer`、`[DN-15]` |
| **Q3.2** | **Level 3 (疑難雜症)** | 大規模檔案毫秒級增量檢索 | 雙階指紋 (mtime+size ➔ SHA1)、二進位快照 `unified.meta.bin`、差量修補 | `source/knowledge-db/.../scanner.py`<br/>`FingerprintScanner`、`[DN-03]`, `[DN-04]` |
| **Q3.3** | **Level 3 (疑難雜症)** | Python 套件安裝損毀與回滾 | 微環境隔離、事前快照 (`act_snapshot`)、`PipInstallError` 自動回滾 | `source/core/core/installer.py`<br/>`source/core/core/pip_manager.py` |

---

## 🎯 Level 1：帶有具體機制/架構實體定位之問題 (Deep Mechanism Queries)

### Q1.1 為什麼手動修改 `.agents/` 內的 workflow 檔案會被覆蓋重置？
- **問題描述**：  
  「有下游開發者反應：他在專案的 `.agents/workflows/Auto.md` 中手動客製化了一段提示詞，但過了一陣子執行某些指令（如模組更新或重新發布）後，發現修改全部消失、被還原成預設內容了。  
  請深入剖析造成此現象的底層架構原因：
  1. 目錄 `.agents/` 在全專案架構中的角色定位是什麼？它與上游源碼的關係為何？
  2. 是哪一個模組、哪一個核心類別在哪個階段執行了覆蓋？其發布管線包含哪 4 個原子步驟？
  3. 若開發者欲永久修改或擴充 workflow，正統的架構途徑應當為何？」
- **Ground Truth**：
  1. **定位**：`.agents/` 屬於由 `agents-workflow` 自動管理的「發布投影目錄 (Projected Release Target)」，視為編譯/物化產物，並非唯一真理來源 (SSOT)。
  2. **覆蓋引擎與 4 步原子發布交易**：
     - 由 `agents-workflow` 模組的 `ReleasePublisher` 類別（`ys_codebase/source/agents-workflow/agents_workflow/publisher.py` Line 50 起）在 Stage 2C 階段執行。
     - 發布流水線包含：
       - **步驟 1 (過往狀態獨立清理 Pruning)**：比對歷史發布清冊，刪除已廢棄或已刪除之目標實體檔案。
       - **步驟 2 (提前解算)**：對啟用的 Targets 提前完整解算中繼檔案至實體目標檔案之映射表。
       - **步驟 3 (原子寫入 Manifest)**：將 Project 軌 (`project://`) 寫入 `storage://`，Local 軌寫入 `cache://`。
       - **步驟 4 (物理落地與增量軟合併)**：將 Stage 1 解算之 Markdown 文本重新覆蓋寫入目標目錄（顯式傳入 `\n` 純 LF 換行），並對 `AGENTS.md` 執行無損軟合併。
  3. **正統途徑**：修改上游模組源碼的模板（`ys_codebase/source/agents-workflow/assets/workflows/`），或透過第三方模組以 `contributes.agents-workflow.exports` 宣告進行擴充注入。

---

### Q1.2 為什麼在專案根目錄下直接執行跑測會引發 `SecurityError` 阻斷？
- **問題描述**：  
  「新加入的工程師習慣在專案根目錄下直接輸入 `pytest` 或調用 `python yscb.py dev op-test` 進行跑測，卻遭遇系統剛性攔截並拋出 `SecurityError`。  
  請深入分析：
  1. 系統是在哪個類別的哪個生命週期方法中進行沙盒環境校驗的？
  2. 該方法是如何透過『向上爬樹』探測目錄特徵來判斷當前是否處於合法虛擬沙盒中的？其特徵條件為何？
  3. 這項剛性守門設計拔除了早期系統的什麼漏洞？架構防護目標是什麼？」
- **Ground Truth**：
  1. **校驗實體與方法**：`YSCBTestCase.setUp`（`ys_codebase/source/dev/dev/testing/case.py` Line 100~120）。
  2. **向上探測演算法與特徵條件**：
     - 若環境變數 `YSCB_SANDBOX_DIR` 未設定，自 `os.getcwd()` 逐層向上爬樹檢查父目錄。
     - 合法沙盒特徵條件（二者滿足其一）：
       - 目錄名稱以 `sandbox_` 開頭且包含 `host_env/` 子目錄；或
       - 目錄內部同時存在 `host_env/` 與 `mock_provider/` 子目錄。
     - 若爬至根目錄仍未命中，剛性拋出：
       `SecurityError: [dev:test] Security Guard Blocked: Unable to resolve an authentic virtual sandbox directory from '...' Running tests directly on the host workspace is strictly forbidden to prevent environment contamination.`
  3. **漏洞拔除與防護目標**：徹底拔除舊版本在找不到沙盒時自動回退至 `os.getcwd()` 的嚴重漏洞；杜絕測試程式碼中的檔案 I/O、套件安裝或測試產物意外外溢污染真實宿主專案。

---

### Q1.3 為什麼在 `source/` 建立了新模組，CLI 卻提示找不到命令？
- **問題描述**：  
  「某開發者在 `source/my-plugin/` 建立了一個新模組，並在 `manifest.json` 中配置了 `contributes.core.commands` 與對應的 CLI 腳本。然而他在終端執行 `python yscb.py my-plugin <cmd>` 時，系統卻回應找不到模組或命令。  
  請分析：
  1. `yscb.py` 在分發模組命令時，其真實探測的檔案物理路徑為何？為什麼它完全不感知 `source/`？
  2. YS-Codebase 的『三態隔離架構』是如何劃分源碼、構建產物與運行環境的？
  3. 開發者必須依序執行哪些標準 CLI 指令，才能讓新模組的 CLI 順利在宿主環境生效？」
- **Ground Truth**：
  1. **真實探測路徑**：`yscb.py` 中的 `dispatch_module` 函式（約 Line 842 起），其探測目標為：
     `os.path.normpath(os.path.join(yscb_abs, ".modules", module_name, "scripts", "cli.py"))`。
     `yscb.py` 嚴格僅從 `.modules/<module>/` 載入運行端代碼，完全不讀取未物化的 `source/` 開發目錄。
  2. **三態隔離架構**：
     - 源碼空間：`source/{module}/`（唯一的真理來源 SSOT，Git 追蹤）。
     - 構建空間：`.build/{module}/{version}/`（打包產物，Git 忽略）。
     - 運行空間：`.modules/{module}/`（實體部署物化代碼，Git 忽略）。
  3. **標準生效指令流程**：
     1. `python yscb.py dev build my-plugin`（打包源碼至 `.build/`）。
     2. `python yscb.py install my-plugin@build --force`（以直裝通道安全同步至 `.modules/`，自動在 `yscb.config.json` 註冊並觸發 `reload`）。

---

## 🔍 Level 2：模組架構運作與組態/生命週期管理 (Architecture & Lifecycle Queries)

### Q2.1 2x2 組態矩陣深層合併、原子寫入與本機刪除降級機制
- **問題描述**：  
  「在 YS-Codebase 的 2x2 組態矩陣中：
  1. 當呼叫 `core.config.get(module, key)` 時，底層 `ConfigManager` 是如何實作 `config.local.json` 與 `config.project.json` 的深層繼承與合併的？
  2. 當系統更新設定值時，採用了什麼原子寫入語意？寫入前有什麼災難恢復防護？
  3. 當開發者透過 CLI 刪除某個本機專屬設定鍵（`--local`）時，底層檔案如何變化？為什麼專案層級的設定不會被損壞？」
- **Ground Truth**：
  1. **深層合併機制**：`ConfigManager._deep_merge`（`ys_codebase/source/core/core/config.py` Line 54 起），採遞迴深拷貝合併；若兩層皆為字典則遞迴深入，否則由 `config.local.json` 覆蓋 `config.project.json`（優先級：Local > Project）。
  2. **原子寫入與災難防護**：
     - 寫入時先寫入同目錄之 `.tmp` 暫存檔，確認寫入完成後透過 `os.replace` 原子覆蓋目標檔案，杜絕斷電產生半截損毀檔案。
     - 透過 `core.config` 變更組態前，引擎自動執行快照備份至 `snapshot://`。
  3. **本機刪除與降級**：調用 `delete_raw(local=True)` 時僅從 `config.local.json` 中透過 `_delete_by_dot_path` 移除該鍵；`config.project.json` 完全維持原狀不被觸碰。下次讀取時，因 Local 無此鍵，系統自然平滑降級返回 Project 設定的預設值。

---

### Q2.2 現場交接快照 `handoff.md` 凍結、恢復與歸檔清理防護
- **問題描述**：  
  「在專案開發作業流程 (SOP) 中：
  1. 當開發者因突發中斷執行 `/Pause` 時，系統在何處生成 `handoff.md`？其核心職責是什麼？
  2. 當後續在全新 Session 輸入 `/Continue` 時，系統依據什麼順序判定接續目標？如何利用 `handoff.md` 避免重複讀取歷史計畫？
  3. 在計畫最終封存歸檔 (`plan archive`) 時，`handoff.md` 會遭遇什麼處置？為什麼？」
- **Ground Truth**：
  1. **`/Pause` 凍結**：於進行中計畫目錄（`plans/<plan_dir>/` 或 `plans/<plan_dir>/sub_XX/`）生成 `handoff.md`，以標準結構記錄當前計畫、所處 Phase、阻塞項、已修改檔案清單與下一步恢復指令，達成現場狀態凍結。
  2. **`/Continue` 恢復順序**：
     - 第一步調用 `python yscb.py agents-workflow plan status` 獲取進行中計畫大綱。
     - 探測計畫目錄下的 `handoff.md`；若存在則作為現場唯一真理來源 (SSOT) 優先加載，無需重新閱讀全量歷史。
     - 比對 `P00`~`P07` 各 Phase 交付物之狀態標註（`Draft` / `Confirmed` / `Completed`），精確定位至未完成的 Phase 銜接推進。
  3. **歸檔處置與理由**：`PlanArchiver.archive_plan`（`ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` Line 132-140）在搬移計畫前執行 `temp_handoff.unlink()` 物理刪除。因為 `handoff.md` 僅為暫存性交接快照，結案成果已登載於 `P07_walkthrough.md` 與 `CHANGELOG.md`，物理清除可杜絕過期現場污染歷史歸檔庫。

---

### Q2.3 計畫封存 `plan archive` 的 4 重守門安全防護
- **問題描述**：  
  「當開發者執行 `python yscb.py agents-workflow plan archive <plan_name>` 試圖封存結案計畫時：
  1. 系統在執行目錄搬移前，會依序執行哪 4 重剛性安全守門檢查？
  2. 如果專案根目錄的 `CHANGELOG.md` 尚未記載該計畫的發布紀錄，系統會發生什麼行為？
  3. 在什麼情況下可以跳過這些檢查？是否有任何一項守門檢查是即使附加旗標也絕對禁止跳過的？」
- **Ground Truth**：
  1. **4 重安全守門**（實作於 `PlanArchiver.archive_plan`，`ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` Line 87~145）：
     - **守門 1 (PlanVerifier 合規檢核)**：調用 `verifier.verify_plan(src_dir)` 執行 5-Stage 檢核，若有重大錯誤 (`FAIL`) 則拋出 `PlanIncompleteError` 阻斷。
     - **守門 2 (完成狀態標記)**：檢查 `fast_track_plan.md`、`FT_plan.md`、`P07_walkthrough.md` 或 `umbrella_overview.md` 是否標註 `Completed`；未完成拋出 `PlanIncompleteError`。
     - **守門 3 (全域 CHANGELOG 登載)**：讀取專案根目錄 `CHANGELOG.md`，確認包含該計畫名稱之發布章節；未登載拋出 `PlanIncompleteError`。
     - **守門 4 (目的地衝突防護)**：檢查目標歷史目錄 `workflow.archived://{YYYY}/{MM}/{plan_name}/` 是否已存在同名目錄；若存在拋出 `PlanDestinationExistsError`。
  2. **未記載 CHANGELOG 行為**：系統強制中斷並拋出 `PlanIncompleteError`，嚴格拒絕將未記錄變更歷史的計畫歸檔。
  3. **跳過控制**：附加 `--force` 旗標可略過守門 1、2、3；但**守門 4 (目的地衝突防護) 為剛性物理保護，即使附加 `--force` 也絕對禁止覆蓋現存歷史目錄**。

---

## 💬 Level 3：直白敘述/故障排查與系統效能保障 (Troubleshooting & Reliability)

### Q3.1 為什麼頻繁存檔時知識庫背景進程不會引發 CPU 飆高？改版時如何自我修復？
- **問題描述**：  
  「下游工程師提出疑難雜症：
  『我在 IDE 寫代碼時經常手動按 Ctrl+S，甚至編輯器開了自動存檔。為什麼背景常駐的知識庫進程不會因為高頻的磁碟更動事件而狂飆 CPU，或是跟 CLI 檢索發生資料庫死鎖？如果我剛剛更新了 knowledge-db 模組的版本，這個背景守護進程又是如何自我重啟以避免用舊代碼處理新索引的？』」
- **Ground Truth**：
  1. **高頻存檔防抖與防飢餓**（`HotReloadServer`，`ys_codebase/source/knowledge-db/knowledge_db/daemon.py` Line 124 起，`[DN-15]`）：
     - 使用 `watchdog` 監聽檔案事件，所有事件進入 `_debounce_lock` 保護的 500ms 防抖計時器 (`_debounce_timer`)。短時間內的密集變更會被聚合到 `_pending_dirty_paths` 集合，待變更冷卻後才單次觸發熱修補。
     - 透過 `SpaceManager.is_path_watched` 雙軌過濾副檔名與排除目錄，迅速過濾無關檔案。
     - 前端 CLI 檢索時，探測到背景 PID 存活會輸出提示並跳過 JIT 檢查，消滅內外進程爭搶資料庫鎖。
  2. **版本自適應重啟**：
     - 守護進程啟動時記錄 `self.version = self.get_module_version()`。
     - 在 Hook 觸發喚醒或每次循環時，若探測到模組代碼版本不相符，自動向舊進程發送 SIGTERM/停止信號並拉起全新版本進程，實現零介入版本自癒。
  3. **閒置資源釋放**：內建 `_inactivity_thread`，超過 600 秒（10分鐘）無檢索活動即自動關閉守護進程，避免無休止佔用記憶體。

---

### Q3.2 為什麼代碼庫擴大至千檔規模時，搜尋依然能在毫秒級完成而無需全盤重掃？
- **問題描述**：  
  「『當我們的專案規模越來越大（包含數百上千個檔案）時，為什麼每次在終端執行 `knowledge-db search` 依然能在數十毫秒內返回，而不需要每次都卡住數十秒把整個磁碟重新掃描一遍？如果我剛剛只微調了其中一個檔案，系統是如何在底層精準只更新該檔案的？』」
- **Ground Truth**：
  1. **雙階增量指紋比對 (Two-Stage Fingerprint, `[DN-03]`)**：
     - 實作於 `FingerprintScanner`（`ys_codebase/source/knowledge-db/knowledge_db/scanner.py` Line 184 起）。
     - **Stage 1 (輕量初篩)**：利用 `os.scandir` 僅比對檔案的 `mtime + size`，耗時 2~3ms，零檔案內容讀取 I/O、零 SHA-1 計算。未變更檔案立即略過。
     - **Stage 2 (SHA-1 內容比對)**：僅針對 Stage 1 判定變更之少數檔案讀取內容計算 SHA-1，精準過濾出 `added`, `modified`, `deleted` 差異清單。
  2. **原生二進位快照 (`unified.meta.bin`, `[DN-04]`)**：
     - 採用 Magic `YFP1` + Python `struct` 原生二進位封裝檔案清冊，反序列化耗時 $<0.1\text{ms}$，徹底取代大型 JSON 解析開銷。
  3. **差量索引修補 (Patch Incremental, `[DN-09]`)**：
     - AST 符號池、倒排索引與向量快取（`VectorIndex.patch_incremental`）均採用增量補丁機制，僅對更動檔案的符號進行熱置換，避免重建整體資料庫。

---

### Q3.3 安裝第三方套件如果中途失敗，系統是如何避免微環境損毀並自動復原的？
- **問題描述**：  
  「『在 YSCB 微環境中，如果某個模組在安裝第三方套件（如 FastEmbed 或 Tree-sitter）時，因為網路不通、版本衝突或 wheel 損毀導致 pip 安裝失敗，系統是如何確保微環境不處於半安裝的損壞狀態，並自動復原成原本可用的樣貌？』」
- **Ground Truth**：
  1. **微虛擬環境物理隔離**：
     - YSCB 在 `yscb://.venv/`（`yscb_dir/.venv/py{ver}/`）維護專屬微環境，由 `core.PipManager` 統一管理，嚴格使用 Wheel-Only 靜默安裝，與宿主系統全域 Python 100% 隔離。
  2. **事前原子快照備份**：
     - 實作於 `source/core/core/installer.py`（Line 85 起）。
     - 在執行 `cmd_install` 或 `cmd_update` 前，首先調用 `snap_id = self.engine.act_snapshot("pre_install")`，在 `snapshot://` 完整備份所有已安裝模組設定與 `yscb.config.json` 快照。
  3. **例外捕獲與原子回滾流水線**：
     - 若 `PipManager` 引發 `PipInstallError` 或任何未預期例外，`Installer` 立即捕獲異常：
       ```python
       except Exception as e:
           print(f"[core:install] Error during install: {e}")
           self.engine.act_restore_snapshot(snap_id)
           return 1
       ```
     - 調用 `act_restore_snapshot(snap_id)` 將環境完全還原至安裝前狀態，並釋放跨進程鎖，確保系統絕不殘留半損毀環境。

---

## 📈 評測計量指標 (Benchmark Metrics)

各題均需記錄：
1. **工具呼叫次數 (Tool Calls)**
2. **檢索讀取字元 (Read Chars) 與預估 Tokens** ($\text{Chars} \div 4$)
3. **思考步驟數 (Thinking Steps)**
4. **耗時 (Wall-Clock Seconds)**
5. **答案準確度 (Accuracy 0~100%)**
