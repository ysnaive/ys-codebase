# 專題調研與分析報告：YS-Codebase 全倉八維度與三平台單點序列深度審計報告 (R01_full_codebase_deep_audit_report.md)

> 調研主題：YS-Codebase 全量生產模組八維度與三平台深度審計 (`Unit 01` ~ `Unit 10`)  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：本地端完成最新一批全倉確定性優化、`file-space` 併入 `core.space` 以及 `module:ast` 語法引擎重構後，需針對全倉 8 大活躍模組與 `yscb.py` 進行零死角之單點序列深度審計，識別潛在跨執行緒競態、跨行程 IPC 死鎖、增量索引資料一致性缺口、跨平台（Linux / Windows / macOS）相容性差異與資安邊界漏洞。
- **調研目標與範疇**：涵蓋 `yscb.py` 與 `core`、`ast`、`knowledge-db`、`server`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 共 218 個生產源碼與組態檔案，劃分為 10 個審計單元（`Unit 01` ~ `Unit 10`），依 `C1`~`C8`（24 子類）與三步自我反駁（Step 2.5）產出 P0~P3 分級診斷與具體修復處方。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

# 🛡️ YS-Codebase 全倉八維度單點序列深度審計報告 (Full Codebase Deep Audit Report)

> 審計日期：2026-11-09  
> 受審分支與帳本版本：[`repo/main/.yscb_gdrive.json`](https://drive.google.com/file/d/1lC166wEJB_-tz7-WB2ee0LLySjvlo0Oq/view?usp=drivesdk)（含 `file-space` 收斂入 `core.space`、[`2026_11_07_1548_ast_architecture_research`](https://drive.google.com/drive/folders/1P-L34s3mdWiyfLg2wn0Q1Kp-fdtMzzuq) 三階段 AST 重構、Server Worker RSS/孤兒進程防護、以及統一 Cell 生命週期與 Stage Profiler）  
> 審計方法學：`codebase-deep-auditor` 八大維度（`C1` ~ `C8` 共 24 子類）+ 三大作業系統（`Linux + Windows + macOS`）+ 三步反向查證  

## 1. 審計執行摘要與十單元健康度矩陣 (Executive Summary & Unit Matrix)

- **受審範圍與規模**：全倉 8 大模組（`core`、`ast`、`knowledge-db`、`server`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support`）及頂層單檔啟動器 [`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk)，共劃分為 **10 個獨立審查單元（`Unit 01` ~ `Unit 10`）** 完成逐一序列深潛與跨單元契約核對。
- **目標語言與平台基準**：語言 `Python 3 (100% Standard Library 微內核 + 可選 Tree-sitter / NetworkX / FastEmbed 防腐降級)` ｜ 平台基準 `Linux (POSIX) + Windows (NTFS / Win32) + macOS (APFS / Darwin)`
- **全倉診斷統計總覽**：
  - 🔴 **P0 (Critical)**：`4` 項
  - 🟠 **P1 (High)**：`25` 項
  - 🟡 **P2 (Medium)**：`26` 項
  - 🔵 **P3 (Optimization)**：`12` 項
  - ✅ **已排除之假陽性與確認安全設計 (`RFP`)**：`38` 項

| 審查單元 (Audit Unit) | 涵蓋模組與核心職責 | P0 | P1 | P2 | P3 | 檢出項目編號 | 單元狀態 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **`Unit 01`** | [`yscb.py`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) + `module:core` 核心引擎、命令分派、日誌、上下文、載入器、遷移腳本（22 檔） | 0 | 2 | 3 | 3 | `CORE-AUD-01` ~ `05`, `08` ~ `10` | 🟠 建議優先修復 |
| **`Unit 02`** | `module:core` 之 `platform/`、`vfs/`、`space/` 檔案空間引擎（收編原 `file-space`，13 檔） | 0 | 0 | 2 | 0 | `CORE-AUD-01` *(跨單元)*, `06`, `07` | 🟡 結構與邊界微調 |
| **`Unit 03`** | `module:ast` 核心引擎、原子 `SymbolNode`、`WorkspaceSymbolGraph`、四階段 `linker.py`、`resolver.py`、`bundler.py`、`provisioner.py`（16 檔） | 1 | 4 | 3 | 2 | `AST-AUD-01` ~ `05`, `09`, `10`, `13` ~ `15` | 🔴 建議優先修復 |
| **`Unit 04`** | `module:ast` 通用 `TreeSitterDriver`、交換律合流器與各語言 Parsers / Dialects（16 檔） | 0 | 3 | 2 | 1 | `AST-AUD-06` ~ `08`, `11`, `12`, `16` | 🟠 建議優先修復 |
| **`Unit 05`** | `module:knowledge-db` 引擎、`IndexingPipeline`、Schema、Config、Providers、IO Utils（11 檔） | 1 | 3 | 2 | 1 | `KDB-AUD-01` ~ `04`, `08`, `09`, `13` | 🔴 建議優先修復 |
| **`Unit 06`** | `module:knowledge-db` 檢索、`HybridSearchEngine`、`EmbeddingService`、`ServiceWorker`、`hook.ast.py`（11 檔） | 0 | 3 | 3 | 1 | `KDB-AUD-05` ~ `07`, `10` ~ `12`, `14` | 🟠 建議優先修復 |
| **`Unit 07`** | `module:server` `MasterSupervisor`、`WarmWorker`、`ServiceManager`、`SpaceWatcher`、RSS 監控（10 檔） | 1 | 3 | 3 | 1 | `SRV-AUD-01` ~ `07`, `14` | 🔴 建議優先修復 |
| **`Unit 08`** | `module:dev` 靜態守門檢查器、測試沙盒、建置發布器 + `module:vscode-support`（15 檔） | 0 | 3 | 3 | 1 | `SRV-AUD-08` ~ `14` | 🟠 建議優先修復 |
| **`Unit 09`** | `module:agents-workflow` 編譯器、發布器、計畫檢核與歸檔工具鏈、`contributes/ast.json`（19 檔） | 0 | 3 | 4 | 0 | `WF-AUD-02` ~ `04`, `07` ~ `10` | 🟠 建議優先修復 |
| **`Unit 10`** | `module:gdrive-support` 同步協調器、`GoogleDriveApiTransport`、三方對帳器、常駐服務（8 檔） | 1 | 2 | 1 | 2 | `WF-AUD-01`, `05`, `06`, `11` ~ `13` | 🔴 建議優先修復 |

## 2. 全倉 🔴 P0 與 🟠 P1 核心問題跨單元速覽表 (Critical & High Priority Cross-Unit Index)

| 全局編號 | 單元編號 | 嚴重度 | 維度與平台 | 檔案路徑與行號座標 | 核心問題摘要 |
| :---: | :---: | :---: | :---: | :--- | :--- |
| **P0-1** | `AST-AUD-01` (`Unit 03`) | 🔴 P0 | `C4.3 & C5.1` (`All-OS`) | [`ast/ast_engine/provisioner.py:L143-L232`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) | `GrammarProvisioner.load_language` 持有程序級 `_LOCK` 跨越 60s 跨進程檔案鎖與 30s `pip install` 網路子進程（阻塞全程序 90s），且與 `_try_pip_install` 發生 `_LOCK` $\leftrightarrow$ `_provision_lock` 鎖順序反轉 |
| **P0-2** | `KDB-AUD-01` (`Unit 05`) | 🔴 P0 | `C1.1 & C1.3` (`All-OS`) | [`knowledge-db/knowledge_db/pipeline.py:L670-L708`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) | `hot_patch_unified_index` 處理 C# `partial class` 跨檔擴展時，將未修改主檔加入 `dirty_keys` 卻漏收集該主檔其餘非 partial 符號，導致主檔既有符號被 `_evict_dirty_file_artifacts` 永久清空 |
| **P0-3** | `SRV-AUD-01` (`Unit 07`) | 🔴 P0 | `C4.1 & C5.2` (`All-OS`) | [`server/server/master.py:L888-L915, L1011-L1054`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) | `_read_worker_handshake` 於 `worker_ready` 後退出，導致 Worker 閒置期背景服務持續寫入之 IPC 封包無人消費（管道塞滿死鎖風險），且交接期欠缺單一 Owner Demuxer 存在雙重 `readline()` 吞包死鎖風險 |
| **P0-4** | `WF-AUD-01` (`Unit 10`) | 🔴 P0 | `C6.1 & C6.3` (`All-OS`) | [`gdrive-support/gdrive_support/config.py:L334-L363, L616-L632`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) | `collect_space_local_files_with_stat` 與 `is_sensitive_credential_path` 於 `push`/`sync` 掃描時未解析 Symlink 真實目標，同步空間內指向 `.config.local/.../token.json` 或工作區外之符號連結可繞過邊界與黑名單外洩 |
| **P1-1** | `CORE-AUD-01` (`Unit 01/02`) | 🟠 P1 | `C1.1 & C1.3` (`All-OS`) | [`core/core/engine.py:L2128-L2139`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) & [`1.2.8.x.py:L84-L132`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) | `act_reload` 漏呼叫 `core.space.reset_default_instances()`；且 `1.2.8.x.py` 遷移腳本未清理 `yscb.config.json` 與 `.modules/.mirror/.cache/.storage.local` 下之 `file-space` 殘留 |
| **P1-2** | `CORE-AUD-02` (`Unit 01`) | 🟠 P1 | `C1.1 & C1.3` (`All-OS`) | [`core/core/commands/dispatcher.py:L101-L147`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) | `_load_registry` 快取鍵缺少 `.modules` / `contributes.merged.json` 世代 `mtime` 且漏支援單檔 `module://<mod>/contributes.json` |
| **P1-3** | `AST-AUD-02` (`Unit 03`) | 🟠 P1 | `C1.1 & C1.2` (`All-OS`) | [`ast/ast_engine/engine.py:L1375-L1415`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) | `_resolve_symbol_node_for_slice` 在 `UnifiedSymbol` 轉 `SymbolNode` 時漏傳 `overload_suffix` 並以 `cand.fqn == ...` 短路，重載方法切片永遠錯切第 1 個定義 |
| **P1-4** | `AST-AUD-03` (`Unit 03`) | 🟠 P1 | `C1.2` (`All-OS`) | [`ast/ast_engine/linker.py:L180-L187, L758-L861`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) | `TopologyLinker` 與 `expand_contract_symbol_ids` 未將限定基底型別（`pkg.Base`）剝離為 `short_name`，且混用 SHA-1 與 Canonical URI 雙軌 ID |
| **P1-5** | `AST-AUD-04` (`Unit 03`) | 🟠 P1 | `C1.1 & C2.2` (`All-OS`) | [`ast/ast_engine/bundler.py:L603-L622, L1006-L1024`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) | 多 Entry Roots 空間下增量熱修補對含 `/` 相對路徑（如 `scripts/cli.py`）跳過 `max_mtime` 消歧，且刪除檔時誤查已清空快取連坐誤刪跨模組同名檔 |
| **P1-6** | `AST-AUD-05` (`Unit 03`) | 🟠 P1 | `C1.1 & C4.2` (`All-OS`) | [`ast/ast_engine/bundler.py:L1109-L1126`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) & [`linker.py:L1404-L1476`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) | `bundle_union` 平行檢查漏列 `query_files`/`processors`/`spaces` 導致子進程丟失擴充規則；Pass 2 多跳 Barrel Re-export 受字母序限制且未回填 `_resolved_import_edges` |
| **P1-7** | `AST-AUD-06` (`Unit 04`) | 🟠 P1 | `C1.1 & C1.2` (`All-OS`) | [`ast/ast_engine/parsers/treesitter.py:L69-L75, L1427-L1457`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) | C++ `namespace` 內類外方法定義丟失類別作用域導致 `.h/.cpp` 配對失敗；Python `self.attr = ...` 重複賦值被誤加偽重載後綴 |
| **P1-8** | `AST-AUD-07` (`Unit 04`) | 🟠 P1 | `C1.1 & C2.3` (`All-OS`) | [`ast/ast_engine/parsers/registry.py:L383-L390`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) | 無 `tree_sitter` 環境下 `ParserRegistry` 未自動降級掛載標準庫 [`PythonASTParser`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk) 與 [`MarkdownParser`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk) |
| **P1-9** | `AST-AUD-08` (`Unit 04`) | 🟠 P1 | `C1.1 & C2.1` (`All-OS`) | [`ast/ast_engine/parsers/base.py:L231-L286`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) & [`treesitter.py:L838-L862`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) | `convert_legacy_symbols_to_file_graph` 將完整外框錯綁為 `parts["name"]`；`TreeSitterDriver` 對無 `body` 多行宣告截斷簽名並混用 Byte 長度作為 `end_col` |
| **P1-10** | `KDB-AUD-02` (`Unit 05`) | 🟠 P1 | `C4.1 & C1.3` (`All-OS`) | [`knowledge-db/knowledge_db/pipeline.py:L1268-L1276`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) | 背景 `KnowledgeDBServiceWorker` 處於常駐空閒 (`worker_active=True, worker_busy=False`) 時，前景 `search` 因 `if worker_active or worker_busy:` 無條件跳過 JIT 同步回傳舊索引 |
| **P1-11** | `KDB-AUD-03` (`Unit 05`) | 🟠 P1 | `C1.1 & C1.2` (`All-OS`) | [`knowledge-db/knowledge_db/pipeline.py:L435-L448`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) | `build_unified_index(force=False)` 見 `unified.index.bin.gz` 存在即短路返回，無視未同步 AST 世代與缺失之 `unified.vectors.bin.gz` |
| **P1-12** | `KDB-AUD-04` (`Unit 05`) | 🟠 P1 | `C1.1 & C1.3` (`All-OS`) | [`knowledge-db/knowledge_db/pipeline.py:L648-L666, L871`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) | `ASTEngine` 先行推進多個世代時，`hot_patch_unified_index` 僅修補局部 `diff_detail` 卻將 `acked_ast_generation` 直接覆寫為最新世代 |
| **P1-13** | `KDB-AUD-05` (`Unit 06`) | 🟠 P1 | `C1.1 & C1.2` (`All-OS`) | [`knowledge-db/scripts/hook.ast.py:L10-L34`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) | `on_register_ast_spaces` 漏讀取專案級 `config://knowledge-db/contribute.json` 與 `list` 型態貢獻，與 `KnowledgeEngine` 空間集合失步 |
| **P1-14** | `KDB-AUD-06` (`Unit 06`) | 🟠 P1 | `C1.1 & C2.1` (`All-OS`) | [`knowledge-db/knowledge_db/formatter.py:L114-L142`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) | `UniversalRedundancyFilter.purify_lines` 以子字串 `"/*" in stripped` 判定區塊註解，遇含 `"src/*"` 之程式碼行會吞噬後續所有切片代碼 |
| **P1-15** | `KDB-AUD-07` (`Unit 06`) | 🟠 P1 | `C1.1 & C2.1` (`All-OS`) | [`knowledge-db/knowledge_db/hybrid.py:L157-L185`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk) & [`selector.py:L186-L206`](https://drive.google.com/file/d/148p_sUneWNWzkpkr51aNwwS7POjYe45Y/view?usp=drivesdk) | 向量檢索先取全域 Top-30 再過濾空間/語言/類型導致篩選餓死，且 `SymbolSelector.parse` 誤吞雙詞查詢首詞 |
| **P1-16** | `SRV-AUD-02` (`Unit 07`) | 🟠 P1 | `C4.1 & C4.2` (`All-OS`) | [`server/server/master.py:L747-L770, L1143-L1166`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) | RSS 自動回收與 `restart_worker()` 存在無 `_dispatch_lock` 保護之 TOCTOU 競態（誤殺剛進場任務），且重設 `_last_active_time` 導致 Idle TTL 失效 |
| **P1-17** | `SRV-AUD-03` (`Unit 07`) | 🟠 P1 | `C2.2 & C4.2` (`Windows`) | [`server/scripts/cli.py:L182-L197`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) | `server stop` 僅等待 2.0s（小於 Master 關閉 `watcher(1s)+worker(2s)` 之 3.0s），過早觸發強制擊殺與跨進程同開 `ServerLogger` 引發 `WinError 32` |
| **P1-18** | `SRV-AUD-04` (`Unit 07`) | 🟠 P1 | `C1.1 & C2.2` (`macOS/All`) | [`server/server/space_watcher.py:L134-L144, L312-L313`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) | `is_transaction_locked` 對 `p_root / ".yscb.lock"` 僅檢查 `.exists()` 未探測鎖持有狀態導致永久凍結；`_match_prefix_rel` 在 macOS `/private/var` 下位移算錯 1 字元 |
| **P1-19** | `SRV-AUD-08` (`Unit 08`) | 🟠 P1 | `C4.1` (`All-OS`) | [`dev/dev/testing/sandbox.py:L211-L234, L507-L518`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) | `dev test --all` 平行測試 >8 個模組時，`_allocate_sandbox_root` 在鎖外呼叫 `prune_sandboxes(max_keep=8)` 存在誤刪同批次活躍沙盒風險 |
| **P1-20** | `SRV-AUD-09/10` (`Unit 08`) | 🟠 P1 | `C6.1 & C3.3` (`All-OS`) | [`dev/dev/testing/sandbox.py:L578-L580`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) & [`projector.py:L353-L386`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) | `sandbox.py` 呼叫 `zf.extractall` 缺 Zip Slip 邊界驗證；`projector.py` 因恆真條件 `or pat in merged` 丟棄所有 `core.space` 轉譯之排除規則 |
| **P1-21** | `WF-AUD-02` (`Unit 09`) | 🟠 P1 | `C1.1 & C2.1` (`All-OS`) | [`agents-workflow/agents_workflow/compiler.py:L158-L160, L670-L713`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) | `make_standalone_tag_regex` 缺行首/行尾錨點且 `sub(..., count=1)` 搭配 `purge_regex` 導致行內 Token 被強制斷行、同檔第 2 個相同 Token 被靜默抹除 |
| **P1-22** | `WF-AUD-03` (`Unit 09`) | 🟠 P1 | `C1.2 & C2.1` (`All-OS`) | [`agents-workflow/agents_workflow/compiler.py:L362-L400`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) | `_substitute_stage2_tags_in_segment` 對整個 Fenced Code Block 執行 `DOUBLE_SLASH_CLEAN_REGEX` 破壞程式碼內 `//` 註解與 Python `//` 整數除法 |
| **P1-23** | `WF-AUD-04` (`Unit 09`) | 🟠 P1 | `C1.1 & C1.2` (`All-OS`) | [`agents-workflow/agents_workflow/publisher.py:L546-L591, L877-L944`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) | `local_release_manifest.json` 寫入實體絕對路徑而非 `project://` URI，且 `_verify_agent_rule_injections` 檢核未物化的 `agent_rules` 破壞短路快取 |
| **P1-24** | `WF-AUD-05` (`Unit 10`) | 🟠 P1 | `C1.1 & C1.3` (`All-OS`) | [`gdrive-support/gdrive_support/coordinator.py:L1447-L1470, L1503-L1514, L2550-L2559`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) | Stage 1 提前原地覆寫 `meta["branch_files"]` 導致 Stage 3 `meta_dirty` 恆為 `False`，雲端新增/CoW 替換檔案於 `pull` 後漏寫回 `.yscb_gdrive.json` |
| **P1-25** | `WF-AUD-06` (`Unit 10`) | 🟠 P1 | `C3.2` (`All-OS`) | [`gdrive-support/gdrive_support/transport.py:L1019, L1045-L1071, L1317-L1326`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk) | `GoogleDriveApiTransport` 於短命 `ThreadPoolExecutor` 執行緒內將 Keep-Alive `HTTPSConnection` 存入 `threading.local()`，池銷毀與 `close()` 時洩漏 SSL Socket |


## 3. Track 1 分級處方與查證詳情：`Unit 01` & `Unit 02` (`yscb.py` + `module:core`)

### 🟠 P1 - High（顯著缺陷：雙軌狀態失步 / 遷移與移除殘留）
- **[CORE-AUD-01] [🟠 P1 | C1.1 & C1.3 | All-OS] [`core/engine.py:L1973-L2004, L2128-L2139`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) & [`scripts/migrations/1.2.8.x.py:L84-L132`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) - `file-space` 模組移除並收斂至 `core.space` 後之快取與儲存空間殘留、以及 `act_reload` 漏刷新 `SpaceRegistry` 單例快取**
  - **問題座標與分類**：
    - [`ys_codebase/source/core/core/engine.py`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk)（`AtomicEngine.act_delete:L1973-L2004`、`AtomicEngine.act_reload:L2128-L2139`）
    - [`ys_codebase/source/core/scripts/migrations/1.2.8.x.py`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk)（`migrate:L84-L132`）
    - [`ys_codebase/source/core/core/space/registry.py`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk)（`get_default_registry:L1837-L1858`）
    - [`ys_codebase/source/core/core/space/scanner.py`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk)（`get_default_scanner:L1869-L1902`）
  - **觸發情境與根因分析**：
    1. **程序內 `SpaceRegistry` / `SpaceScanner` 快取於 `act_reload` 未同步失效**：在 [`engine.py:L2128-L2139`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) 中，`act_reload()` 清除了 `config`、`locale`、`symbols`、`contributes`、`uri` 與 `dispatcher` 快取，但**漏呼叫 `core.space.reset_default_instances()`**。在常駐 Server Worker 或單一程序連續執行 `install` / `remove` / `reload` 後，`RuntimeContext.space_default_registries` 與 `space_default_scanners` 仍滯留舊模組的空間定義。
    2. **`1.2.8.x.py` 遷移腳本遺漏清理舊 `file-space` 持久化快照與殘留註冊**：[`1.2.8.x.py:L84-L132`](https://drive.google.com/file/d/1a3ClD-BVgPsI-127p1MW1Oe7s5VCnmx7/view?usp=drivesdk) 將 `config/file-space/contribute.json` 遷移至 `config/core/contribute.json`，但未清理舊版獨立 `file-space` 模組遺留的 `.storage.local/file-space`、`.cache/file-space`、`.mirror/file-space`，亦未檢查 `yscb.config.json` 的 `installed_modules` 是否仍殘留 `"file-space"` 鍵值。
  - **建議解決方案（Recommended Solution）**：
    ```python
    # 1. ys_codebase/source/core/core/engine.py (L2128-L2140)
            try:
                from core import config as cfg_mod, locale as loc_mod, symbols as sym_mod, contributes as contrib_mod
                from core.commands import dispatcher as disp_mod
                from core.space import reset_default_instances as reset_space_instances
                cfg_mod.reload()
                loc_mod.clear_cache()
                sym_mod.clear_callable_cache()
                contrib_mod.invalidate_cache()
                uri.invalidate_uri_cache()
                disp_mod.clear_cache()
                reset_space_instances()
            except Exception:
                pass

    # 2. ys_codebase/source/core/scripts/migrations/1.2.8.x.py (於 migrate 末尾追加清理)
        host_dir = context.get("host_dir")
        if host_dir:
            host_cfg_path = os.path.join(host_dir, "yscb.config.json")
            host_cfg = _read_json_dict_or_none(host_cfg_path)
            if isinstance(host_cfg, dict) and isinstance(host_cfg.get("installed_modules"), dict):
                if "file-space" in host_cfg["installed_modules"]:
                    del host_cfg["installed_modules"]["file-space"]
                    _atomic_write_json_file(host_cfg_path, host_cfg)

        import shutil
        for obsolete_sub in (
            os.path.join(".modules", "file-space"),
            os.path.join(".mirror", "file-space"),
            os.path.join(".cache", "file-space"),
            os.path.join(".storage.local", "file-space"),
            os.path.join(".config.local", "file-space"),
        ):
            obs_path = os.path.join(yscb_dir, obsolete_sub)
            if os.path.isdir(obs_path):
                shutil.rmtree(obs_path, ignore_errors=True)
    ```
- **[CORE-AUD-02] [🟠 P1 | C1.1 & C1.3 | All-OS] [`core/commands/dispatcher.py:L101-L147`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk) - `_load_registry` 直接掃描 `.modules/*/contributes/` 原始檔，缺少 `mtime` 世代鍵與單檔 `contributes.json` 支援**
  - **問題座標與分類**：[`ys_codebase/source/core/core/commands/dispatcher.py`](https://drive.google.com/file/d/11O592fq7I7o0Xeh4UAxePODswLRLeQIC/view?usp=drivesdk)（`_load_registry:L101-L147`） vs [`ys_codebase/source/core/core/contributes.py`](https://drive.google.com/file/d/14uiWHuqM93UGCeXoVN9XeDGgUnBZ8ZTX/view?usp=drivesdk)（`L626-L683`）
  - **觸發情境與根因分析**：
    1. 若模組將指令宣告於統一單檔 `module://<mod>/contributes.json`（[`contributes.py:L672-L683`](https://drive.google.com/file/d/14uiWHuqM93UGCeXoVN9XeDGgUnBZ8ZTX/view?usp=drivesdk) 支援此格式），`_load_registry` 僅掃描 `contributes/(core.json, commands.json)` 而完全漏讀。
    2. `ctx.dispatcher_global_registry` 快取鍵僅比對 `norm_root` 字串而未納入 `contributes.merged.json` 或 `.modules` 的 `mtime`。
  - **建議解決方案（Recommended Solution）**：
    ```python
    # ys_codebase/source/core/core/commands/dispatcher.py (L101-L147)
    def _load_registry(yscb_abs: str) -> CommandsRegistry:
        ctx = get_runtime_context()
        norm_root = os.path.normcase(os.path.abspath(yscb_abs)) if yscb_abs else ""
        modules_dir = os.path.join(yscb_abs, ".modules")
        merged_cache_file = os.path.join(yscb_abs, ".cache", "core", "contributes.merged.json")
        try:
            gen_mtime = os.path.getmtime(merged_cache_file) if os.path.isfile(merged_cache_file) else (
                os.path.getmtime(modules_dir) if os.path.isdir(modules_dir) else 0.0
            )
        except OSError:
            gen_mtime = 0.0
        cache_key = f"{norm_root}|{gen_mtime}"
        if ctx.dispatcher_global_registry is not None and ctx.dispatcher_global_registry_root == cache_key:
            return ctx.dispatcher_global_registry
        ...
    ```

### 🟡 P2 - Medium（鎖重入、臨時檔碰撞、三平台大小寫與孤兒死代碼）
- **[CORE-AUD-03] [🟡 P2 | C4.3 & C1.1 | All-OS] [`core/engine.py:L753-L824`](https://drive.google.com/file/d/145agARs-T07K3eVKWsu0tfVnFaLpe01Z/view?usp=drivesdk) - `AtomicEngine.act_lock` 與 `act_unlock` 使用單一實體鎖檔 `cache://.yscb.lock`，但以 `operation` 名稱分桶計數，導致同進程跨 `operation` 嵌套呼叫時自我拋出 `BlockingIOError` 或提前刪鎖**
  - **建議解決方案**：當 `self._active_locks` 內已有任一已上鎖的 `InterProcessLock` 實例時，跨 `operation` 直接共享同一鎖實例並累加計數，僅在最後一個 `operation` 釋放時才呼叫 `lock.release()`。
- **[CORE-AUD-04] [🟡 P2 | C4.1 & C3.2 | All-OS] [`core/log.py:L945-L958`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk) & [`yscb.py:L60, L835`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - `_rotate_lines_file` 使用 `Path.with_suffix()` 會覆寫原檔副檔名導致同目錄同名不同副檔名日誌碰撞，且 `yscb.py:cmd_self_update` 暫存檔缺 `pid`**
  - **建議解決方案**：將 `log.py:L945` 改為 `tmp_path = target_path.parent / f".{target_path.name}.tmp.{os.getpid()}.{threading.get_ident()}"`，並將 `yscb.py:L835` 改為 `f"{current_file}.tmp_{os.getpid()}"`。
- **[CORE-AUD-05] [🟡 P2 | C8.2 | All-OS] [`core/uri.py:L404-L468`](https://drive.google.com/file/d/1nVAdvAdfNjtElV3tRDmjrrryb_OGzb2R/view?usp=drivesdk) & [`yscb.py:L1292-L1311, L1378-L1407`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) - 雙重查證確認零引用的孤兒死代碼 (`_print_reconcile_prompt` 等 3 個舊互動函式與 `yscb.py` 舊版 `cmd_restore`)**
  - **建議解決方案**：移除 `core/uri.py:L404-L468` 中已廢棄的 3 個私有互動函式；將 `yscb.py:cmd_restore` 精簡為委派 `dispatch_module("core", ["restore"] + argv)`。
- **[CORE-AUD-06] [🟡 P2 | C2.2 & C6.1 | Linux / macOS / Windows] [`core/vfs/os_backend.py:L345-L389`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk) - `OSBackend._safe_copytree` 無條件以 `seen_lower` 跳過大小寫相異檔案（在 Linux 大小寫敏感系統上靜默丟失檔案），且複製 symlink 後漏呼叫 `assert_safe_path`**
  - **建議解決方案**：僅在 `os.name == "nt" or sys.platform == "darwin"` 時啟用 `seen_lower` 去重，並在複製 symlink 後當 `self.root_dir` 存在時呼叫 `self.assert_safe_path(d)`。
- **[CORE-AUD-07] [🟡 P2 | C2.1 | All-OS] [`core/space/scanner.py:L246-L260`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk) & [`core/space/registry.py:L1814`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) - 負值 `mtime_ns` 在 `save_state` 夾限為 `0` 但 `registry.py` 掃描時未夾限為 `0`，導致負時間戳記檔案每次被迫重算 Stage 2 雜湊**
  - **建議解決方案**：於 [`space/registry.py:L1814-L1816`](https://drive.google.com/file/d/1VpZM-5SMErKKtsfD80LK8C6V4n-ZDQ43/view?usp=drivesdk) 統一使用 `max(0, int(st.st_mtime_ns))` 正規化。

### 🔵 P3 - Optimization（效能與樣板收斂）
- **[CORE-AUD-08] [🔵 P3 | C7.1 | All-OS] [`core/contributes.py:L215-L220`](https://drive.google.com/file/d/14uiWHuqM93UGCeXoVN9XeDGgUnBZ8ZTX/view?usp=drivesdk)**：`_deep_merge` 在 `extend` 策略下對可雜湊純量（`str`/`int`/`tuple`）使用輔助 `set` 消除 $O(N^2)$ 線性查找。
- **[CORE-AUD-09] [🔵 P3 | C8.3 | All-OS] [`core/scripts/cli.py:L1001-L1088`](https://drive.google.com/file/d/1yfAawIj_jqBY_MPmXTLeE9wh85FptJk0/view?usp=drivesdk)**：`file_space_<subcmd>` 與 `fs_<subcmd>` 共 16 個單行轉發包裝函式可直接以別名賦值 `file_space_spaces = fs_spaces = _handle_space_spaces` 收斂（保留 `def file_space` 與 `def fs` 頂層群組入口）。
- **[CORE-AUD-10] [🔵 P3 | C8.3 | All-OS] [`core/installer.py:L79-L132, L936`](https://drive.google.com/file/d/17uDfbIVJ6JU-wgmJu8yFmTZS6WS2M6lZ/view?usp=drivesdk)**：`cmd_restore` 先執行 `_restore_module_package` 解壓至 `.modules` 後又呼叫 `act_reload()` 從 `.mirror` 重新解壓第二次，可收斂為僅驗證/同步 `.mirror` 後交由 `act_reload()` 單次解壓。

### ✅ Track 1 已排除之假陽性與刻意設計 (`CORE-RFP-01` ~ `08`)
- **`[CORE-RFP-01]` [`yscb.py:L204-L590`](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk)**：單檔自舉器必須零依賴獨立運作，與 `core/engine.py` 各自維護打包與目錄同步函式屬刻意設計（By Design）。
- **`[CORE-RFP-02]` [`core/context.py:L439-L448`](https://drive.google.com/file/d/1RCAOOWZ6k2dSEixC6ugpVF8Di8817kNL/view?usp=drivesdk)**：`CellScope` 退出時強制設定 `_state["closed"] = True` 並清空快取，背景執行緒繼承 `ContextVar` 不會寫入已關閉之 Cell。
- **`[CORE-RFP-03]` [`core/loader.py:L117-L136`](https://drive.google.com/file/d/1bMcC0wixXQqyBTdtRpJNhqTlWCzU6KTt/view?usp=drivesdk)**：`exec_module` 異常時完整回滾 `sys.modules` 與 `loaded_modules_cache`。
- **`[CORE-RFP-04]` [`core/log.py:L458-L473`](https://drive.google.com/file/d/1s3rumjvEItiDgkGyAosCf0VgDCVfz2cQ/view?usp=drivesdk)**：`DebouncedIOStreamer` 在呼叫 `emit_chunk` 前已清空 `_buffer`，無重入重複輸出風險。
- **`[CORE-RFP-05]` [`core/platform/lock.py:L63-L77`](https://drive.google.com/file/d/1JnE7Sp_K0C5pHrifLkgcs3qpj6_ncKrK/view?usp=drivesdk)**：POSIX `flock` 取得後已比對 `fstat(fd)` 與 `stat(path)` 之 `(st_dev, st_ino)`，彻底防範 Lock on Unlinked File。
- **`[CORE-RFP-06]` [`core/vfs/os_backend.py:L176-L202`](https://drive.google.com/file/d/1ADQcFdC5ngTutKTtfneu9B6PLJ7E6Yu5/view?usp=drivesdk)**：`assert_safe_path` 對根目錄與目標路徑成對使用 `os.path.realpath`，相容 macOS `/var -> /private/var`。
- **`[CORE-RFP-07]` [`core/space/scanner.py:L48, L840`](https://drive.google.com/file/d/1DzG2_uQK7m0ZLcBzfMpTExvPwVgPKSGO/view?usp=drivesdk)**：`RACY_CLEAN_WINDOW_NS = 10_000_000` (10ms) 強制對同毫秒近期修改檔案重算內容雜湊，防範 Racy-Clean。
- **`[CORE-RFP-08]` `core/platform` & `core/space/providers.py` 跨模組 L0 API**：均由 `server`、`dev`、`agents-workflow` 透過正式契約調用，非死代碼。

## 4. Track 2 分級處方與查證詳情：`Unit 03` & `Unit 04` (`module:ast`)


### 🔴 P0 - Critical（高危阻斷：持鎖慢速網路下載與鎖順序反轉死鎖風險）
- **[AST-AUD-01] [🔴 P0 | C4.3 & C5.1 | All-OS] [`ys_codebase/source/ast/ast_engine/provisioner.py:L143-L232`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) - `GrammarProvisioner.load_language` 持有程序級 `_LOCK` 跨越 60s 跨進程檔案鎖與 30s `pip install` 網路下載，且與 `_try_pip_install` 發生鎖順序反轉**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/provisioner.py`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk)（`GrammarProvisioner._try_pip_install:L143-L189`、`GrammarProvisioner.load_language:L191-L262`）｜ 類別 `C4.3`（持鎖慢速網路 I/O 與 AB-BA 鎖順序反轉）｜ 影響平台：`Linux + Windows + macOS` (`All-OS`)
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：`load_language` 於 `L205` 進入 `with cls._LOCK:`（`threading.RLock`），並在未釋放 `cls._LOCK` 的情況下於 `L227` 呼叫 `cls._try_pip_install(pkg_name, module_name=module_name)`。雖然 `_try_pip_install` 在 `L148-L150` 設計了「先取 `cls._LOCK` 檢查 `_FAILED_PACKAGES`、退出 `with` 區塊釋放 `_LOCK` 後，再於 `L152` 獲取跨進程鎖 `with cls._provision_lock():`（`timeout=60.0`）並執行 `subprocess.run([..., "pip", "install", ...], timeout=30)`（`L174-L180`）」，但因為外層 `load_language` 已經持有了可重入鎖 `cls._LOCK`（遞迴計數為 1），內層 `L148` 離開 `with cls._LOCK:` 時遞迴計數僅從 2 降為 1，**鎖並未真正釋放**！
    2. **上游呼叫方查驗**：[`treesitter.py:L562-L566`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) (`TreeSitterDriver._init_driver`) 與 [`engine.py:L1629, L1672`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`ASTEngine.outline` 呼叫 `GrammarProvisioner.get_warnings`) 均直接請求 `GrammarProvisioner._LOCK`。當任一執行緒觸發 `load_language` 自動安裝時，整個程序內其他執行緒連呼叫 `get_warnings()` 或讀取已快取於 `_LOADED_LANGUAGES` 的語言都會被阻塞長達 **90 秒（60s 檔案鎖 + 30s pip 下載）**。此外，直接呼叫 `_try_pip_install` 的鎖順序為 `_provision_lock -> _LOCK`，而經由 `load_language` 呼叫的鎖順序為 `_LOCK -> _provision_lock`，構成鎖序反轉。
    3. **設計意圖核對**：`_try_pip_install` 在 `L148` 與 `L153` 刻意拆成兩段 `with cls._LOCK:`，證實作者原本即希望在等待跨進程鎖與執行 `pip install` 時釋放執行緒鎖，僅因外層 `load_language` 鎖粒度過粗而破功。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：縮小 `load_language` 內 `cls._LOCK` 的持有範圍，僅在讀寫記憶體快取（`_LOADED_LANGUAGES`、`_FAILED_PACKAGES`）時持鎖；執行 `importlib.import_module` 與 `_try_pip_install` 時不持有 `cls._LOCK`，並在 `_try_pip_install` 內維持單一明確的鎖順序 `_provision_lock -> _LOCK`（僅在修改 `_FAILED_PACKAGES` 時短暫取 `_LOCK`）。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/provisioner.py:L143-L261
      @classmethod
      def _try_pip_install(cls, pkg_name: str, module_name: Optional[str] = None) -> bool:
          with cls._LOCK:
              if pkg_name in cls._FAILED_PACKAGES:
                  return False

          with cls._provision_lock():
              with cls._LOCK:
                  if pkg_name in cls._FAILED_PACKAGES:
                      return False
              if module_name:
                  importlib.invalidate_caches()
                  try:
                      importlib.import_module(module_name)
                      return True
                  except ImportError:
                      pass

              try:
                  cmd = [
                      sys.executable,
                      "-m",
                      "pip",
                      "install",
                      "--quiet",
                      "--disable-pip-version-check",
                      pkg_name,
                  ]
                  proc = subprocess.run(
                      cmd,
                      stdout=sys.stderr,
                      stderr=sys.stderr,
                      timeout=30,
                      check=False,
                  )
                  if proc.returncode == 0:
                      importlib.invalidate_caches()
                      return True
              except Exception as exc:
                  log_debug(f"GrammarProvisioner pip install failed for '{pkg_name}': {exc}")

              with cls._LOCK:
                  cls._FAILED_PACKAGES.add(pkg_name)
              return False

      @classmethod
      def load_language(
          cls,
          lang_key: str,
          module_name: str,
          func_name: str = "language",
          auto_install_pkg: Optional[str] = None,
          attempt_auto_install: Optional[bool] = None,
      ) -> Optional[Any]:
          if ":" in module_name:
              module_name, func_name = module_name.split(":", 1)

          cache_key = f"{lang_key}:{module_name}:{func_name}"
          pkg_name = auto_install_pkg or DEFAULT_GRAMMAR_PACKAGES.get(module_name) or module_name.replace("_", "-")

          with cls._LOCK:
              if cache_key in cls._LOADED_LANGUAGES:
                  return cls._LOADED_LANGUAGES[cache_key]
              if pkg_name in cls._FAILED_PACKAGES or module_name in cls._FAILED_PACKAGES:
                  cls._emit_warning(pkg_name)
                  return None

          mod = None
          try:
              mod = importlib.import_module(module_name)
          except ImportError:
              should_install = (
                  attempt_auto_install
                  if attempt_auto_install is not None
                  else (cls.auto_install_enabled or bool(auto_install_pkg))
              )
              if should_install and cls._try_pip_install(pkg_name, module_name=module_name):
                  try:
                      mod = importlib.import_module(module_name)
                  except Exception:
                      mod = None

          with cls._LOCK:
              if mod is None:
                  cls._FAILED_PACKAGES.add(pkg_name)
                  cls._FAILED_PACKAGES.add(module_name)
                  cls._emit_warning(pkg_name)
                  return None

              if tree_sitter is None:
                  cls._FAILED_PACKAGES.add("tree-sitter")
                  cls._emit_warning("tree-sitter")
                  return None

              try:
                  if hasattr(mod, func_name):
                      lang_fn = getattr(mod, func_name)
                  elif hasattr(mod, f"language_{lang_key}"):
                      lang_fn = getattr(mod, f"language_{lang_key}")
                  else:
                      raise AttributeError(f"Module '{module_name}' has no function '{func_name}'")

                  raw_lang = lang_fn()
                  ts_lang = raw_sitter_language(raw_lang)
                  cls._LOADED_LANGUAGES[cache_key] = ts_lang
                  return ts_lang
              except Exception as exc:
                  log_debug(f"GrammarProvisioner failed initializing '{module_name}:{func_name}': {exc}")
                  cls._FAILED_PACKAGES.add(pkg_name)
                  cls._FAILED_PACKAGES.add(module_name)
                  cls._emit_warning(pkg_name)
                  return None
      ```


### 🟠 P1 - High（顯著缺陷：雙軌狀態與契約失步 / 增量熱修補錯位 / 無 Tree-sitter 降級斷裂）
- **[AST-AUD-02] [🟠 P1 | C1.1 & C1.2 | All-OS] [`ys_codebase/source/ast/ast_engine/engine.py:L1375-L1415`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - `_resolve_symbol_node_for_slice` 在 `UnifiedSymbol` 轉 `SymbolNode` 時漏傳重載後綴，且 fallback 迴圈以 `cand.fqn == ...` 短路，導致重載方法切片永遠錯切至首個定義**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)（`ASTEngine._resolve_symbol_node_for_slice:L1375-L1415`）｜ 類別 `C1.1 / C1.2`（`UnifiedSymbol` 與 `SymbolNode` 雙軌轉換失步）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：當使用者對同名重載方法指定參數型別執行無損切片（如 `engine.slice_part("Window.Open(string, int)", part="body")`）時，`L1406` 的 `self.resolve(q_str)` 會精確解析出第 2 個重載的 `UnifiedSymbol`（例如位於 L50，而無參數的 `Window.Open()` 位於 L20），並於 `L1414` 將該 `UnifiedSymbol` 遞迴傳入 `_resolve_symbol_node_for_slice`。然而在 `L1384-L1387`：
       - `SymbolNode.compute_canonical_id(symbol_or_id.file_path, symbol_or_id.fqn or symbol_or_id.name)` **沒有傳入 `overload_suffix`**，而 [`treesitter.py:L1447-L1457`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) 對同檔同名重載節點的 `canonical_id` 均附加了 `({params})` 後綴，因此 `canonical_id in ws_graph.nodes_by_id` 必不命中。
       - 程式退入 `L1393-L1397` 迴圈：`if cand.fqn == (symbol_or_id.fqn or symbol_or_id.name) or (cand.span.start_line == symbol_or_id.line_number ...)`。由於同類別下所有重載的 `cand.fqn` 完全相同（皆為 `"UI.Window.Open"`），第一個條件 `cand.fqn == ...` 在遇到檔案內第 1 個重載（L20）時即恆為 `True` 並立即 `return cand`，完全無視 `symbol_or_id.line_number`（L50）！
       - 此外，若使用者未指定參數（如 `slice_part("Window.Open")`），`self.resolve()` 回傳 `status == "overload_group"`，但 `L1412` 僅攔截 `if res.status == "ambiguous":`，未提示重載歧義便靜默取 `res.targets[0]`。
    2. **上游呼叫方查驗**：[`cli.py:L522`](https://drive.google.com/file/d/1QFkpVeFwOH1jSPVT_lW-QXGRMLEOd3pf/view?usp=drivesdk) (`slice`) 與 [`engine.py:L1532`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) (`traverse_edges`) 均直接調用此方法。
    3. **設計意圖核對**：屬重構引入 `SymbolNode` 後，與既有 `UnifiedSymbol` 解析器對接時的條件優先序錯誤。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在將 `UnifiedSymbol` 映射至 `SymbolNode` 時，優先比對 `(cand.fqn == target_fqn and cand.span.start_line == symbol_or_id.line_number)`（精確對齊行號與 FQN），若無同列匹配再退回單一 FQN 匹配；同時支援帶重載後綴的 `compute_canonical_id` 查找。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/engine.py:L1382-L1398
      if isinstance(symbol_or_id, UnifiedSymbol):
          ws_graph = self.get_workspace_graph(auto_sync=True)
          target_fqn = symbol_or_id.fqn or symbol_or_id.name
          norm_fp = symbol_or_id.file_path.replace("\\", "/")
          fg = ws_graph.file_graphs.get(norm_fp) or ws_graph.file_graphs.get(symbol_or_id.file_path)
          if fg is None:
              fg = self.parse_file(symbol_or_id.file_path)
          # 1. Exact (fqn, start_line) match to disambiguate same-file overloads accurately
          for cand in fg.all_nodes_by_id.values():
              if cand.span.start_line == symbol_or_id.line_number and (
                  cand.fqn == target_fqn or cand.name == symbol_or_id.name.split(".")[-1]
              ):
                  return cand
          # 2. Direct canonical ID lookup
          canonical_id = SymbolNode.compute_canonical_id(norm_fp, target_fqn)
          if canonical_id in ws_graph.nodes_by_id:
              return ws_graph.nodes_by_id[canonical_id]
          # 3. Fallback to FQN match if line numbers shifted
          for cand in fg.all_nodes_by_id.values():
              if cand.fqn == target_fqn:
                  return cand
          raise ASTError(f"SymbolNode not found for UnifiedSymbol '{target_fqn}'")
      ```
- **[AST-AUD-03] [🟠 P1 | C1.2 | All-OS] [`ys_codebase/source/ast/ast_engine/linker.py:L180-L187, L758-L775, L848-L861, L928-L935`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) - `TopologyLinker` 與 `expand_contract_symbol_ids` 在限定名稱基底型別（`pkg.Base`）與雙軌 ID 空間（SHA-1 vs. Canonical URI）間發生契約斷裂**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/linker.py`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)（`TopologyLinker._reindex:L180-L187`、`_expand_contract_from_workspace_graph:L738-L845`、`expand_contract_symbol_ids:L848-L980`）｜ 類別 `C1.2`（跨模組/雙軌契約漂移）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - **(a) 限定基底型別名稱未正規化導致繼承鏈斷裂 (`linker.py:L180-L187, L928-L935`)**：在 `Unit 04` 的 [`treesitter.py:L661-L708`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) 中，`_extract_base_type_relations` 為支援 Pass 3 跨檔型別解析，保留了帶模組/命名空間前綴的基底型別字串（如 `base.BaseParser` 或 `Ns::IBase`）並寫入 `UnifiedSymbol.metadata["base_types"]`。然而 `Unit 03` 的 `TopologyLinker._reindex`（`L184-L186`）與 `expand_contract_symbol_ids`（`L932-L934`）直接以 `bt_str`（`"base.BaseParser"`）作為 `_class_bases[short_name]` 與 `_base_derived[bt_str]` 的鍵，而所有類別的 `_methods_by_class_and_short` 皆以無前綴的 `short_name`（`"BaseParser"`）為鍵！這導致所有寫為 `class Sub(pkg.Base):` 或 `class Sub : Ns::Base` 的繼承關係在 `TopologyLinker` 與 `expand_contract_symbol_ids` 中 100% 無法匹配。
       - **(b) `expand_contract_symbol_ids` 雙軌 ID 空間混用 (`linker.py:L761-L770, L857-L860`)**：當傳入含有 `.workspace_graph` 屬性的容器（如 `CallGraphIndex`）或直接傳入 `WorkspaceSymbolGraph` 搭配 `UnifiedSymbol` 時，`L857-L860` 轉調 `_expand_contract_from_workspace_graph`，其回傳值混雜了 `UnifiedSymbol.id`（40 字元 SHA-1）與 `SymbolNode.id`（`file::fqn` URI），且在 `L766` 對重載方法呼叫 `SymbolNode.compute_canonical_id` 時漏傳 `overload_suffix` 導致查無節點。
    2. **上游呼叫方查驗**：[`resolver.py:L839, L1022`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) (`query_callers`、`query_impact`) 與 [`engine.py:L846, L1031`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 均重度依賴此組件。
    3. **設計意圖核對**：屬 `Unit 04` 修改 `_extract_base_types` 輸出格式後，`Unit 03` 消費端未同步正規化 `short_base` 的跨單元契約失步。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `TopologyLinker._reindex` 與 `expand_contract_symbol_ids` 中，對 `base_types` 同時以原始 `bt_str` 與剝離限定前綴後的 `bt_short = re.split(r"[.:]+", bt_str)[-1].strip()` 建立雙向索引。
      2. 在 `_expand_contract_from_workspace_graph` 中，當 `rt` 為 `UnifiedSymbol` 且無直接 `cand_id` 命中時，退回比對 `(file_path, fqn/ line_number)` 以支援重載方法。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/linker.py:L180-L187 (並同步套用至 L928-L935)
      base_types = sym.metadata.get("base_types")
      if base_types and isinstance(base_types, (list, tuple)):
          for bt in base_types:
              if bt:
                  bt_str = str(bt).strip()
                  bt_short = re.split(r"[.:]+", bt_str)[-1].strip()
                  for b_key in ({bt_str, bt_short} if bt_short else {bt_str}):
                      self._class_bases[short_name].add(b_key)
                      self._base_derived[b_key].add(short_name)
      ```
- **[AST-AUD-04] [🟠 P1 | C1.1 & C2.2 | All-OS] [`ys_codebase/source/ast/ast_engine/bundler.py:L603-L622, L1006-L1008, L1022-L1024`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/engine.py:L646-L648`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - 多 Entry Roots 空間下增量熱修補對含 `/` 相對路徑跳過 `mtime` 消歧，且對刪除檔誤用已清空之快取，導致跨模組同名檔（如 `scripts/cli.py`）被連坐誤刪或全量重解析**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/bundler.py`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)（`_normalize_space_dirty_paths:L603-L622`、`_resolve_dirty_files_only:L1006-L1025`）與 [`ys_codebase/source/ast/ast_engine/engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)（`_collect_space_generations_and_files_map:L646-L648`）｜ 類別 `C1.1 / C1.3`（增量熱修補路徑消歧錯誤）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - 在 `bundler.py:L615`、`L1006`、`L1022` 中，當空間包含多個 Entry Roots（例如 YS-Codebase 的 `source` 空間映射了 `ys_codebase/source/core`、`ast`、`dev` 等 9 個模組根目錄），且傳入的髒檔相對路徑為 `"scripts/cli.py"` 或 `"scripts/hook.core.py"` 時，因為每個模組下都存在 `scripts/cli.py`，`existing_cands` / `snap_matches` / `inc_matches` 會同時命中 9 個檔案。但程式碼寫了 `if len(...) > 1 and "/" not in raw_p:`（及 `"/" not in clean_p`），誤以為只有不含 `"/"` 的純檔名才會在多 Entry Roots 間碰撞，導致 `"scripts/cli.py"` 跳過 `max_mtime` 消歧，把全部 9 個模組的 `scripts/cli.py` 當作髒檔淘汰並重解析！
       - 在 `bundler.py:L603-L613`，當檔案被刪除（`prefer_missing=True`）且無 `snap_matches` 時，程式試圖用 `_safe_resolve_str(c) in cache_ref`（即 `self._file_symbols_cache`）找出哪一個 Entry Root 原先擁有該檔案。然而 [`engine.py:L860, L1139`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 在每次建置或熱修補結束時都呼叫了 `self.bundler.clear_transient_caches()`，導致進入 `hot_patch_index` 時 `self._file_symbols_cache` **永遠是空字典 `{}`**！結果 `cached_missing` 恆為空，退回將所有不存在該路徑的 Entry Roots 展開加入 `expanded_deleted`。
       - 在 `engine.py:L646-L648`，`del_norm = normalize_dirty_paths(incremental_detail.deleted)` 未先透過 `_normalize_space_dirty_paths` 解析至具體模組路徑便直接呼叫 `is_dirty_file_match(p, del_norm)`；因 [`io_utils.py:L127`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk) 採用後綴匹配 `sym_path_norm.endswith("/" + p)`，若單一模組刪除 `scripts/cli.py`，`files_map` 中其餘 8 個模組的 `*/scripts/cli.py` 會被一併誤刪。
    2. **上游呼叫方查驗**：`ASTEngine.hot_patch_index` 與 `hook.core.py:on_file_space_changed` 為直接呼叫鏈。
    3. **設計意圖核對**：`bundler.py:L575-L576` 在處理 `snap_matches` 時並未加 `"/" not in raw_p` 限制，證明 `L615/L1006/L1022` 為不一致的防禦漏洞。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：移除 `L615`、`L1006`、`L1022` 中多餘的 `and "/" not in ...` 條件，只要多於一個 Entry Root 命中同一相對路徑即以 `mtime_ns` 取最新修改者；並在 `engine.py:L646` 與 `bundler.py` 中結合 `self._snapshot.file_to_symbol_ids`（持久化存活於記憶體的檔案映射）協助 `prefer_missing` 精準定位被刪除檔案所屬的 Entry Root。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/bundler.py:L614-L622 (同理移除 L1006, L1022 之 `and "/" not in clean_p`)
      else:
          if len(existing_cands) > 1:
              max_mtime = max((_safe_mtime_ns(c) for c, _ in existing_cands), default=0)
              existing_cands = [(c, r) for c, r in existing_cands if _safe_mtime_ns(c) >= max_mtime]
          cands_to_use = (
              existing_cands
              if len(existing_cands) >= 1
              else (matching_candidates if len(matching_candidates) == 1 or "/" in raw_p else existing_cands)
          )
      ```
- **[AST-AUD-05] [🟠 P1 | C1.1 & C4.2 | All-OS] [`ys_codebase/source/ast/ast_engine/bundler.py:L414-L420, L1109-L1126`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/linker.py:L1404-L1412, L1460-L1476`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) - `bundle_union` 多進程平行建置漏檢 `LanguageConfig` 擴充欄位導致子進程丟失規則，且 Pass 2 Barrel Re-export 受字母序限制並漏更新 `_resolved_import_edges`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/bundler.py`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)（`_get_worker_registry:L414-L420`、`bundle_union:L1109-L1126`）與 [`ys_codebase/source/ast/ast_engine/linker.py`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)（`WorkspaceGraphLinker._run_pass2_import_resolution:L1404-L1476`）｜ 類別 `C1.1 / C4.2`（平行/序列雙軌失步與順序相依）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - **(a) `bundle_union` 多進程 Worker 丟失注入之 `query_files` / `processors` / `spaces` (`bundler.py:L1109-L1117`)**：`has_custom_configs` 僅比對 `mode`、`grammar`、`query_file`、`parser_entry`、`extensions` 五個舊欄位，漏檢了重構新增的 `query_files`、`spaces`、`processors`、`module_resolver`、`edge_refiners` 以及 `self._contributes_data is not None`。當呼叫方注入自訂 `.scm` (`query_files`) 或 `SymbolProcessor` (`processors`) 且檔案數 $\ge 10$ 時，`use_parallel` 被誤判為 `True`，而子進程 `_get_worker_registry()` 建立的是預設 `ParserRegistry(register_defaults=True)`（無 `contributes_data`），導致子進程解析出的 `FileSymbolGraph` 完全不含擴充查詢與 Processor 精煉結果！
       - **(b) Pass 2 Barrel Re-export 單輪字母序走訪與 `_resolved_import_edges` 漏同步 (`linker.py:L1404-L1412, L1460-L1476`)**：在 `_run_pass2_import_resolution` 中，`self._resolved_import_edges` 於 `L1404` 寫入時，Barrel 模組（如 `__init__.py` 或 `index.ts`）的 `raw_bindings_by_file` 尚未完成 Wildcard（`L1432`）與 Re-export（`L1460`）展開，因此 `from pkg import MyClass` 的 `imports` 邊目標只指向 `pkg/__init__.py` 的 `root_nodes`（常為空 `()`）而非真正的 `pkg/core.py::MyClass`，且後續從未回填 `_resolved_import_edges`。此外，`L1461` 僅按檔名字母序單輪走訪 `raw_bindings_by_file`，若 `app.py` 匯入 `pkg/__init__.py` 而 `pkg/__init__.py` 再轉匯出 `pkg/sub/__init__.py`，因 `"app.py" < "pkg/__init__.py"`，處理 `app.py` 時 `pkg/__init__.py` 尚未解出 `resolved_symbol_ids`，導致多跳 Barrel 轉匯出解析失敗。
    2. **上游呼叫方查驗**：`ASTEngine.build_index`、`ASTEngine.hot_patch_index`、`ASTEngine.traverse_edges` (`--kind=imports`)。
    3. **設計意圖核對**：違反 Pass 2 確定性匯入解析與多進程透明加速之設計契約。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `bundler.py:L1109` 將 `self._contributes_data is not None` 以及 `cfg.query_files != ...`、`cfg.processors`、`cfg.spaces`、`cfg.module_resolver`、`cfg.edge_refiners` 納入 `has_custom_configs` 判斷。
      2. 在 `linker.py:L1460-L1476` 以不動點迴圈（Fixed-point loop，最多迭代至無新增變更）解析多跳 Barrel Re-export，並在完成後同步回填 `self._resolved_import_edges` 中指向 Barrel 模組的匯入邊。
    - **程式碼修改範例**：
      ```python
      # 1. ys_codebase/source/ast/ast_engine/bundler.py:L1109-L1118
      has_custom_configs = (
          self._contributes_data is not None
          or len(getattr(self.parser_registry, "_parsers", ())) > len(lang_cfgs)
          or any(
              lang_id not in DEFAULT_LANGUAGES
              or cfg.mode != DEFAULT_LANGUAGES[lang_id].get("mode", "tree_sitter")
              or cfg.grammar != DEFAULT_LANGUAGES[lang_id].get("grammar")
              or cfg.query_file != DEFAULT_LANGUAGES[lang_id].get("query_file")
              or tuple(cfg.query_files) != ((DEFAULT_LANGUAGES[lang_id]["query_file"],) if DEFAULT_LANGUAGES[lang_id].get("query_file") else ())
              or bool(cfg.spaces)
              or bool(cfg.processors)
              or bool(cfg.module_resolver)
              or bool(cfg.edge_refiners)
              or cfg.parser_entry != DEFAULT_LANGUAGES[lang_id].get("parser_entry")
              or tuple(cfg.extensions) != tuple(DEFAULT_LANGUAGES[lang_id].get("extensions", ()))
              for lang_id, cfg in lang_cfgs.items()
          )
      )

      # 2. ys_codebase/source/ast/ast_engine/linker.py:L1460-L1477
      changed = True
      while changed:
          changed = False
          for norm_path, b_dict in raw_bindings_by_file.items():
              for alias_k, b_val in list(b_dict.items()):
                  if not b_val.resolved_symbol_ids and b_val.resolved_file_path:
                      sym_tail = re.split(r"[.:/]+", b_val.target_expr)[-1].strip()
                      target_b_dict = raw_bindings_by_file.get(b_val.resolved_file_path, {})
                      if sym_tail in target_b_dict and target_b_dict[sym_tail].resolved_symbol_ids:
                          re_b = target_b_dict[sym_tail]
                          b_dict[alias_k] = FileImportBinding(
                              local_alias=b_val.local_alias,
                              target_expr=b_val.target_expr,
                              resolved_file_path=re_b.resolved_file_path or b_val.resolved_file_path,
                              resolved_symbol_ids=re_b.resolved_symbol_ids,
                              is_wildcard=b_val.is_wildcard,
                              is_external=False,
                              is_reexport=True,
                          )
                          changed = True
      ```
- **[AST-AUD-06] [🟠 P1 | C1.1 & C1.2 | All-OS] [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L69-L75, L1427-L1457`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/dialects/cpp.py:L67-L78`](https://drive.google.com/file/d/1R9JQ5AFvCVmhcm6aOcI2wC8ETkznXDso/view?usp=drivesdk) - C++ 命名空間內類外方法定義 (`ClassName::method`) 在 `SymbolNode` 中丟失類別作用域導致 `.h/.cpp` 配對失敗，且 Python `self.attr = ...` 重複賦值被當作方法重載附加偽簽名後綴**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`BUILTIN_QUERIES["python.scm"]:L69-L75`、`_build_recursive_symbol_nodes:L1405-L1457`）與 [`ys_codebase/source/ast/ast_engine/dialects/cpp.py`](https://drive.google.com/file/d/1R9JQ5AFvCVmhcm6aOcI2wC8ETkznXDso/view?usp=drivesdk)（`CppDialect.resolve_out_of_line_scope:L67-L78`）｜ 類別 `C1.1 / C1.2`（AST 階層建構與跨檔折疊契約失步）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - **(a) C++ `namespace` 內類外方法丟失類別名稱 (`treesitter.py:L1427-L1437` & `dialects/cpp.py:L67-L78`)**：當 `.cpp` 在 `namespace Ns { void MyClass::foo() {} }` 內定義類外方法時，外層 `stack` 使 `item["scope_path"]` 為 `["Ns"]`。`L1427` 呼叫 `resolve_out_of_line_scope` 回傳 `("foo", "MyClass", "method")` 後，`L1432` 將 `item["short_name"]` 改為 `"foo"`，但 `L1433` 卻寫成 `if parent_scope_val and not item["scope_path"]:`！因為 `item["scope_path"]` 非空（`["Ns"]`），`parent_scope_val`（`"MyClass"`）被完全丟棄，`item["fqn"]` 在 `L1437` 變成 `"Ns::foo"`（丟失 `"MyClass"`）；且若類外定義寫為 `Ns::MyClass::foo`，`dialects/cpp.py:L77` 只取 `cpp_parts[-2]` 而丟失前綴命名空間。這直接導致 `.cpp` 內 `SymbolNode.fqn`（`"Ns::foo"`）與 `.h` 標頭檔內 `SymbolNode.fqn`（`"Ns::MyClass::foo"`）不一致，使 `WorkspaceGraphLinker` Pass 1 的 `.h/.cpp` 配對（`linker.py:L1256-L1260`）失效！
       - **(b) Python `self.attr = ...` 重複賦值產生重複 `SymbolNode` 與偽重載 ID (`treesitter.py:L69-L75, L1405-L1457`)**：`python.scm:L69-L75` 將所有 `self.x = ...` 賦值語句捕獲為 `@definition.field`。當類別在多個方法對同一屬性賦值（例如 `ASTEngine` 在 4 處寫入 `self._snapshot = ...`）時，`_build_recursive_symbol_nodes` 將 4 處賦值全數加入 `ASTEngine.children`，使 `fqn_counts["ASTEngine._snapshot"] == 4`；接著 `L1447-L1452` 誤將欄位當作重載函式，從賦值右值（如 `self._snapshot = ASTSnapshot.from_dict(raw)`）提取出 `(raw)` 拼成 `engine.py::ASTEngine._snapshot(raw)`，而兩處 `self._snapshot = None` 更產生完全相同的 `canonical_id` 發生字典覆寫！
    2. **上游呼叫方查驗**：所有經由 `TreeSitterDriver.extract_file_graph` 與 `parse` 解析之 C++ 與 Python 檔案。
    3. **設計意圖核對**：C++ 類外定義應將拆出的類別路徑合併至 `scope_path`；Python 實例欄位應在同一容器內按名稱去重，且 `overload_suffix` 僅應對可呼叫符號（`callable_kinds`）生效。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `dialects/cpp.py:L77` 回傳完整的限定父路徑 `"::".join(cpp_parts[:-1])`；在 `treesitter.py:L1433` 將拆出的 `extra_scopes` 追加至既有 `item["scope_path"]`（去除重疊前綴）。
      2. 在 `_build_symbol_hierarchy` 與 `_build_recursive_symbol_nodes` 中，對附加至類別容器的 `field` 依 `short_name` 去重（保留首個定義或具備 `return_type` 型別註解者），且在 `L1447` 僅對 `item["kinds"] & callable_kinds` 附加 `overload_suffix`。
    - **程式碼修改範例**：
      ```python
      # 1. ys_codebase/source/ast/ast_engine/dialects/cpp.py:L67-L78
      def resolve_out_of_line_scope(
          self,
          name: str,
          parent_scope: str,
          kind: str = "",
      ) -> Tuple[str, str, str]:
          if "::" in name and kind in ("function", "method", ""):
              cleaned_name = self._strip_template_args(name)
              cpp_parts = [p.strip() for p in cleaned_name.split("::") if p.strip()]
              if len(cpp_parts) >= 2:
                  return cpp_parts[-1], "::".join(cpp_parts[:-1]), "method"
          return name, parent_scope, kind

      # 2. ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L1427-L1457
      short_name_val, parent_scope_val, resolved_kind = self.dialect.resolve_out_of_line_scope(
          name=item["short_name"],
          parent_scope=item["scope_path"][-1] if item["scope_path"] else "",
          kind=item["kind"],
      )
      item["short_name"] = short_name_val
      if parent_scope_val:
          extra_scopes = [p for p in parent_scope_val.split(scope_sep) if p]
          for es in extra_scopes:
              if not item["scope_path"] or item["scope_path"][-1] != es:
                  item["scope_path"].append(es)
      item["kinds"].add(resolved_kind)
      item["kind"] = self._select_primary_kind(item["kinds"])
      item["fqn"] = scope_sep.join(item["scope_path"] + [item["short_name"]])
      ```
- **[AST-AUD-07] [🟠 P1 | C1.1 & C2.3 | All-OS] [`ys_codebase/source/ast/ast_engine/parsers/registry.py:L383-L390`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L1263-L1270, L1805-L1806`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) - 當 `tree_sitter` 未安裝或語法動態庫不可用時，`ParserRegistry` 未降級掛載標準庫 `PythonASTParser` 與 `MarkdownParser`，導致無第三方套件環境下 `.py` 解析結果全空**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/parsers/registry.py`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk)（`ParserRegistry._load_from_contributes:L383-L390`）與 [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`L1263-L1270, L1805-L1806`）｜ 類別 `C1.1 / C2.3`（第三方依賴缺失時的防腐降級斷裂）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：在 [`python_ast.py:L2-L3`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk) 與 [`markdown.py:L2-L3`](https://drive.google.com/file/d/11uHvmCN_yIDGNT17HBrPO6SMcOqlQoYa/view?usp=drivesdk) 中，專案實作了零外部依賴的 `PythonASTParser`（基於標準庫 `ast`）與 `MarkdownParser`。然而在 `registry.py:L383-L390` 中，當 `cfg.mode == "tree_sitter"` 且 `driver._language is None or driver._parser is None`（例如環境未安裝 `tree_sitter` 或離線無法安裝 `tree-sitter-python` / `tree-sitter-markdown`）時，`ParserRegistry` 僅記錄 `self.load_errors[cfg.id]`，卻仍將空殼 `TreeSitterDriver` 註冊為唯一解析器。後續呼叫 `driver.parse()` 時，`PythonDialect.fallback_symbols` 回傳 `[]`，導致所有 Python 檔案解析出 0 個符號與 0 條邊！
    2. **上游呼叫方查驗**：全文檢索確認 `PythonASTParser` 與 `MarkdownParser` 除 `__init__.py` 匯出外，在 `registry.py` 與 `treesitter.py` 中為 0 引用。
    3. **設計意圖核對**：與 `python_ast.py` Docstring 明載之 *"Provides zero-external-dependency Python AST parsing when Tree-sitter is unavailable"* 設計目標直接背離。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：在 `registry.py:L383-L390` 中，當 `driver._language is None or driver._parser is None` 時，若 `cfg.id == "python"` 則自動實例化 `PythonASTParser` 並綁定 `extensions` / `SPACES` / `_processors` 後註冊；若 `cfg.id == "markdown"` 則自動降級註冊 `MarkdownParser`。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/parsers/registry.py:L383-L391
      if cfg.mode == "tree_sitter":
          driver = TreeSitterDriver(cfg, processors=tuple(proc_instances))
          self._bind_configured_extensions(driver, cfg.extensions)
          driver.SPACES = cfg.spaces
          if driver._language is None or driver._parser is None:
              err_msg = f"Failed to load tree-sitter grammar '{cfg.grammar}' or query '{cfg.query_file}'"
              self.load_errors[cfg.id] = err_msg
              fallback_parser: Optional[BaseParser] = None
              if cfg.id == "python":
                  from .python_ast import PythonASTParser
                  fallback_parser = PythonASTParser()
              elif cfg.id == "markdown":
                  from .markdown import MarkdownParser
                  fallback_parser = MarkdownParser()
              if fallback_parser is not None:
                  self._bind_configured_extensions(fallback_parser, cfg.extensions)
                  fallback_parser.SPACES = cfg.spaces
                  if proc_instances:
                      fallback_parser._processors = tuple(proc_instances)  # type: ignore[attr-defined]
                  self.register_parser(fallback_parser, priority=100)
                  continue
          self.register_parser(driver, priority=100)
      ```
- **[AST-AUD-08] [🟠 P1 | C1.1 & C2.1 | All-OS] [`ys_codebase/source/ast/ast_engine/parsers/base.py:L231-L286`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L838-L862`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) - `convert_legacy_symbols_to_file_graph` 將完整外框 `sp` 錯綁為 `parts["name"]` 且漏填 `signature`/`doc`/`body`，另 `TreeSitterDriver` 對無 `body` 之多行宣告截斷簽名並混用 Byte 長度作為 `end_col`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/parsers/base.py`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk)（`convert_legacy_symbols_to_file_graph:L231-L286`）與 [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`_extract_raw_definition_items:L838-L862`）｜ 類別 `C1.1 / C2.1`（L0 `slice_part` 位元組座標契約失步）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - 在 `parsers/base.py:L279`，`convert_legacy_symbols_to_file_graph` 建立 `SymbolNode` 時寫死 `parts={"name": sp}`（其中 `sp` 是涵蓋整個符號 `start_line..end_line` 的外框 `Span`），且完全未填入 `"signature"`、`"doc"`、`"body"`。這導致對所有 Custom Parsers（`SpiceParser`、`CssParser`、`HtmlParser`、`MarkdownParser`、`PythonASTParser`）產出的節點呼叫 `slice_part(..., part="name")` 時，會切出整個多行類別或函式本體；而呼叫 `part="signature"` 或 `part="doc"` 則永遠回傳空字串 `""`！
       - 在 `parsers/treesitter.py:L851-L862`，當宣告節點無 `body` 子節點（例如 C# `interface` 多行方法、C/C++ `.h` 跨行函式原型 `void Foo(\n int a,\n int b);`）時，`parts_spans["signature"]` fallback 僅取首行 `first_ln_len = nl if nl != -1 else len(raw_b)`，導致跨行參數列被截斷；同時 `L861` 將 UTF-8 byte 長度 `sig_trim_len` 直接加至字元欄位 `start_point[1]`，在含非 ASCII 字元時造成 `end_col` 失準。
    2. **上游呼叫方查驗**：`ASTEngine.slice_part`（[`engine.py:L1416-L1450`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)）直接讀取 `node.parts` 執行無損切片。
    3. **設計意圖核對**：`VALID_SLICE_PARTS` 明定支援 7 種結構部位切片，此處為新舊介面橋接與邊界計算缺失。
  - **建議解決方案（Recommended Solution）**：
    - **修改思路**：
      1. 在 `convert_legacy_symbols_to_file_graph` 中，精確定位首行內 `short_name` 的位元組區間作為 `parts["name"]`，首行作為 `parts["signature"]`，其餘行作為 `parts["body"]`。
      2. 在 `treesitter.py:L851-L862` 中，若無 `body` 子節點但存在 `parts_spans.get("parameters")` 或 `parts_spans.get("return_type")`，將 `signature` 的結束位元組延伸至涵蓋 `parameters` 與 `return_type` 的最大 `end_byte`（或修剪尾部 `;`/`{` 後的完整宣告區間）。
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L851-L863
      if "signature" not in parts_spans and def_node is not None:
          if "parameters" in parts_spans or "return_type" in parts_spans:
              sig_end_sp = parts_spans.get("return_type") or parts_spans["parameters"]
              if "parameters" in parts_spans and "return_type" in parts_spans:
                  sig_end_sp = parts_spans["parameters"].union(parts_spans["return_type"])
              parts_spans["signature"] = Span(
                  start_byte=int(def_node.start_byte),
                  end_byte=sig_end_sp.end_byte,
                  start_line=int(def_node.start_point[0]) + 1,
                  start_col=int(def_node.start_point[1]),
                  end_line=sig_end_sp.end_line,
                  end_col=sig_end_sp.end_col,
              )
          else:
              first_ln_len = nl if nl != -1 else len(raw_b)
              sig_slice = raw_b[:first_ln_len].rstrip(b" \t\r\n:{;")
              sig_trim_len = len(sig_slice)
              if sig_trim_len > 0:
                  sig_char_len = len(sig_slice.decode("utf-8", errors="replace"))
                  parts_spans["signature"] = Span(
                      start_byte=int(def_node.start_byte),
                      end_byte=int(def_node.start_byte) + sig_trim_len,
                      start_line=int(def_node.start_point[0]) + 1,
                      start_col=int(def_node.start_point[1]),
                      end_line=int(def_node.start_point[0]) + 1,
                      end_col=int(def_node.start_point[1]) + sig_char_len,
                  )
      ```


### 🟡 P2 - Medium（防禦缺口、序列化邊界與跨進程讀取一致性）
- **[AST-AUD-09] [🟡 P2 | C1.2 & C3.1 | All-OS] [`ys_codebase/source/ast/ast_engine/schema.py:L150-L167, L247-L267`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk) - `_freeze_facets_dict` 與 `SymbolNode.to_dict` 僅做單層淺轉換，當 `facets` 含巢狀容器時破壞不可變性或導致 `json.dumps` 拋出 `TypeError`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/schema.py`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk)（`_freeze_facets_dict:L150-L167`、`SymbolNode.to_dict:L247-L267`）｜ 類別 `C1.2`（序列化契約不一致）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：`_freeze_facets_dict` 在 `L158-L160` 將 `list` 轉為 `tuple(dict(x) if isinstance(x, Mapping) else x for x in v)`，使內層 `Mapping` 退化為可變 `dict`；且當 `v` 為巢狀 `Mapping`（內含 `list` / `set` / `MappingProxyType`，如 `LanguageConfig.symbol_folding` 或自訂 `SymbolProcessor` 寫入的複合 `facets`）時，`SymbolNode.to_dict()`（`L249-L255`）僅做單層 `dict(v)`，未遞迴將內層 `tuple`/`frozenset`/`MappingProxyType` 轉回 JSON 相容之 `list`/`dict`，導致 [`formatter.py:L735`](https://drive.google.com/file/d/1N89QaHI3Uu1a3ww3aL09ezgE5KA0qxFa/view?usp=drivesdk) (`format_traverse_output(..., as_json=True)`) 呼叫 `json.dumps` 時拋出 `TypeError`。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/schema.py:L150-L167
      def _freeze_value(val: Any) -> Any:
          if isinstance(val, (list, tuple)):
              return tuple(_freeze_value(x) for x in val)
          if isinstance(val, (set, frozenset)):
              return frozenset(_freeze_value(x) for x in val)
          if isinstance(val, Mapping):
              return MappingProxyType({str(k): _freeze_value(v) for k, v in val.items()})
          return val

      def _thaw_value(val: Any) -> Any:
          if isinstance(val, (tuple, list, set, frozenset)):
              return [_thaw_value(x) for x in val]
          if isinstance(val, Mapping):
              return {str(k): _thaw_value(v) for k, v in val.items()}
          return val
      ```
- **[AST-AUD-10] [🟡 P2 | C4.1 | All-OS] [`ys_codebase/source/ast/ast_engine/engine.py:L735-L788`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - `_save_snapshot_and_graph` 寫入端受 `InterProcessLock` 保護，但讀取端 `_ensure_loaded_from_disk` 無鎖連讀雙檔，跨進程併發下存在 `ASTSnapshot` 與 `CallGraphIndex` 世代撕裂風險**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)（`_save_snapshot_and_graph:L735-L753`、`_ensure_loaded_from_disk:L783-L788`）｜ 類別 `C4.1`（跨檔案原子性違背與世代撕裂）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：寫入端在 `InterProcessLock` 內先替換 `unified.symbols.bin.gz`，再壓縮並替換體積龐大的 `unified.graph.bin.gz`。若讀取進程在兩次替換之間呼叫 `_ensure_loaded_from_disk()`，將載入 Gen $N+1$ 的 `_snapshot` 與 Gen $N$ 的 `_graph`。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/engine.py:L783-L788
      def _ensure_loaded_from_disk(self, force_reload: bool = False) -> bool:
          if not self.symbols_index_path.exists() or not self.graph_index_path.exists():
              return False
          from core.platform.lock import InterProcessLock
          lock_file = str(self._resolve_index_lock_path())
          with InterProcessLock(lock_file, timeout=15.0):
              return self._ensure_symbols_loaded(force_reload=force_reload) and self._ensure_graph_loaded(
                  force_reload=force_reload
              )
      ```
- **[AST-AUD-11] [🟡 P2 | C1.1 | All-OS] [`ys_codebase/source/ast/ast_engine/parsers/registry.py:L529-L585`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L1220-L1230`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) - 交換律合流器在合併 `Mapping` 型別之 `facets`（如 `field_types`）時以字串比較覆寫而非鍵值聯集，且 `language`/`name` 取 `node_a` 違反交換律**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/parsers/registry.py`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk)（`_merge_symbol_nodes_commutative:L529-L585`）與 [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`_commutatively_merge_raw_items:L1220-L1230`）｜ 類別 `C1.1`（交換律合流不變量違背）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：當兩個 `.scm` 查詢或兩個 Parser 針對同一節點各自貢獻了 `Mapping` 類型的 `facets`（例如 `field_types`）時，`L545` 僅判斷 `(set, frozenset, list, tuple)`，導致 `Mapping` 落入 `elif str(fv) > str(merged_facets[fk]): merged_facets[fk] = fv` 被整包覆寫而非合併鍵值；且 `L575, L579` 直接取 `name=node_a.name`、`language=node_a.language`，若兩節點屬性不同則結果隨 `(node_a, node_b)` 順序改變。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/parsers/registry.py:L541-L549
      merged_facets = dict(node_a.facets)
      for fk, fv in node_b.facets.items():
          if fk not in merged_facets or not merged_facets[fk]:
              merged_facets[fk] = fv
          elif isinstance(merged_facets[fk], Mapping) and isinstance(fv, Mapping):
              combined_map = dict(merged_facets[fk])
              for mk, mv in fv.items():
                  if mk not in combined_map or str(mv) > str(combined_map[mk]):
                      combined_map[mk] = mv
              merged_facets[fk] = combined_map
          elif isinstance(merged_facets[fk], (set, frozenset, list, tuple)) and isinstance(fv, (set, frozenset, list, tuple)):
              merged_facets[fk] = tuple(sorted({str(x) for x in (*merged_facets[fk], *fv)}))
          elif str(fv) > str(merged_facets[fk]):
              merged_facets[fk] = fv
      ```
- **[AST-AUD-12] [🟡 P2 | C1.2 | All-OS] [`ys_codebase/source/ast/ast_engine/dialects/base.py:L147-L173`](https://drive.google.com/file/d/1MFfZA2sghRNbTnSs0knK9FIaxaZhcBDN/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L669-L706`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) - `normalize_call_receiver` 處理 `super().field.method()` 與 C++ `__super` 失準，且 `_extract_base_type_relations` 漏捕獲 TypeScript 介面繼承 `extends_type_clause`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/dialects/base.py`](https://drive.google.com/file/d/1MFfZA2sghRNbTnSs0knK9FIaxaZhcBDN/view?usp=drivesdk)（`DialectAdapter.normalize_call_receiver:L147-L173`）與 [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`_extract_base_type_relations:L669-L706`）｜ 類別 `C1.2`（多語言 Dialect 邊界提取）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：
       - 在 `dialects/base.py:L159-L172` 中，`super().helper.run()` 的 `raw_prefix` 為 `"super().helper."`，去尾點號後為 `"super().helper"`；因結尾不是 `")"`（`L159`）且開頭是 `"super()."` 而非 `"super."`（`L171`），未被正規化為 `"self.helper"`；而 C++ `__super::foo()` 轉為 `"__super"` 後未被正規化為 `"base"`，導致 `TopologyLinker._resolve_self_or_cls_call`（[`linker.py:L330`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)）無法識別。
       - 在 `treesitter.py:L670` 中，`child.type` 檢查清單缺少 `tree-sitter-typescript` 的 `"extends_type_clause"` 與 `"extends_clause"`，導致 TypeScript `interface Sub extends Base` 的 `inherits` 邊漏提。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # 1. ys_codebase/source/ast/ast_engine/dialects/base.py:L166-L173
      prefix = re.sub(r"^(?:super|base)\s*\([^)]*\)\.", "super.", prefix)
      if prefix == "this":
          return "self"
      if prefix in ("base", "super", "__super"):
          return "base"
      if prefix.startswith(("this.", "base.", "super.", "__super.")):
          return "self." + prefix.split(".", 1)[1]
      return prefix

      # 2. ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L670
      if child.type in ("base_list", "base_class_clause", "class_heritage", "extends_type_clause", "extends_clause", "argument_list"):
      ```
- **[AST-AUD-13] [🟡 P2 | C2.1 | All-OS] [`ys_codebase/source/ast/ast_engine/resolver.py:L251-L292`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) - `SymbolSelector.parse` 在處理含泛型或特殊符號前綴之選擇器（如 `method MyClass<T>.Run` 或 `class .btn`）走入 fallback 分支時，未剝離前導 `<kind>` 修飾詞**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/resolver.py`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)（`SymbolSelector.parse:L251-L292`）｜ 類別 `C2.1`（特殊字元與泛型選擇器退化輸入）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：當查詢字串包含 `<...>` 泛型、CSS `.class` / `#id` 或空白標題（如 `class .btn`、`method MyBox<int>.Get()`）時，`cls._PATTERN.match(clean_expr)`（`L265`）回傳 `None` 進入 `L266-L292` fallback 分支；該分支未檢查開頭是否存在 `KIND_PREFIX_MAP` 定義的 `<kind>` 空白前綴，導致 `"class .btn"` 被拆為 `scope="class "`、`identifier="btn"`、`target_kinds=None`。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/resolver.py:L265-L292
      m = cls._PATTERN.match(clean_expr)
      if not m:
          target_kinds: Optional[Set[str]] = None
          rem_expr = clean_expr
          parts_ws = clean_expr.split(None, 1)
          if len(parts_ws) == 2 and parts_ws[0].lower() in KIND_PREFIX_MAP:
              target_kinds = set(KIND_PREFIX_MAP[parts_ws[0].lower()])
              rem_expr = parts_ws[1].strip()
          is_call = rem_expr.endswith(")") and "(" in rem_expr
          params_tuple: Optional[Tuple[str, ...]] = None
          if is_call:
              p_start = rem_expr.find("(")
              base = rem_expr[:p_start].strip()
              p_inner = rem_expr[p_start + 1 : -1].strip()
              if p_inner:
                  params_tuple = tuple(_split_top_level_comma(p_inner))
          else:
              base = rem_expr
          scope = None
          norm_base = re.sub(r"<[^>]+>", "", base).replace("::", ".")
          if "." in norm_base and not norm_base.startswith("."):
              parts = norm_base.split(".")
              scope = ".".join(parts[:-1])
              name = parts[-1]
          else:
              name = norm_base
          return ParsedSelector(
              raw_query=clean_expr,
              identifier=name,
              scope=scope,
              target_kinds=target_kinds,
              is_callable=is_call or bool(target_kinds and target_kinds.issubset(CALLABLE_KINDS)),
              param_types=params_tuple,
          )
      ```


### 🔵 P3 - Optimization（效能加速、序列化瘦身與無損結構打磨）
- **[AST-AUD-14] [🔵 P3 | C7.1 & C7.2 | All-OS] [`ys_codebase/source/ast/ast_engine/schema.py:L412-L451, L570-L674`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk) - `FileSymbolGraph` 與 `WorkspaceSymbolGraph` 序列化重複儲存多份遞迴 `SymbolNode` 樹，且反序列化時重複實例化並丟棄 `all_nodes_by_id`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/schema.py`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk)（`FileSymbolGraph.to_dict/from_dict:L412-L451`、`WorkspaceSymbolGraph.__post_init__/to_dict/from_dict:L570-L674`）｜ 類別 `C7.1 / C7.2`（反序列化 CPU 與記憶體熱點）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：`FileSymbolGraph.__post_init__`（`L402-L410`）本身就會從 `root_nodes` 遞迴走訪自動建構 `all_nodes_by_id`，但 `FileSymbolGraph.to_dict()`（`L418`）卻將 `all_nodes_by_id` 完整序列化，而 `from_dict()`（`L434-L438`）又將其全部反序列化為 `SymbolNode` 後在 `__post_init__` 中被 `_walk_nodes(roots_tup)` 覆寫丟棄！同理，`WorkspaceSymbolGraph.__post_init__`（`L581-L584`）已支援從 `file_graphs` 自動彙整 `nodes_by_id`，但 `to_dict()`（`L652`）與 `from_dict()`（`L667`）卻又額外序列化與反序列化了一整份獨立的 `nodes_by_id`，造成快照體積與載入時間膨脹約 **3 倍**，且使 `ws_graph.nodes_by_id[id]` 與 `ws_graph.file_graphs[f].all_nodes_by_id[id]` 指向不同物件實例。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/schema.py:L423-L451 & L577-L585
      # 於 FileSymbolGraph.from_dict 中：若 raw_roots 非空，直接由 __post_init__ 的 _walk_nodes 衍生 all_nodes_by_id，免除重複反序列化
      # 於 WorkspaceSymbolGraph.__post_init__ 中：優先由 fg_map 內已建立的 fg.all_nodes_by_id 匯聚 nodes_map，僅補入不在 fg_map 中的額外節點
      nodes_map: Dict[str, SymbolNode] = {}
      for fg in fg_map.values():
          for nid, n in fg.all_nodes_by_id.items():
              nodes_map[nid] = n
      if isinstance(self.nodes_by_id, Mapping) and self.nodes_by_id:
          for k, v in self.nodes_by_id.items():
              k_str = str(k)
              if k_str not in nodes_map:
                  nodes_map[k_str] = v if isinstance(v, SymbolNode) else SymbolNode.from_dict(v)
      object.__setattr__(self, "nodes_by_id", MappingProxyType(nodes_map))
      ```
- **[AST-AUD-15] [🔵 P3 | C7.1 | All-OS] [`ys_codebase/source/ast/ast_engine/bundler.py:L437-L449, L908-L935`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) & [`ys_codebase/source/ast/ast_engine/engine.py:L841-L859`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) - 單檔解析在已提取 `FileSymbolGraph` 後仍重複執行 `_extract_raw_definition_items` 與 `extract_imports`，且 `build_index` 重複掃描空間檔案清單 3~4 次**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/bundler.py`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk)（`_parse_file_task_worker:L437-L449`、`_parse_file_full:L908-L935`、`extract_all_file_graphs:L1405-L1432`）與 [`ys_codebase/source/ast/ast_engine/engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)（`build_index:L841-L859`）｜ 類別 `C7.1`（重複解析與重複目錄走訪）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：在 `extract_all_file_graphs`（`bundler.py:L1411`）與 `_extract_call_sites_and_imports_core`（`bundler.py:L1340`）中，當 `self._last_bundle_unique_files` 已由 `bundle_union`（`bundler.py:L1090-L1091`）收集完畢且目標 `spaces` 相同時，仍重新呼叫 `self._collect_space_files(target_spaces)` 走訪空間檔案；且對繼承 `BaseParser` 的自訂解析器，`extract_file_graph`（`base.py:L373-L375`）已呼叫過 `parse`、`extract_call_sites`、`extract_imports`，外部緊接著又再呼叫一次。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/bundler.py:L1405-L1413
      def extract_all_file_graphs(
          self,
          spaces: Optional[List[Union[str, SpaceConfig]]] = None,
      ) -> Dict[str, FileSymbolGraph]:
          target_spaces = self._resolve_target_spaces(spaces)
          target_sp_names = {_space_logical_name(sp) for sp in target_spaces}
          if self._last_bundle_unique_files and target_sp_names == self._last_bundle_spaces:
              unique_files = self._last_bundle_unique_files
          else:
              unique_files = self._collect_space_files(target_spaces)
          ...
      ```
- **[AST-AUD-16] [🔵 P3 | C7.1 & C8.3 | All-OS] [`ys_codebase/source/ast/ast_engine/parsers/python_ast.py:L110-L290, L314-L361`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk) - `PythonASTParser` 缺少函式內巢狀定義提取，且 `extract_call_sites` 對多層屬性呼叫（如 `self.a.b()`）丟失 `context_prefix`**
  - **問題座標與分類**：[`ys_codebase/source/ast/ast_engine/parsers/python_ast.py`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk)（`_visit_block:L233-L289`、`extract_call_sites:L320-L335`）｜ 類別 `C7.1 / C8.3`（與 `TreeSitterDriver` 行為對齊度）｜ 影響平台：`All-OS`
  - **三步反向查證與觸發根因分析**：
    1. **精確定位**：`python_ast.py:L233-L289` 在解析 `FunctionDef` / `AsyncFunctionDef` 後未遞迴呼叫 `_visit_block(node.body, fqn_parts, fn_id, kind_val)`，導致函式內部的 helper 函式或局部類別漏提；且 `L324-L333` 僅展開 1~2 層 `py_ast.Attribute`，當遇到 `self.bundler.bundle_union()` 等三層以上鏈式呼叫時，`prefix` 變為空字串 `""`。
  - **建議解決方案（Recommended Solution）**：
    - **程式碼修改範例**：
      ```python
      # ys_codebase/source/ast/ast_engine/parsers/python_ast.py:L322-L335
      elif isinstance(node.func, py_ast.Attribute):
          callee_name = node.func.attr
          attr_parts: List[str] = []
          curr_val: Any = node.func.value
          while isinstance(curr_val, py_ast.Attribute):
              attr_parts.insert(0, curr_val.attr)
              curr_val = curr_val.value
          if isinstance(curr_val, py_ast.Name):
              root_id = "base" if curr_val.id == "super" else curr_val.id
              attr_parts.insert(0, root_id)
          elif (
              isinstance(curr_val, py_ast.Call)
              and isinstance(curr_val.func, py_ast.Name)
              and curr_val.func.id == "super"
          ):
              attr_parts.insert(0, "base")
          prefix = ".".join(attr_parts)
      ```


## 3. 已排除之假陽性與刻意設計核對紀錄 (Verified Safe & Rejected False Positives)

- **[AST-RFP-01] [`ys_codebase/source/ast/ast_engine/__init__.py:L163-L171`](https://drive.google.com/file/d/1kHv49lpzfJ4UAKrc0D0YKRnbyDpxX17y/view?usp=drivesdk)（PEP 562 延遲載入與冷啟動保護 `C7.3`）**：初看頂層匯出多達 73 個符號疑似拖慢冷啟動，經查驗確認全數封裝於 `MappingProxyType` 並由模組級 `__getattr__` 按需動態載入，匯入 `ast_engine` 時零第三方套件開銷。
- **[AST-RFP-02] [`ys_codebase/source/ast/ast_engine/io_utils.py:L70-L84`](https://drive.google.com/file/d/1dLoIiy_vUU2tgEX1hzd7CwXiltHn1Vv_/view?usp=drivesdk)（三平台原子替換與 `EXDEV` 防護 `C2.2 / C4.1`）**：`atomic_save_gzip_pickle` 統一透過 `core.vfs.write_bytes` 執行同目錄暫存檔寫入與原子替換，已妥善規避容器環境跨掛載點 `/tmp` 之 `EXDEV` 錯誤與 Windows `WinError 32` 檔案鎖衝突。
- **[AST-RFP-03] [`ys_codebase/source/ast/ast_engine/engine.py:L1255-L1271`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk)（`ensure_jit_synced` 對非 AST 可解析檔案跳過熱修補 `C1.1`）**：當空間內僅有非 AST 納管副檔名（如純設定檔）變更時，`has_parseable` 為 `False`，僅推進 `consume_diff` 游標而不觸發 `hot_patch_index`，確認為刻意設計之 I/O 節流機制。
- **[AST-RFP-04] [`ys_codebase/source/ast/ast_engine/linker.py:L1632-L1658`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)（`WorkspaceGraphLinker` Pass 3 繼承圖循環剪枝 `C2.1 / C7.1`）**：在建立 `_type_bases_by_id` 與 `_type_derived_by_id` 前，以 `_can_reach(b_id, s_id)` 嚴格阻斷惡意或語法錯誤造成的循環繼承（如 `A -> B -> A`），保證後續 Pass 4 MRO/BFS 遍歷 100% 終止。
- **[AST-RFP-05] [`ys_codebase/source/ast/ast_engine/linker.py:L1431-L1459`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk)（`WorkspaceGraphLinker` Pass 2 Wildcard Import 循環防護 `C2.1`）**：展開 `from X import *` 與 `export * from` 時以 `visited_wild: Set[str] = {norm_path}` 執行去重 BFS，確認不會因雙向星號匯入陷入無窮迴圈。
- **[AST-RFP-06] [`ys_codebase/source/ast/ast_engine/parsers/treesitter.py:L415-L416, L1115-L1139`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk)（`TreeSitterDriver._get_bytes_and_matches` 執行緒安全 `C4.1`）**：雖然底層 C 擴充 `tree_sitter.Parser` 本身非執行緒安全，但 `_get_bytes_and_matches` 全程以 `with self._cache_lock:` (`threading.RLock`) 保護 `self._parser.parse` 與 `QueryCursor.matches`，確認無併發競態。
- **[AST-RFP-07] [`ys_codebase/source/ast/ast_engine/provisioner.py:L164-L180`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk)（`GrammarProvisioner` 子進程命令安全與 `--json` 純淨度隔離 `C6.2`）**：採用參數陣列 `[sys.executable, "-m", "pip", "install", ...]` 呼叫（無 Shell 注入風險），並強制將 `stdout=sys.stderr, stderr=sys.stderr` 重導向，確保 CLI `--json` 輸出不被 pip 訊息污染。
- **[AST-RFP-08] [`ys_codebase/source/ast/ast_engine/resolver.py:L712-L722`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk)（`SnippetExtractor._file_lines_cache` 記憶體上限與失效控制 `C1.3 / C7.2`）**：快取鍵同時校驗 `st_mtime_ns`（檔案一經修改即重新讀取），且具備 32 檔上限之 FIFO 淘汰機制，無快取失步或無界記憶體增長問題。

## 5. Track 3 分級處方與查證詳情：`Unit 05` & `Unit 06` (`module:knowledge-db`)

### 🔴 P0 - Critical（資料損毀 / 雙軌狀態永久失步）
- **[KDB-AUD-01] [🔴 P0 | C1.1 & C1.3 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:L670-L708`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `hot_patch_unified_index` 處理 C# `partial class` 跨檔擴展時，會將未修改主檔加入 `dirty_keys` 卻漏收集同檔其餘符號，導致主檔非 partial 符號被永久清空**
  - **問題座標與分類**：[`pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)（`IndexingPipeline._collect_all_dirty_files` `L670-L708`、`_evict_dirty_file_artifacts` `L710-L722`、`_hot_patch_unified_index_locked` `L863-L871`）｜ `C1.1` 雙軌路徑漏同步、`C1.3` 索引狀態損毀 ｜ `All-OS`
  - **三步反向查證與觸發根因**：
    1. 假設 `FileA.cs` 內含 `partial class MyService` 與一般類別 `class HelperA`。當新增第二個分部檔 `FileB.cs`（定義 `partial class MyService`）時，`diff_detail.dirty_files` 僅含 `{"FileB.cs"}`。在 `L673-L683` 掃描舊 `_unified_index` 時，舊的 `MyService` 尚無 `"FileB.cs"` 於 `partial_files` 中，因此 `L685` 計算出的 `dirty_paths_norm` 僅含 `{"FileB.cs"}`。
    2. 接著在 `L688-L706` 走訪新 `snapshot.symbols.values()` 時，`HelperA`（位於 `FileA.cs`）因不匹配 `dirty_paths_norm`（僅含 `FileB.cs`）而被略過；但 `MyService`（主路徑為 `FileA.cs`、新 `partial_files` 含 `["FileA.cs", "FileB.cs"]`）在 `L695` 命中 `partial_files`，並於 `L706` 執行 `dirty_keys.add(sym.file_path)` 將 `"FileA.cs"` 加入 `dirty_keys`。此外，若新增的是排序更前面的 `File0.cs`（使聚合主檔由 `FileA.cs` 變更為 `File0.cs`），`L706` 僅執行 `dirty_keys.add(sym.file_path)` 而未將 `sym.metadata["partial_files"]` 加入 `dirty_keys`，導致舊主檔 `FileA.cs` 上的舊聚合符號未被淘汰而產生雙份幽靈符號。
    3. 隨後 `L864-L870` 將擴張後的 `dirty_keys`（含 `"FileA.cs"`）傳入 `_evict_dirty_file_artifacts(dirty_keys)` 與 `self._unified_index.patch_incremental(dirty_file_paths=dirty_keys, new_symbols=all_new_symbols, pre_aggregated=True)`，將 `FileA.cs` 下所有舊符號（含 `HelperA`）全數從 BM25 倒排索引與 `VectorIndex` 刪除，卻僅補回 `MyService`，造成 `FileA.cs` 其餘未修改符號在索引中永久遺失。
  - **建議解決方案（Recommended Solution）**：
    ```python
    # ys_codebase/source/knowledge-db/knowledge_db/pipeline.py (L668-L708)
    # 第一階段：先在舊 _unified_index 與新 snapshot.symbols 上雙向收斂所有受波及之 partial_files 與 file_path
    dirty_paths_norm = normalize_dirty_paths(dirty_keys)
    for raw_sym in snapshot.symbols.values():
        partial_files = (raw_sym.metadata or {}).get("partial_files") or []
        cs_key = (
            (",".join(sorted(raw_sym.spaces)) if raw_sym.spaces else "", raw_sym.kind, raw_sym.fqn or raw_sym.name)
            if raw_sym.language in ("c_sharp", "csharp") and raw_sym.kind in ("class", "struct", "interface")
            else None
        )
        if (
            is_dirty_file_match(raw_sym.file_path, dirty_paths_norm)
            or any(is_dirty_file_match(str(pf), dirty_paths_norm) for pf in partial_files)
            or (cs_key is not None and cs_key in affected_cs_keys)
        ):
            dirty_keys.add(raw_sym.file_path)
            for pf in partial_files:
                dirty_keys.add(str(pf))
            if cs_key is not None:
                affected_cs_keys.add(cs_key)

    # 第二階段：以最終收斂之 dirty_paths_norm 收集所有受影響檔案的全部符號
    dirty_paths_norm = normalize_dirty_paths(dirty_keys)
    all_new_symbols: List[UnifiedSymbol] = []
    seen_ids: Set[str] = set()
    for raw_sym in snapshot.symbols.values():
        sym = self._filter_symbol_for_indexed_spaces(raw_sym, indexed_spaces)
        if sym is None:
            continue
        partial_files = (sym.metadata or {}).get("partial_files") or []
        if is_dirty_file_match(sym.file_path, dirty_paths_norm) or any(
            is_dirty_file_match(str(pf), dirty_paths_norm) for pf in partial_files
        ):
            if sym.id not in seen_ids:
                seen_ids.add(sym.id)
                all_new_symbols.append(sym)
    ```

### 🟠 P1 - High（前景/背景競態失步、跨模組契約漂移、雙水位線錯位）
- **[KDB-AUD-02] [🟠 P1 | C4.1 & C1.3 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:L1268-L1276`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - 當背景 `KnowledgeDBServiceWorker` 處於常駐空閒 (`worker_active=True, worker_busy=False`) 時，前景 `search` 無條件跳過 JIT 增量同步並直接回傳陳舊索引**
  - **觸發根因**：`L1269` 條件寫為 `if worker_active or worker_busy:`。只要背景服務處於啟動狀態（即使 `worker_busy == False` 完全空閒），檔案修改後立即執行 `search` 會直接載入舊索引返回而不執行 `_ensure_jit_index_ready_locked`。
  - **建議解決方案**：將 `L1269` 短路條件改為 `if worker_busy:`，讓空閒狀態下前景可直接非阻塞取得 `_index_lock` 完成毫秒級熱修補。
- **[KDB-AUD-03] [🟠 P1 | C1.1 & C1.2 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:L435-L448`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - `build_unified_index(force=False)` 於 `unified.index.bin.gz` 存在時直接短路返回，無視待同步空間變更與缺失的向量索引，且未同步 `_GLOBAL_INDEX_CACHE`**
  - **建議解決方案**：在 `not force and bin_file.exists()` 分支中，同時檢驗 `idx.acked_ast_generation == self.get_current_ast_generation()` 以及向量缺口 `get_vector_deficit_info()["missing_count"] == 0` 後才可短路返回。
- **[KDB-AUD-04] [🟠 P1 | C1.1 & C1.3 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/pipeline.py:L648-L666, L871`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) - 當 `ASTEngine` 先行推進多個世代時，`hot_patch_unified_index` 僅修補局部 `diff_detail` 卻將 `acked_ast_generation` 直接覆寫為最新 `ast_generation`**
  - **建議解決方案**：呼叫 `ensure_jit_synced` 前記錄 `pre_ast_gen = self.get_current_ast_generation()`；若存在未納入本次 `diff_detail` 的世代跳躍（`pre_ast_gen > current_acked_gen` 且 `snapshot.ast_generation - current_acked_gen > 1`），觸發回退全量重建 BM25。
- **[KDB-AUD-05] [🟠 P1 | C1.1 & C1.2 | All-OS] [`ys_codebase/source/knowledge-db/scripts/hook.ast.py:L10-L34`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) - `on_register_ast_spaces` 僅讀取 `core_contributes.get("knowledge-db")` 之 `dict` 型態，漏讀專案級 `config://knowledge-db/contribute.json` 與 `list` 型態貢獻**
  - **建議解決方案**：與 [`engine.py:L337-L394`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk) 對齊，在 `hook.ast.py` 中同步解析 `list` 型態貢獻與 `config://knowledge-db/contribute.json` 的 `space_weights` / `spaces`。
- **[KDB-AUD-06] [🟠 P1 | C1.1 & C2.1 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/formatter.py:L114-L142`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) - `UniversalRedundancyFilter.purify_lines` 以子字串 `"/*" in stripped` 判定多行註解，遇含 `"src/*"` 等字串之程式碼會吞噬後續所有切片代碼**
  - **建議解決方案**：改為檢查 `stripped.startswith(q)`，並在單行閉合註解被剔除時直接 `continue` 外層迴圈。
- **[KDB-AUD-07] [🟠 P1 | C1.1 & C2.1 | All-OS] [`ys_codebase/source/knowledge-db/knowledge_db/hybrid.py:L157-L185`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk) & [`selector.py:L186-L206`](https://drive.google.com/file/d/148p_sUneWNWzkpkr51aNwwS7POjYe45Y/view?usp=drivesdk) - 向量檢索先取全域 Top-30 再過濾空間/語言/類型導致篩選餓死，且 `SymbolSelector` 誤吞雙詞查詢首詞**
  - **建議解決方案**：當帶有過濾條件時放大 `vector_index.search` 的 `top_k` 至全池並於過濾後截斷至 `fetch_limit`；在 `SymbolSelector.parse` 中當 `kind_str` 不在 `KIND_PREFIX_MAP` 時保留完整 `clean_expr`。

### 🟡 P2 & 🔵 P3 - Medium & Optimization (`KDB-AUD-08` ~ `14`)
- **[KDB-AUD-08] [🟡 P2 | C1.2 & C2.1 | All-OS] [`config.py:L122-L153, L232-L240`](https://drive.google.com/file/d/111Qj35vYsej9Zd0JrLkEgdkfG6QmmLAX/view?usp=drivesdk) & [`schema.py:L20-L37`](https://drive.google.com/file/d/1NQhH7d0ndfViI-pk6oj-wbJw7wzXQ-uK/view?usp=drivesdk)**：`KnowledgeDBConfig.load` 合併 `local_config` 時對互斥單位鍵（`jit_vector_timeout_ms` vs `jit_vector_timeout_seconds`）執行互斥清除，並在 `validate_space_weights` 加入 `not math.isfinite(w)` 與 `OverflowError` 攔截。
- **[KDB-AUD-09] [🟡 P2 | C1.3 & C4.1 | All-OS] [`pipeline.py:L1212-L1225`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) & [`service.py:L212-L268`](https://drive.google.com/file/d/1-d5Z8_Ejlus4zHLSMGWxH8jKMGPFft1r/view?usp=drivesdk)**：`_clean_locked` 加 `_kdb_index_file_lock` 保護且在常駐 Worker 活躍時不覆寫 `worker_running=False`；對齊 `service.py` 的 `invalidate_cell_state("kdb.worker_state")` 鍵名。
- **[KDB-AUD-10] [🟡 P2 | C1.1 & C2.1 | All-OS] [`embedding.py:L560-L573`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk)**：`VectorIndex.load_binary` 在 `doc_ids == []` 且 `vectors is not None` 時仍應呼叫 `idx.build` 還原 `model_name` 與 `dim`。
- **[KDB-AUD-11] [🟡 P2 | C1.1 | All-OS] [`retrieval.py:L1139-L1188`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk)**：`BM25Engine.search_aggregated` 移除 `elif len(unique_files) < target_limit:` 的過早截斷，於計算完 `total_score` 排序後再取 `[:target_limit]`。
- **[KDB-AUD-12] [🟡 P2 | C2.2 | macOS / Windows] [`formatter.py:L207-L250`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk)**：`ResultFormatter.__init__` 將 `self.workspace_root` 正規化為 `Path(workspace_root).resolve()`，相容 macOS `/var -> /private/var`。
- **[KDB-AUD-13] [🔵 P3 | C7.1 & C2.1 | All-OS] [`pipeline.py:L1496-L1519`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)**：`_filter_symbol_for_indexed_spaces` 在 `if not indexed_spaces: return sym` 早退，並由外部迴圈預傳 `weights` 消除每符號重複字典拷貝。
- **[KDB-AUD-14] [🔵 P3 | C7.3 | All-OS] [`pipeline.py:L932-L937`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) & [`engine.py:L595-L600, L751-L774`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk)**：`status` / `model_status` 與 `get_vector_deficit_info` 改用 `_dimension or _resolve_dimension_mock()` 查表取得維度，避免狀態查詢觸發 ONNX 模型同步載入。

### ✅ Track 3 已排除之假陽性與刻意設計 (`KDB-RFP-01` ~ `06`)
- **`[KDB-RFP-01]` [`knowledge_db/__init__.py:L90-L101`](https://drive.google.com/file/d/1snz_0tyMCDaAjlSiu_OBH27h_dsWe2zv/view?usp=drivesdk)**：PEP 562 延遲匯入確保零第三方套件頂層開銷。
- **`[KDB-RFP-02]` [`pipeline.py:L90, L216, L594`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)**：`_index_lock`、`_CACHE_LOCK` 與 `_kdb_index_file_lock` 呈嚴格單向 DAG 順序，無 AB-BA 死鎖風險。
- **`[KDB-RFP-03]` [`pipeline.py:L399, L605`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)**：`current_files` 與 `full_files_map` 為向後相容關鍵字參數。
- **`[KDB-RFP-04]` [`pipeline.py:L996-L1121`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk)**：`sync_vector_deficit_step` 鎖外推論後重入鎖內已二次校驗 `if sid in current_sym_ids:`。
- **`[KDB-RFP-05]` [`io_utils.py:L6-L11`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk)**：二進位索引存放於本機 `.storage.local/knowledge-db/indices/` 並受跨進程鎖保護。
- **`[KDB-RFP-06]` [`engine.py:L927-L963`](https://drive.google.com/file/d/1nC0BzPrYNvKiVx4zj3sMgtKGDka5Y4a3/view?usp=drivesdk)**：`get_engine()` 每次重新讀取 `KnowledgeDBConfig.load()` 並在模型名稱變更時重置快取。

## 6. Track 4 分級處方與查證詳情：`Unit 07` & `Unit 08` (`module:server`、`module:dev`、`module:vscode-support`)

### 🔴 P0 - Critical（高危阻斷：並發競態導致 IPC 管道吞包與死鎖）
- **[SRV-AUD-01] [🔴 P0 | C4.1 & C4.2 | All-OS] [`ys_codebase/source/server/server/master.py:L888-L915, L1011-L1054`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) - WarmWorker 閒置期間背景服務發送 IPC 控制封包與前景任務派發缺乏 stdout 讀取交接同步，存在管道緩衝區塞滿與雙執行緒同時 `readline()` 吞包死鎖風險**
  - **問題座標與分類**：[`master.py`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)（`MasterSupervisor._read_worker_handshake` `L1011-L1054` 與 `_stream_task_over_worker_pipe` `L879-L940`）｜ `C4.1 / C4.2 / C5.2` ｜ `All-OS`
  - **三步反向查證與觸發根因**：
    1. **閒置期管道無人消費**：`_read_worker_handshake` 在收到 `worker_ready` 後即 `break`（`L1050`）退出。當 Worker 處於 Idle 狀態時，Master 端無任何執行緒讀取 `proc.stdout`，而 Worker 內的背景服務（`CoreSpaceWatcherServiceWorker`、`knowledge-db-worker`、`gdrive-sync`）持續透過 `_WorkerIPCLinkSink` 與 `set_state` 向 `proc.stdout` 寫入 `log` 與 `service_status` 封包。長時間無前景任務時會填滿 OS 匿名管道緩衝區（Windows 4KB、Linux 64KB），導致背景執行緒阻塞於 `ipc_out.write()` 並鎖死 `ipc_lock`（[`worker.py:L337`](https://drive.google.com/file/d/1YDMnio1KHGj52Tiro48e18u6i4NNYN9p/view?usp=drivesdk)）。
    2. **Pre-warm 交接雙重 Reader 競態**：`ready_event.set()`（`L1046`）觸發時，若 `dispatch_task` 立即進入 `_stream_task_over_worker_pipe` 呼叫 `proc.stdout.readline()`（`L898`），缺乏單一 Owner Demuxer 隔離。
  - **建議解決方案（Recommended Solution）**：
    - 將 `proc.stdout` 交由單一常駐 Per-Worker Demuxer 執行緒 `_read_worker_stdout_loop` 獨佔讀取：即時消費 `worker_alive`、`worker_ready` 與背景控制封包（`log`、`service_status`、`touch_activity`），並將任務輸出封包（`stream`、`task_finish`）推入 `self._active_task_queue: Queue` 供 `_stream_task_over_worker_pipe` 消費。

### 🟠 P1 - High（TOCTOU 誤殺、Windows 句柄衝突、孤兒鎖凍結、平行沙盒修剪與 Zip Slip）
- **[SRV-AUD-02] [🟠 P1 | C4.1 & C4.2 | All-OS] [`ys_codebase/source/server/server/master.py:L747-L770, L1143-L1166`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk) - `restart_worker()` 與 RSS 自動回收存在「先無鎖檢查後殺進程」之 TOCTOU 競態，會誤殺剛進場的前景任務並重設 `_last_active_time` 導致 Idle TTL 永不觸發**
  - **建議解決方案**：為 `restart_worker` 新增 `if_idle_only: bool = False, touch_activity: bool = True` 參數；由 `_evaluate_worker_memory_health` 呼叫時先以 `self._dispatch_lock.acquire(blocking=False)` 取得派發鎖並二次驗證 `_is_worker_completely_idle()`，且不重設 `self._last_active_time`。
- **[SRV-AUD-03] [🟠 P1 | C2.2 & C4.2 | Windows] [`ys_codebase/source/server/scripts/cli.py:L182-L197`](https://drive.google.com/file/d/12wcSafrN6hCft_BsAK9629zEqYhpJDEe/view?usp=drivesdk) - `server stop` 優雅關閉等待上限 2.0s 小於 Master 內部關閉耗時（`watcher 1s + worker 2s = 3s`），過早觸發強制擊殺並跨進程同開 `ServerLogger` 造成 Windows `WinError 32`**
  - **建議解決方案**：將 `L182` 等待迴圈由 `range(20)`（2.0s）提升至 `range(45)`（4.5s），並於強制擊殺後確認進程已終止且鎖已釋放再執行 `archive_and_close()`。
- **[SRV-AUD-04] [🟠 P1 | C1.1 & C2.2 | macOS / All-OS] [`ys_codebase/source/server/server/space_watcher.py:L134-L144, L292-L340`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk) - `is_transaction_locked()` 對 `p_root / ".yscb.lock"` 僅判斷 `.exists()` 未以 `InterProcessLock` 探測持有狀態導致永久凍結，且 `_match_prefix_rel` 在 macOS `/private/var` 下切片位移算錯 1 字元**
  - **建議解決方案**：將 `p_root / ".yscb.lock"` 併入 `lock_candidates` 統一用 `InterProcessLock(str(lock_cand)).acquire(blocking=False)` 探測；將 `_match_prefix_rel` 的 `raw_str[8:]` 修正為保留前導斜線之 `raw_str[7:]`（或對稱剝離 `/private`）。
- **[SRV-AUD-08] [🟠 P1 | C4.1 | All-OS] [`ys_codebase/source/dev/dev/testing/sandbox.py:L211-L234, L507-L518`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) - `dev test --all` 多執行緒平行建置 >8 個沙盒時，`_allocate_sandbox_root` 在鎖外呼叫 `prune_sandboxes(max_keep=8)` 存在誤刪同批次活躍沙盒風險**
  - **建議解決方案**：將 `_sweep_sandboxes` 的保留數量設為 `effective_keep = max(max_keep, len(SandboxProvisioner._ACTIVE_SANDBOXES) + 2)`，並以進程級共享集合保護活躍沙盒清單。
- **[SRV-AUD-09] [🟠 P1 | C6.1 | All-OS] [`ys_codebase/source/dev/dev/testing/sandbox.py:L578-L580`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk) - `_deploy_target_and_dependency_modules` 直接呼叫 `zf.extractall(dest_mod)` 未做成員路徑邊界校驗（Zip Slip 風險）**
  - **建議解決方案**：解壓前逐一驗證 `os.path.realpath(os.path.join(dest_mod, member))` 位於 `os.path.realpath(dest_mod)` 之下。
- **[SRV-AUD-10] [🟠 P1 | C1.1 & C3.3 | All-OS] [`ys_codebase/source/vscode-support/vscode_support/projector.py:L353-L386`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk) - `_resolve_workspace_exclude_patterns` 在預設 `include_all=False` 下因恆真條件 `or pat in merged` 丟棄所有 `core.space` 動態轉譯之排除規則**
  - **建議解決方案**：將 `translated` 中不在 `merged` 的項目依序追加至 `merged` 後回傳。

### 🟡 P2 & 🔵 P3 - Medium & Optimization (`SRV-AUD-05` ~ `07`, `11` ~ `14`)
- **[SRV-AUD-05] [🟡 P2 | C1.2 & C4.1 | All-OS] [`server/service.py:L202-L229`](https://drive.google.com/file/d/1a1Q4sx6sMcWXZ-UzqDumMnVH8MinyVJz/view?usp=drivesdk) & [`server/master.py:L439-L478`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)**：`BaseServiceWorker.set_state` fallback 通知補齊 `"busy"` 欄位，並在 `MasterSupervisor` 原子更新 `_worker_services`。
- **[SRV-AUD-06] [🟡 P2 | C1.3 & C3.2 | Windows / All-OS] [`server/space_watcher.py:L729-L775`](https://drive.google.com/file/d/1ZPU73PGyq4MEXqau9FPrvIrWPCpBaI6H/view?usp=drivesdk)**：`sync_watched_directories()` 記錄 `ObservedWatch` 並在臨時空間移除時呼叫 `self._observer.unschedule(watch_obj)` 釋放 Windows 目錄句柄。
- **[SRV-AUD-07] [🟡 P2 | C1.1 | All-OS] [`server/watcher.py:L81-L99`](https://drive.google.com/file/d/1HPg_sG_c-i2OI1Z7U1MDC4M8-mIi9dba/view?usp=drivesdk)**：`ModulesWatcher._is_core_transaction_locked()` 同步納入 `os.path.join(yscb_root, ".yscb.lock")` 探測。
- **[SRV-AUD-11] [🟡 P2 | C3.3 | All-OS] [`dev/checker.py:L346, L763-L764`](https://drive.google.com/file/d/1Bou8pzQEZ9QvKEVSmQj_h6PAexbhPQ2U/view?usp=drivesdk)**：修正 `_MUTABLE_TYPE_NAMES` 中含前導空白的 `" DefaultDict"` 為 `"DefaultDict"`（消除 `ClassVar[DefaultDict]` False-Green 漏檢），並移除 `L763-L764` 空分支。
- **[SRV-AUD-12] [🟡 P2 | C5.2 & C2.2 | Windows / All-OS] [`dev/tester.py:L941-L949`](https://drive.google.com/file/d/14Ghh6Wu1Ax08ecJYHcaSvhA4CB2xihOU/view?usp=drivesdk)**：`_handle_post_test_sync` 在 `subprocess.run is _ORIG_SUBPROCESS_RUN` 時改用 `run_subprocess_with_tree_timeout` 防止超時殘留孤兒進程。
- **[SRV-AUD-13] [🟡 P2 | C2.2 & C2.3 | Windows] [`vscode_support/projector.py:L229-L242`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)**：Windows Junction fallback 優先呼叫 `_winapi.CreateJunction`（對齊 [`sandbox.py:L471`](https://drive.google.com/file/d/1Y5xYNAG_g1Kgxk9tkw8op6K1ACfdOuXK/view?usp=drivesdk)），失敗才退回 `cmd /c mklink /J`。
- **[SRV-AUD-14] [🔵 P3 | C7.1 & C8.3 | All-OS] [`server/service.py:L88-L115`](https://drive.google.com/file/d/1a1Q4sx6sMcWXZ-UzqDumMnVH8MinyVJz/view?usp=drivesdk) & [`dev/scripts/cli.py:L58-L59`](https://drive.google.com/file/d/1RHDxT3GsitIywSIKCY7c-4Lawx1DVyOC/view?usp=drivesdk)**：`touch_activity()` 快取 `daemon.json` 之 `(mtime, port, token)`；`dev/scripts/cli.py` 對 `cmd_bags` 元素做 `str(a)` 保護。

### ✅ Track 4 已排除之假陽性與刻意設計 (`SRV-RFP-01` ~ `08`)
- **`[SRV-RFP-01]` [`master.py:L1200-L1210`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)**：`daemon.lock` 保留於磁碟並以 `InterProcessLock.acquire(blocking=False)` 判定存活性，防範 POSIX `flock` unlink 競態。
- **`[SRV-RFP-02]` [`master.py:L520-L567`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)**：`get_status_dict()` 刻意不取 `_dispatch_lock` 以確保長任務期間 `server status` 毫秒級回應。
- **`[SRV-RFP-03]` [`worker.py:L187-L205, L270-L281`](https://drive.google.com/file/d/1YDMnio1KHGj52Tiro48e18u6i4NNYN9p/view?usp=drivesdk)**：透過 `bind_runtime_context` 隔離請求級 `cwd` 與 `env`。
- **`[SRV-RFP-04]` [`master.py:L59-L186`](https://drive.google.com/file/d/1knGK_GIg72fpXpnhS4mbOtJN751jUQLI/view?usp=drivesdk)**：`WorkerMemoryHealthMonitor` 採 256MB 保底基線與三維度相對閾值 + 60s 冷卻期。
- **`[SRV-RFP-05]` [`dev/builder.py:L102-L147`](https://drive.google.com/file/d/1FrYUW_-lZNhQAClLTGl9xxdyuFmKaHMd/view?usp=drivesdk)**：同目錄暫存 zip 關閉句柄後 `os.replace`，防範 `EXDEV` 與 `WinError 32`。
- **`[SRV-RFP-06]` [`dev/testing/runner.py:L66-L95`](https://drive.google.com/file/d/1OtlDW4WKjSe4EDdH5Ry9vI-xj_O8K9sb/view?usp=drivesdk)**：`start_parent_death_watchdog` 同時支援 POSIX `ppid == 1` 與 Windows `is_process_alive(expected_ppid)`。
- **`[SRV-RFP-07]` [`vscode_support/projector.py:L24-L84`](https://drive.google.com/file/d/1jjRmoXvvKVoYdprmcXjyswDeWS2CSWSy/view?usp=drivesdk)**：`strip_jsonc` 狀態機正確保護字串內 `//` 與 `/*`。
- **`[SRV-RFP-08]` [`server/logger.py`](https://drive.google.com/file/d/1tpy7XYyfoUAhI0EtXSeQHj1BVaeQO8t1/view?usp=drivesdk) & [`server/streamer.py`](https://drive.google.com/file/d/1UkuxGO5yW1_Rm4zw9roQPXHspRIZuQ8O/view?usp=drivesdk)**：相容門面（Compatibility Facade），予以保留。

## 7. Track 5 分級處方與查證詳情：`Unit 09` & `Unit 10` (`module:agents-workflow`、`module:gdrive-support`)

### 🔴 P0 - Critical（高危阻斷：Symlink 繞過邊界與敏感憑證守門）
- **[WF-AUD-01] [🔴 P0 | C6.1 & C6.3 | All-OS] [`ys_codebase/source/gdrive-support/gdrive_support/config.py:L334-L363, L616-L632`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) - 本地空間掃描與敏感憑證守門未解析符號連結（Symlink），可致憑證外洩或越界上傳**
  - **問題座標與分類**：[`gdrive_support/config.py`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk)（`is_sensitive_credential_path` `L334-L363`、`collect_space_local_files_with_stat` `L616-L632`）｜ `C6.1 / C6.3` ｜ `All-OS`
  - **三步反向查證與觸發根因**：
    1. `pull` 下載路徑（[`coordinator.py:L3098-L3112`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)）會先 `.resolve()` 再呼叫 `spec.is_local_abs_allowed()` 與 `is_sensitive_credential_path()`；但 `push` / `sync` 的本地掃描入口 `collect_space_local_files_with_stat`（`L616-L632`）直接使用未 `.resolve()` 的 `local_abs`。
    2. 若同步空間內存在符號連結（如 `docs/debug.txt -> ../ys_codebase/.config.local/gdrive-support/token.json` 或指向工作區外的私鑰），`local_abs.relative_to(proj_root)`（`L621`）在字面路徑上直接成功，且 `is_sensitive_credential_path`（`L340-L353`）僅檢查字面檔名 `debug.txt` 與字面相對路徑 `docs/debug.txt`，導致憑證或越界檔案在 `push` 時被上傳至 Google Drive。
  - **建議解決方案（Recommended Solution）**：
    ```python
    # ys_codebase/source/gdrive-support/gdrive_support/config.py (L334-L363 & L616-L632)
    def is_sensitive_credential_path(abs_path: Path, proj_root: Path) -> bool:
        if _check_single_cred_path(abs_path, proj_root):
            return True
        try:
            resolved = abs_path.resolve()
            if resolved != abs_path and _check_single_cred_path(resolved, proj_root.resolve()):
                return True
        except OSError:
            return True
        return False
    ```
    並在 `collect_space_local_files_with_stat` 中對 `if local_abs.is_symlink() and not spec.is_local_abs_allowed(local_abs, proj_root): continue` 進行攔截。

### 🟠 P1 - High（編譯器正則誤傷、雙軌 Manifest 失步、雲端帳本漏回寫與 SSL Socket 洩漏）
- **[WF-AUD-02] [🟠 P1 | C1.1 & C2.1 | All-OS] [`ys_codebase/source/agents-workflow/agents_workflow/compiler.py:L158-L160, L670-L713`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) - `make_standalone_tag_regex` 缺少行首/行尾錨點且 `count=1` 導致行內 Token 誤判斷行與同檔重複 Token 被靜默抹除**
  - **建議解決方案**：為 `make_standalone_tag_regex` 補上 `^`、行尾 `(?:
?
|$)` 與 `re.MULTILINE`，移除 `L688` 的 `count=1`，並允許同檔同時展開獨立行錨點與行內 code span 標籤。
- **[WF-AUD-03] [🟠 P1 | C1.2 & C2.1 | All-OS] [`ys_codebase/source/agents-workflow/agents_workflow/compiler.py:L362-L400`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) - `_substitute_stage2_tags_in_segment` 對整個 Fenced Code Block 執行 `DOUBLE_SLASH_CLEAN_REGEX` 破壞程式碼內 `//` 註解與 Python `//` 整數除法**
  - **建議解決方案**：移除 `L400` 對整個 `segment` 的 `DOUBLE_SLASH_CLEAN_REGEX.sub("/", segment)`，僅在 `__#{...}__` 與 `__${...}__` 標籤替換結果與緊鄰右斜線拼接處清理雙斜線。
- **[WF-AUD-04] [🟠 P1 | C1.1 & C1.2 | All-OS] [`ys_codebase/source/agents-workflow/agents_workflow/publisher.py:L546-L591, L877-L944`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk) - `ReleasePublisher` 雙軌 Manifest 路徑格式失步（`local_release_manifest.json` 寫入實體絕對路徑而非 `project://` URI）且 `agent_rules` 檢核與物化脫節**
  - **建議解決方案**：在 `_save_deployment_manifests` 的 Local 軌統一使用 `self._to_project_uri(f, eff_proj_root)`，並對齊 `_verify_agent_rule_injections` 與 `_prepare_target_compilations`。
- **[WF-AUD-05] [🟠 P1 | C1.1 & C1.3 | All-OS] [`ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L1447-L1470, L1503-L1514, L2550-L2559`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) - Stage 1 提前原地覆寫 `meta["branch_files"]` 導致 Stage 3 `meta_dirty` 恆為 `False`，雲端新增/CoW 替換檔案於 `pull` 後漏寫回 `.yscb_gdrive.json`**
  - **建議解決方案**：在 Stage 1 更新 `meta["branch_files"]` 前先快照比對 `prev_all_branch_files`，將 `stage1_meta_dirty` 傳入 `_RemoteStageSnapshot` 並於 Stage 3 合併判定 `meta_dirty`。
- **[WF-AUD-06] [🟠 P1 | C3.2 | All-OS] [`ys_codebase/source/gdrive-support/gdrive_support/transport.py:L1019, L1045-L1071, L1317-L1326`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk) - `GoogleDriveApiTransport` 於短命 `ThreadPoolExecutor` 工作執行緒內將 Keep-Alive `HTTPSConnection` 存入 `threading.local()`，池銷毀與 `close()` 時洩漏 SSL Socket 句柄**
  - **建議解決方案**：在 `GoogleDriveApiTransport` 中以 `self._conn_lock` 與 `self._all_conns: Set[HTTPSConnection]` 追蹤所有執行緒建立之連線，於 `_drop_https_conn` 與 `close()` 中確定性關閉全部連線。

### 🟡 P2 & 🔵 P3 - Medium & Optimization (`WF-AUD-07` ~ `13`)
- **[WF-AUD-07] [🟡 P2 | C3.3 | All-OS] [`plans/verifier.py:L458-L545`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk) & [`_verifier_healer.py:L108-L123`](https://drive.google.com/file/d/1_KSAfX7eYfZECTr3aHzSPdMiuc3uTCsK/view?usp=drivesdk)**：`has_name`/`has_date`/`has_status`/`has_parent`/`has_model` 改為檢查 `any(bool(headers.get(k, "").strip()) for k in ...)`，避免空白標頭（如 `> 狀態：`）觸發 False-Green 放行。
- **[WF-AUD-08] [🟡 P2 | C1.2 | All-OS] [`plans/verifier.py:L358-L368`](https://drive.google.com/file/d/1PzMd1dReINug7i4a2EKje_vNJpLNSt9q/view?usp=drivesdk)**：`_extract_non_code_lines` 對 Fenced Code Block 內部行填入空字串 `""` 佔位而非 `continue` 刪除，維持報錯行號 1:1 對齊原檔。
- **[WF-AUD-09] [🟡 P2 | C1.1 & C3.3 | All-OS] [`plans/archiver.py:L109-L171`](https://drive.google.com/file/d/1Rin77sqznCMYxaFoPalyAtH_AkZLrnFG/view?usp=drivesdk)**：`archive_plan` 改用 `PlanScanner.get_plan_info` 確認主計畫與所有 `sub_XX` 皆已完成（避免單憑 `revision_log.md` 誤放行），並於歸檔時一併清理 `sub_XX/handoff.md`。
- **[WF-AUD-10] [🟡 P2 | C1.1 & C1.2 | All-OS] [`compiler.py:L230-L240, L281-L293`](https://drive.google.com/file/d/1xsNrrg2XILpzTAfOXl586AhvGpnhC3SD/view?usp=drivesdk) & [`plans/_common.py:L11-L15`](https://drive.google.com/file/d/1zp81LYD76rSLemT0FvimTivX1qwB3NJ-/view?usp=drivesdk)**：補齊 `workflow.roadmap://` 與 `workflow.docs://` 在 `_resolve_local_uri_tag`、`_resolve_project_uri_tag` 與 `DEFAULT_URI_FALLBACKS` 的對稱退避。
- **[WF-AUD-11] [🟡 P2 | C1.1 & C1.3 | All-OS] [`gdrive_support/config.py:L466-L476`](https://drive.google.com/file/d/1eLin6obQE1iPoIBoIU2UHi6wZe2UPUce/view?usp=drivesdk) & [`gdrive_support/service.py:L140-L165, L231-L249`](https://drive.google.com/file/d/1-s1zWxlX2uqcMC8C5N5_py_uRqFxEffC/view?usp=drivesdk)**：`load_gdrive_config` 對齊 `hook.core.py` 支援 `raw_cfg["sync_spaces"]`；`GDriveSyncServiceWorker.stop()` 關閉自建 `transport` 並重置 `self._coordinator = self._explicit_coordinator`。
- **[WF-AUD-12] [🔵 P3 | C7.1 | All-OS] [`gdrive_support/coordinator.py:L1143-L1182`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)**：`checkout_branch` 保留 `target_raw_entries` 並傳遞 `entry_hint=target_raw_entries.get(rel_p)` 予 `download_file`，省去 $2 \times N$ 次雲端 API 往返。
- **[WF-AUD-13] [🔵 P3 | C7.1 & C1.3 | All-OS] [`gdrive_support/coordinator.py:L1998-L2015`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)**：`_execute_pull_batch` 將下載時已算好的 `(mtime_ns, size, md5, sha256)` 同步寫入 `state["fingerprint_cache"]`，避免下一輪同步重複計算雜湊。

### ✅ Track 5 已排除之假陽性與刻意設計 (`WF-RFP-01` ~ `08`)
- **`[WF-RFP-01]` [`agents-workflow/contributes/ast.json`](https://drive.google.com/file/d/1XzAoW_-axJzehOdRbDJNDO3PuDFDzBym/view?usp=drivesdk)**：`SpaceRegistry` 雙鍵支援短空間名 `["docs", "plans"]`。
- **`[WF-RFP-02]` [`publisher.py:L1251-L1304`](https://drive.google.com/file/d/1SgrO-hVFp_u7-CLJmQvOHnzBZ7q_S_Hy/view?usp=drivesdk)**：`ensure_jit_release` 5 秒時間桶同時綁定 6 個設定/Manifest 的 `st_mtime_ns` 元組。
- **`[WF-RFP-03]` [`roadmap.py:L19-L30`](https://drive.google.com/file/d/1AGe9UIoVFQ3MqcunnTmXuvXqltfepa3u/view?usp=drivesdk)**：`_STDLIB_WRITE_TEXT` 供白箱單元測試 `patch.object(Path, "write_text")` 攔截驗證。
- **`[WF-RFP-04]` [`transport.py:L473-L511`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：`list_files` 自動將同名重複舊檔移入垃圾桶屬雲端自癒防線。
- **`[WF-RFP-05]` [`coordinator.py:L563-L631`](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)**：`cli_yield.signal` 具備 120s 超時與 `is_process_alive(pid)` 死進程自動清理。
- **`[WF-RFP-06]` [`transport.py:L1628-L1644`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：下載暫存檔位於目標檔同目錄且關閉句柄後 `os.replace`，防範 `EXDEV` 與 `WinError 32`。
- **`[WF-RFP-07]` [`reconciler.py:L1-L426`](https://drive.google.com/file/d/1PnaaNLogqRvmXNuEGfWQiEB8b67uBCXs/view?usp=drivesdk)**：100% 無狀態純函式三方對帳器。
- **`[WF-RFP-08]` [`transport.py:L2018-L2045`](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：OAuth Callback 已使用 `html.escape` 並將 `token.json` 權限設為 `0o600`。


---

## 3. 結論 (Conclusion)

- **核心結論**：全倉 10 個審計單元共檢出 **65 項真實問題（4 P0、26 P1、24 P2、11 P3）** 並排除 **38 項誤報（RFP）**。其中 4 項 P0 分別位於 `ast/ast_engine/parsers/provisioner.py`（`AST-AUD-01` 全域鎖跨越 `pip install` 阻塞 90 秒）、`knowledge-db/knowledge_db/pipeline.py`（`KDB-AUD-01` C# `partial class` 增量熱修補永久抹除主檔案非 partial 符號）、`server/server/master.py`（`SRV-AUD-01` 握手後閒置期未排空 Worker `stdout` 導致 OS Pipe 緩衝區塞滿死鎖）與 `gdrive-support/gdrive_support/config.py`（`WF-AUD-01` Symlink 未解析繞過空間邊界與機密憑證黑名單）。
- **後續建議（選填）**：已全量轉化為本 Umbrella 主計畫旗下 `sub_01` ~ `sub_05` 五個子計畫之 `P00_discuss.md`、`P01-05_auto.md` 與 `P06_test_plan.md`，供本地端拉取後依序推進實作與回歸測試。
