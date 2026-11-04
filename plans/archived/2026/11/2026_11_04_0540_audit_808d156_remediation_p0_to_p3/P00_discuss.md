# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_04_0540_audit_808d156_remediation_p0_to_p3  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 Commit `808d156b1412f464de01a52a3be2bd6343821204` 全專案八維度單點序列深度審計表單（共 14 項 Issue：`AUD-01` ~ `AUD-14`，含 P0 1 項、P1 4 項、P2 5 項、P3 4 項）完成修復與驗證。
- **核心目標**：
  1. **P0 高危阻斷修復 (`AUD-01`)**：根除 `server` Master 自我重啟與 Worker 派生時之單例鎖 FD / 日誌句柄繼承死鎖風險（`os.set_inheritable(fd, False)`、`close_fds=True` 與嚴格自我重啟移交序列）。
  2. **P1 跨平台與並發競態修復 (`AUD-02` ~ `AUD-05`)**：
     - `AUD-02` (`vscode-support`)：實作字串感知之 JSONC 剝離器（移除字串外 `//`、`/* */` 註解與尾隨逗號），讀取含 JSONC 註解之 `.vscode/settings.json` 時自動備份至 `.vscode/settings.json.bak` 後完成軟合併，若語法損毀則備份並保留原檔告警；所有 JSON/Schema 寫入統一採用同目錄 `.tmp` + Windows `PermissionError` 退避重試之原子替換。
     - `AUD-03` & `AUD-05` (`core`, `dev`, `yscb.py`)：於 `core/vfs/os_backend.py` 建立統一的 `robust_rmtree` 與 `robust_replace` 防腐適配函式（`U2` Anti-Corruption Shim），內建唯讀屬性剝離 (`stat.S_IWRITE`)、Windows `WinError 5 / 32` 退避重試與跨掛載點 `EXDEV` 安全回退，以及 macOS `/var -> /private/var` 成對 `os.path.realpath` 路徑邊界檢查。
     - `AUD-04` (`ast`, `core`)：於 `GrammarProvisioner._try_pip_install` 及 `PipManager` 安裝入口加上跨進程排他檔案鎖 (`InterProcessLock`) 與獲鎖後 Double-Checked 存在性驗證。
  3. **P2 狀態隔離、管道防死鎖與圖譜一致性 (`AUD-06` ~ `AUD-10`)**：
     - `AUD-06` (`yscb.py`, `core`)：同進程派發多模組同名腳本（`scripts/cli.py`、`scripts/hook.*.py`）時，統一賦予唯一模組命名空間 `_yscb_mod_{module_id}_{script_stem}` 杜絕 `sys.modules` 快取污染。
     - `AUD-07` (`dev`)：測試子進程與超時控制採用獨立進程群組（Process Group / Session）與 `terminate_popen_tree` 整棵進程樹清理，並為 `communicate()` 加上二次超時防線防止孫進程霸佔管道死鎖。
     - `AUD-08` (`server`)：`ServerLogger` 與日誌讀取/輪替支援非阻塞句柄釋放與檔案截斷/輪替偏移量重置（`st_size < last_offset` 或 inode 變更歸零），防止 Windows 輪替鎖衝突。
     - `AUD-09` (`file-space`)：`FingerprintScanner` 納入 `(st_mtime_ns, st_ctime_ns)` 與 `RACY_CLEAN_WINDOW_NS` 臨界時間窗強制雜湊複核，並對 `scandir` / `stat()` 捕獲 `OSError` 安全忽略懸空或循環符號連結。
     - `AUD-10` (`knowledge-db`, `ast`)：增量熱修補刪除或修改檔案時，先依 `file -> symbol_ids` 索引徹底拔除 `CallGraphIndex` 內舊節點與關聯邊；對同一索引目錄之持久化加跨進程排他鎖防止前景 JIT 與背景 Worker 互相覆蓋。
  4. **P3 冷啟動延遲載入與演算法加速 (`AUD-11` ~ `AUD-14`)**：
     - `AUD-11` (`yscb.py`, `knowledge-db`, `ast`)：頂層重型依賴（`networkx`, `numpy`, `fastembed`）延遲載入（Lazy Import）守門，頂層僅保留 `if TYPE_CHECKING:`。
     - `AUD-12` (`core`)：於 `core/contributes.py` 與 `core/validator.py` 建立基於 `(path, mtime_ns, size)` 的程序內 JSON 解析快取，消除單次 CLI 週期內重複讀取 `manifest.json` 與 `contributes/*.json`。
     - `AUD-13` (`agents-workflow`)：`session_trace.py` 與 `_trace_parser.py` 強化逐行生成器串流解析與單行超長緩衝截斷保護，控制巨型 JSONL 記憶體峰值。
     - `AUD-14` (`ast`)：於 `TopologyLinker` / `resolver.py` 預建 `short_name -> list[UnifiedSymbol]` 與 `module_suffix -> list[UnifiedSymbol]` 二級倒排雜湊索引，將跨檔案後綴匹配由 $O(N^2)$ 線性掃描降為 $O(1)$ 查找。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.platform.lock.InterProcessLock` 實現 `AUD-04`（語法包/Pip 安裝鎖）與 `AUD-10`（索引持久化鎖），不另造新鎖類別。
  - 復用並擴充 `core.vfs.os_backend.OSBackend` 既有之 `remove()` / `atomic_write()` 邏輯，提煉為模組級公開輔助函式 `robust_rmtree` 與 `robust_replace` 供 `OSBackend`、`AtomicEngine`、`Installer` 與 `SandboxProvisioner` 統一調用。
  - 復用 `core.platform.process.terminate_popen_tree` 於 `dev` 測試子進程超時清理（`AUD-07`）。
- **邊界排除 (Explicitly Excluded)**：
  - 已於審計報告 §3 確認排除之 5 項假陽性（`RFP-01` ~ `RFP-05`）不在修改範圍內。
  - 不引入任何第三方套件（如 `json5` 或 `commentjson`），`AUD-02` 之 JSONC 剝離器 100% 以 Python 標準庫狀態機實作。
- **架構影響範圍**：
  - 涵蓋 `yscb.py` 及 `ys_codebase/source/{core,server,dev,vscode-support,file-space,ast,knowledge-db,agents-workflow}/` 全倉 8 個模組之內部穩健性、跨平台防腐層與效能優化，不破壞對外 CLI 語法契約。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `AUD-02` `.vscode/settings.json` JSONC 剝離與 `.bak` 備份保護策略**：
  - 實作純標準庫、字串感知（String-Aware）之 `strip_jsonc(raw_text: str) -> str`，精準剝離雙引號字串字面量以外的單行註解 `//...`、多行註解 `/*...*/` 與物件/陣列尾隨逗號（`,}` / `,]`），同時絕不誤傷字串內的 URL（如 `"http://..."`）。
  - 當偵測到原始 `.vscode/settings.json` 含 JSONC 語法（標準 `json.loads` 失敗但經 `strip_jsonc` 後解析成功），或經 `strip_jsonc` 後仍無法解析時，先將原始檔案完整備份至 `.vscode/settings.json.bak`；解析成功者繼續執行軟合併與原子寫入，解析失敗者輸出告警並保留原檔不覆寫（同步更新 `test_vscode_support.py` 之 `test_et_01` 覆蓋 JSONC 註解成功合併 + `.bak` 備份，以及真正損毀語法之保護）。
- **[P00:DR-02] 單一 Full Track 計畫分流與 4 大工作包閉環**：
  - 採單一標準開發計畫 (`Full Track`) 一次閉環推進 `AUD-01` ~ `AUD-14`，於架構與實作階段劃分為 4 個正交工作包：
    - **WP-1 (`AUD-01`, `AUD-08`)**：`core.platform` & `server` 句柄隔離、自我重啟移交序列與日誌輪替安全。
    - **WP-2 (`AUD-02`, `AUD-03`, `AUD-05`, `AUD-06`, `AUD-12`)**：`core.vfs` (`robust_rmtree` / `robust_replace` / `realpath` / `EXDEV`)、`core.symbols` / `dispatcher` 腳本命名空間隔離、`core.contributes` I/O 快取與 `vscode-support` JSONC 容錯。
    - **WP-3 (`AUD-04`, `AUD-07`, `AUD-09`, `AUD-13`)**：`dev` 沙盒與測試進程樹清理、`file-space` Racy Stat Gate 與壞連結防禦、`ast` / `core` Pip 跨進程鎖與 `agents-workflow` JSONL 串流記憶體防線。
    - **WP-4 (`AUD-10`, `AUD-11`, `AUD-14`)**：`ast` & `knowledge-db` 呼叫圖孤兒節點清除、跨進程持久化鎖、重型依賴延遲載入（`networkx` / `numpy` / `fastembed`）與跨檔案後綴二級雜湊索引 $O(1)$ 加速。

---

## 3. 開放議題與確認紀錄

- **[已確認]** `AUD-02` 採用選項 A（字串感知 JSONC 剝離解析 + `.bak` 備份寫入，損毀時備份並保留原檔）。
- **[已確認]** 採用單一標準開發計畫（Full Track）一次閉環完成 `AUD-01` ~ `AUD-14`。

