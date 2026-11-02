# 專題調研與分析報告：`module:space` 通用檔案空間與指紋快取底座模組評估 (R01_module_space_evaluation.md)

> 調研主題：`module:space` 通用檔案空間與指紋快取底座模組效益、可行性與合理性評估  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  外部設計提案建議將目前位於 `module:knowledge-db` 內部的「多空間定義聚合（`SpaceManager`）」與「雙階增量指紋快照引擎（`FingerprintScanner` / `BinarySnapshotManager (YFP1)`）」解耦抽離為 `ys-codebase` 第 6 枚獨立模組 **`module:space`（Layer 1 純標準庫底座）**，並賦予其四大職責：
  1. 統一空間幾何抽象與雙軌聚合（`SpaceManager` + `space_ref` 引用分離）。
  2. 微秒級 `YFP1` 二進位快照與「空間總指紋（Space Merkle Root）」計算（支援 `eager_content` / `lazy_stabilized` / `stat_only` 三級雜湊策略）。
  3. 全系統唯一背景監聽與差量廣播（`SpaceWatcherServiceWorker`）。
  4. 跨模組 `.gitignore` 受管區塊協調器。
- **調研目標與範疇**：
  結合 `ys-codebase` v1.2.1 實體代碼庫（`knowledge-db`、`agents-workflow`、`server`、`core`）與現行路線圖（僅保留 `task-cache`，暫不納入 `rclone-tools` / `sg-tools`），從 **「合理性（事實與架構查核）」、「可行性（深層技術盲點與並發陷阱）」、「效益與 ROI（近期 vs. 遠期）」** 三個維度進行嚴格審計，並給出客觀落地裁決。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 合理性評估：對照現有代碼庫之事實查核 (Rationality & Fact-Check)

經實機檢視 `knowledge-db`、`agents-workflow` 與 `server` 源碼，提案中有 **3 項核心洞察完全成立**，但也有 **3 項假設與現況存在明顯落差**：

| 查核項目 | 外部提案宣稱之假設 | v1.2.1 原始碼實證查核結果 | 合理性判定 |
| :--- | :--- | :--- | :---: |
| **1. 標準庫純淨度** | `space.py`（208 行）與 `scanner.py`（430 行）100% 僅依賴 Python 標準庫，無任何重型第三方套件耦合 | **完全屬實**：`space.py` 僅引用 `json/logging/pathlib` 與 `core.{uri,contributes}`；`scanner.py` 僅引用 `struct/fnmatch/os/tempfile/time`。兩者與 `tree-sitter`、`fastembed`、`networkx` 完全零耦合。 | **高（成立）** |
| **2. 領域屬性分離 (`space_ref`)** | 將空間幾何（`include/exclude`）與業務屬性（如 `knowledge-db` 的 `weight`、`task-cache` 的 `command`）透過 `space_ref` 分離 | **設計優雅且合理**：目前 `agents-workflow/contributes/knowledge-db.json` 將 `weight: 1.2` 直接寫在 `SpaceDef` 內；若未來 `task-cache` 與 `knowledge-db` 共用 `"source"` 空間，以 `space_ref` 引用可避免重複定義 `include/exclude`。 | **高（成立）** |
| **3. 空間總指紋 (`Merkle Root`) 對 `task-cache` 的價值** | 對空間內匹配檔案排序後計算單一 SHA-256 總指紋，供 `task-cache` 快取命中與 `P06` 防偽測試印章使用 | **完全成立且為 `task-cache` 剛需**：`task-cache` 的核心就是比對「當前空間指紋 == 上次綠燈印章」，計算確定性 Merkle Root 是最標準的解法。 | **高（成立）** |
| **4. 現有模組「重複造輪子」程度** | 宣稱 `core/engine.py`、`server/watcher.py`、`agents-workflow` 各自重複造輪子，抽離 `space` 可大幅消除重複 | **部分誇大（存在職責錯位）**：<br>• `server/watcher.py`（138 行）監聽的是 `.modules/` 系統部署目錄以重啟 Worker，屬於 **Layer 0 宿主內部機制**，絕不能反向依賴 Layer 1 的 `space`。<br>• `agents-workflow/publisher.py` 的 `_get_source_file_sha1` 針對單一模板資產做 CRLF 正規化與 SHA-1 快取，已高度最佳化（`< 1ms` 短路）。<br>• `plans/scanner.py` 掃描的是 `plans/YYYY_MM_DD_*` 計畫狀態機與 Markdown 表頭，並非通用檔案指紋比對。 | **中低（對現有模組收益有限）** |
| **5. `YFP1` 快照已儲存內容雜湊 (`hash`)** | 提案 §1 與 §4.2 稱現有 `YFP1` 儲存 `{relpath: (mtime, size, hash)}` 並執行雙階內容比對 | **與事實不符**：檢視 `scanner.py:48`（`ENTRY_STRUCT = "<HQd"`），現行 `YFP1` **僅儲存 `(path_len, size, mtime)`**，`FileFingerprint.sha1` 目前為空字串預設值，並未實際讀取檔案計算 SHA-1/SHA-256。若要支援抗 `touch` / `git checkout` 的 `eager_content` Merkle Root，必須升級二進位格式（如 `YFP2`）並補寫基於 `(mtime, size)` 快篩的二階段內容雜湊計算。 | **需修正規格** |
| **6. 分級雜湊策略 (`hash_policy`)** | 提供 `eager_content`、`lazy_stabilized`、`stat_only` 三級雜湊策略以隔離小代碼與下游大型資產/依賴目錄 | **高（作為通用底座具備必要前瞻性）**：下游專案（如遊戲資產、韌體映像、編譯產物或大型依賴目錄）之檔案體積與寫入型態未知；在 `SpaceDef` 層級保留 `eager_content` / `lazy_stabilized` / `stat_only` 三級策略，能防止下游配置大檔案空間時阻塞背景 Watcher 或引發檔案控制代碼鎖死。 | **高（成立，應保留）** |
| **7. 跨模組 `.gitignore` 協調器** | 允許空間宣告 `git_ignore: true` 並統一維護 `.gitignore` 受管區塊 | **不納入（收斂範疇）**：依開發者裁決，現階段專注於 `space` 空間定義、分級指紋與背景監視本體設計，不橫跨 `.gitignore` 代管等非核心外圍職責。 | **低（排除以保持高內聚）** |

---

### 2.2 可行性評估：3 大深層技術盲點與架構陷阱 (Feasibility & Technical Pitfalls)

若直接按照外部提案照單全收實作，將在執行期觸發以下 **3 個嚴重技術陷阱**，必須在架構設計上修正後才具備可行性：

#### 陷阱一：【致命並發競態】快照單一所有權與「Watcher 提前覆寫 `.meta.bin` 導致業務模組漏更新」（Snapshot Advance Race Condition）
- **問題剖析**：
  提案 §4.3 設計：「`SpaceWatcherServiceWorker` 在 Debounce 穩定後計算出 `ScanDiffDetail(added, modified, deleted)`，**先原子更新 `YFP1` 快照**，再透過 `core.events`（或記憶體回呼）將差量清單推送給訂閱該空間的業務模組。」
- **為什麼這會導致災難性資料不一致？**
  1. 在現行 `knowledge-db/pipeline.py:567` 中，`unified.meta.bin` 是在 AST 解析、BM25 倒排修補、呼叫圖重連與向量更新 **全部成功完成後的最後一步（Stage 4 `_persist_patched_indices`）** 才寫入磁碟！
  2. 如果改由底層 `space-watcher` **先更新 `.meta.bin` 快照**，一旦隨後：① 開發者終端機正好在 `server` 未啟動或重啟瞬間發起 CLI 查詢、② 業務模組熱修補中途發生例外或超時熔斷、或 ③ 某個消費者模組當下尚未載入，下次該業務模組執行 `check_invalidation` 時，會看到 `.meta.bin` 已經是最新狀態（`Clean`），從而**永久漏掉這批變更檔案，造成索引腐敗（Silent Corruption）**！
- **可行性修正方案（Snapshot Watermark vs. Consumer Cursor 解耦）**：
  - `module:space` 維護的 `space.meta.bin` 僅作為 **「磁碟物理狀態快取（Shared Stat + Hash Cache，加速免重讀檔案計算 SHA-256）」**。
  - **每個消費模組（`knowledge-db`、`task-cache`）必須各自持有自己的「已提交游標 / 已驗證印章（Committed Merkle Root 或 Consumer Snapshot）」**！唯有當消費者自身完成索引更新或測試通過時，才推進自身的印章。如此即便 `space` 隨時刷新底層檔案雜湊快取，也永遠不會吃掉任何上層模組尚未消化的 Diff！

#### 陷阱二：`core.events` 的跨進程邊界限制（Hook 機制並非 IPC 訊息佇列）
- **問題剖析**：
  提案 §4.3 提到透過 `core.events` 將差量事件分發給業務模組。
- **現況查核**：
  檢視 `core/events.py`，`events.broadcast(event_name, context, emit_module="space")` 是透過動態載入 `module://<mod>/scripts/hook.space.py` 在 **當前進程（In-Process）** 內同步呼叫函式。
  - 當 `space-watcher` 運行於 `server` 的常駐 `WarmWorker` 子進程內時，`events.broadcast(..., emit_module="space")` 確實可以在同一個 `WarmWorker` 進程內喚醒 `knowledge-db` 與 `task-cache` 的 `hook.space.py` 進行熱修補。
  - 但對於外部獨立啟動的單次 CLI 進程（未走 `server` 派發時），In-Process 廣播無法跨進程通知，因此消費者仍必須依賴上方的「比對自身已提交 Merkle Root vs. `space` 當前 Merkle Root」來實現 100% 冪等自足。

#### 陷阱三：背景監視依賴與 `watchdog` 整合策略
- **問題剖析**：
  原提案一方面強調「`module:space` 100% Python 標準庫、零 `pip` 依賴」，另一方面又要求將 `knowledge-db/service.py`（依賴 `watchdog>=4.0.0`）遷移為 `space` 的 `SpaceWatcherServiceWorker`。
- **可行性修正方案（直接於 `module:space` 宣告 `watchdog>=4.0.0` 依賴 + 標準庫安全降級）**：
  - 經開發者拍板，既然 `module:space` 專司檔案空間與指紋監視，且原本 `knowledge-db` 即已宣告 `"watchdog": ">=4.0.0"`，直接讓 `module:space` 的 `manifest.json` 承接 `"pip_dependencies": {"watchdog": ">=4.0.0"}` 最為直接且合理！
  - 如此 `SpaceWatcherService` 可直接使用成熟的作業系統原生事件（`inotify` / `FSEvents` / `ReadDirectoryChangesW` 與 `PollingObserver`），免除在標準庫中自造複雜的輪詢樹；若遇極端尚未執行 `pip` 同步之受限沙盒，則以 `try: import watchdog` 安全降級至被動 JIT 掃描模式。

---

### 2.3 效益與 ROI 評估：現在做 vs. 與 `task-cache` 同步啟動 (Cost-Benefit & Timing Analysis)

我們必須誠實評估：**在 `task-cache` 尚未正式動工的「今天」，立刻單獨抽離 `module:space` 的投資報酬率（ROI）有多高？**

1. **對現有 5 大核心模組的立即收益（單一真實消費者）**：
   - 目前全母倉真正需要「多空間 `include/exclude` + 檔案快照比對 + 背景監聽」的模組只有 **`knowledge-db` 1 個**（`agents-workflow` 雖貢獻了 `docs` 與 `plans` 空間定義，但那是貢獻給 `knowledge-db` 檢索用的）。
   - 若為了單一消費者而將母倉從 5 個模組擴增為 6 個模組，將立即增加：
     - 每次 `restore`、`status`、`dev check`、`dev test`、`dev release` 的第 6 份模組打包與沙盒開銷；
     - `knowledge-db` 與 `space` 之間的跨模組版本約束同步成本（Breaking Change 需雙模組聯動升版）。
2. **當 `task-cache` 啟動時的雙消費者協同收益（ROI 轉正拐點）**：
   - 一旦啟動路線圖中的 **`task-cache`**，全系統將同時存在 **2 個重度依賴空間指紋與背景監聽的核心模組**（`knowledge-db` 算語意索引指紋、`task-cache` 算建置測試指紋與 `P06` 防偽印章），外加 `agents-workflow` 的 `plan verify` 印章查驗（第 3 個輕量消費者）。
   - 此時若無共用底座，`knowledge-db` 與 `task-cache` 將在 `server` 後台啟動 2 個獨立的 Watcher 執行緒，並在每次存檔時對同一批源碼各自掃描磁碟計算雜湊。此時抽離或共用空間指紋底座的效益才會真正顯現。

---

### 2.4 三大候選落地架構方案深度對比 (Candidate Architecture Comparison)

| 評估維度 | 方案 A：立即新建獨立模組 `module:space`（修正三大技術陷阱後立即落地） | 方案 B：維持於 `knowledge-db` 或下沉至 `module:core.space` | **方案 C：完整保留分級雜湊之 `module:space` 納入路線圖，與 `task-cache` 協同演進（推薦方案）** |
| :--- | :--- | :--- | :--- |
| **核心作法** | 立即建立第 6 模組 `space`，實作 `SpaceManager`、`YFP2`（含三級 `hash_policy`）、`MerkleRoot`、`space-watcher` 與游標分離機制，並重構 `knowledge-db` | 將純標準庫的 `space.py` + `scanner.py`（約 500 行）作為按需載入子套件 `core.space` 放入 `module:core`（或緩存於 `knowledge-db`），不新增第 6 模組 | **完整保留 `SpaceDef` 三級雜湊策略（`eager_content` / `lazy_stabilized` / `stat_only`）與 `space_ref` 設計**，並修正快照游標競態與 `YFP2` 規格，列為 Layer 1 基礎設施路線圖（可作為 `task-cache` 前置底座或獨立立項） |
| **解決多頭監聽與下游大檔案防護** | **完美支援**：立即提供三級雜湊隔離與單一監聽 | Watcher 仍需掛於業務模組 | **完美支援**：保留三級 `hash_policy` 保護下游未知大檔案情境，並在多消費者登場時提供單一 `space-watcher` 與共用 Merkle Root |
| **架構複雜度與維護稅** | **中高**：立即多維護第 6 個模組，但能提前驗證 `knowledge-db` 解耦 | **低**：維持母倉 5 大核心模組拓撲不膨脹 | **最佳平衡**：架構規格一次定錨無損，可依排程隨時 `roadmap promote` 啟動（或若決定現在做則直接走出口 ①） |
| **並發安全性（防漏更新）** | **高（經本次調研修正後）**：採用「底層共享 `(mtime, size, sha256)` 快取池 + 上層消費者各自持有已提交 Merkle Root 游標」 | 維持現有由消費者提交快照之安全模型 | **高**：採用「底層共享 `(mtime, size, sha256)` 快取池 + 上層消費者各自持有已提交 Merkle Root 游標」雙層分離設計 |

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. **效益與合理性總評（高度合理，且應保留三級分級雜湊 `hash_policy`）**：
     - 將純標準庫的「空間幾何定義（`SpaceManager`）+ 雙階增量雜湊與空間總指紋（`Merkle Root`）+ 單一背景檔案監聽」抽離為共用底座並透過 `space_ref` 解耦領域屬性，對 `knowledge-db`、`task-cache` 及下游專案自訂空間具有高度架構價值。
     - **保留分級雜湊策略（`eager_content` / `lazy_stabilized` / `stat_only`）**：考量下游專案使用情境多元（可能包含大型二進位建置產物、韌體映像、美術資產或龐大第三方標頭檔目錄），保留三級 `hash_policy` 能確保 `module:space` 面對未知下游負載時具備 I/O 隔離與防鎖死韌性。
  2. **可行性關鍵修正（實作時必守之 3 項技術修正）**：
     - **修正 ①（根除快照覆寫競態）**：嚴禁由 `space-watcher` 單方面覆寫業務模組的變更比較基準；`space` 應維護「物理檔案 `(mtime, size, sha256)` 共享快取表」並即時計算當前 `merkle_root`，而 `knowledge-db` 與 `task-cache` 各自保存最後一次成功處理的 `committed_merkle_root`（或檔案狀態表），確保任何異常中斷或離線 CLI 執行皆 100% 不漏更。
     - **修正 ②（真正落實雙階內容雜湊 `YFP2` 與三級策略）**：在現有僅存 `(mtime, size)` 的 `YFP1` 基礎上升級為 `YFP2`，納入 `hash_policy`：
       - `eager_content`：當 `(mtime, size)` 未變時直接複用快取之 `sha256`（`< 0.1ms` 合成空間 `merkle_root`），當 `mtime/size` 改變時重算檔案 `sha256`。
       - `lazy_stabilized`：背景監聽期間僅記錄 `(mtime, size)` 並確認檔案連續穩定且無獨佔寫入鎖後，或於上層顯式呼叫驗證時才計算內容雜湊。
       - `stat_only`：純以 `(relpath, size, mtime)` 合成空間指紋，零檔案內容讀取。
     - **修正 ③（直接依賴 `watchdog>=4.0.0` 實現原生 OS 監聽）**：由 `module:space` 直接宣告 `"pip_dependencies": {"watchdog": ">=4.0.0"}`，統一採用 `watchdog` 原生事件驅動監聽，免除重複維護自製輪詢樹，並聚焦於空間定義、分級指紋與游標隔離本體。
- **後續建議**：
  已由開發者拍板採納 **選項 B（修訂 `R01`/`R02` 並完成 `R03` 生態系前置介面與 `contributes`/CLI 契約調研定案後，直接立項開發 `module:space`）**。

