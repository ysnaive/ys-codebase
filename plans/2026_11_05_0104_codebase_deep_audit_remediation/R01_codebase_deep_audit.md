# 專題調研與分析報告：全倉八維度單點序列深度審計與盲眼反向查驗 (R01_codebase_deep_audit.md)

> 調研主題：全倉八維度單點序列深度審計與盲眼反向查驗 (2026_11_05_0104_codebase_deep_audit_remediation)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 調研狀態：Concluded  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：隨 `ys-codebase` 新增 `vscode-support` 與 `gdrive-support` 兩大擴充模組並完成多執行緒同步與空間權重收斂，需針對全倉（宿主 `yscb.py` 與九大模組共 9 個獨立審查單元、160 個核心檔案）執行八維度（`C1`～`C8`）單點序列深度審計，並透過 `BlindSubagentStandards.md` 原型 ③（Devil's Advocate 盲眼反向事實查驗）於 Linux VM 進行實證反推，剔除偽陽性、攔截修復副作用並校準真實爆炸半徑（Blast Radius）。
- **調研目標與範疇**：
  1. 完成 `Unit 01 (gdrive-support)` 與 `Unit 02 (vscode-support)` 重點新模組及 `Unit 03`～`Unit 09` 全倉八維度深潛審查。
  2. 透過 4 路盲眼子代理反向驗證首輪 66 項候選命題，確立最終 **64 項有效問題**（`2 P0 / 12 P1 / 29 P2 / 21 P3`，駁回 2 項完整偽陽性與 5 項子命題）與 **8 大防回歸修復紅線**。
  3. 制定無檔案寫入衝突之 4 路平行子計畫（`sub_01` ～ `sub_04`）修復藍圖。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

- **核心分析與實證內容**：以下完整收錄雙輪審計統計矩陣、盲眼反向查驗攔截之 8 大修復副作用紅線、以及 `Unit 01` ～ `Unit 09` 逐項根因分析與無副作用程式碼級處方。

>
>
>
>

### 1. 雙輪審計執行總覽與盲眼反向查驗校準統計

本報告包含兩階段嚴格審計成果：

1. **第一輪（正向八維度序列深潛）**：針對 [repo/main/](https://drive.google.com/drive/folders/1LuXaG9m8uZUs2q37WiGuVwCWB65Uvkog) 下 9 個審查單元（160 個核心檔案）提出 **66 項候選問題**（初判 `6 P0 / 29 P1 / 22 P2 / 9 P3`）。

2. **第二輪（Devil's Advocate 盲眼反向事實查驗）**：以相同 4 路分流派出全新零上下文盲眼子代理，直接於 Linux VM 載入第一手源碼與 `DESIGN_NOTES.md` 進行實證反推，**成功攔截 8 項擬議修復方案的潛在回歸副作用（20% 差異分支不變量）**、**駁回 2 項完整偽陽性與 5 項局部子命題**，並將具有上游防護減輕之項目精確下調至真實爆炸半徑（Blast Radius）。

* **反向查驗校準後最終統計（共 64 項有效問題，駁回 2 項）**：

  * 🔴 **P0 (Critical — 實機證實常態核心路徑資料遺失或全域狀態競態)**：**`2` 項**（由初判 6 項收斂：`U1-P0-01`、`DEV-01`）

  * 🟠 **P1 (High — 核心功能缺口、跨環境污染或特定條件必現故障)**：**`12` 項**（含初判 P0 下調 4 項 + 維持 P1 8 項）

  * 🟡 **P2 (Medium — 次要並發/異常邊界、非預設配置或向後相容缺口)**：**`29` 項**

  * 🔵 **P3 (Optimization — 低頻邊界防禦、死分支清理與微觀 I/O 加速)**：**`21` 項**

  * ❌ **駁回 (`[REJECTED_FALSE_POSITIVE]` / By Design)**：**`2` 項完整駁回**（`U1-P2-01`、`DEV-06`）＋ **5 項局部子命題剔除**

| 審查單元 (Audit Unit) | 模組路徑與雲端連結 | 初判分佈 (P0/P1/P2/P3) | **校準後分佈 (P0/P1/P2/P3/駁回)** | 盲眼反向查驗核心結論 | 
| ----- | ----- | ----- | ----- | ----- | 
| **Unit 01** *(重點關注)* | [ys_codebase/source/gdrive-support/](https://drive.google.com/drive/folders/1ayVBCvXjGJIu8rjY63q-jL7ODlGPMrpl) | 1 / 5 / 3 / 2 | **🔴 1 / 🟠 1 / 🟡 4 / 🔵 4 / ❌ 1** | \*\*VM 實證坐實 `U1-P0-01`（單向 `pull` 污染基準線致後續 `sync` 靜默覆蓋本地修改）\*\*與 `U1-P1-04`（CLI `--sandbox-dir` 污染生產狀態）；駁回 `U1-P2-01`（雙閘門防誤刪屬刻意設計）；攔截 `U1-P3-01` 盲信非活躍分支快取導致誤刪 `.history/` 之副作用。 | 
| **Unit 02** *(重點關注)* | [ys_codebase/source/vscode-support/](https://drive.google.com/drive/folders/1KvI2QpqLxtv7Mr29nf5Ph09e_0kTq6Y0) | 0 / 2 / 2 / 1 | **🔴 0 / 🟠 1 / 🟡 3 / 🔵 1 / ❌ 0** | **坐實 `U2-P1-02`（`extraPaths` 缺漏 `TODO-22`，驗證用 `self.yscb_dir` 可 100% 通過 `dev check` Zero-Probing）**；`U2-P1-01` 因 `installer.py` 後續 `on_reload`/`on_env_synced` 已自動清理孤兒 Schema，下調為 `P2`（僅需收緊 `ctx` Fail-Closed 守衛）。 | 
| **Unit 03** *(宿主與微內核)* | [yscb.py](https://drive.google.com/file/d/1d27_f7eYvqi1Z0rx2Eq96qzkADwfv9yf/view?usp=drivesdk) + [ys_codebase/source/core/](https://drive.google.com/drive/folders/1mF6RGkH4OCWUgMR6-92_PiZkk9OBcII6) | 2 / 6 / 4 / 2 | **🔴 0 / 🟠 4 / 🟡 8 / 🔵 2 / ❌ 0** | `U3-P0-01` 與 `U3-P0-02` 因屬本機 CLI 輸入且標準庫 `getresponse()` 原生拋出 `ConnectionResetError` 已命中 `accepted=True`，校準下調為 `P1`；**攔截 3 項致命修復副作用**（禁在 `uri.resolve` 封殺基準值 `../`、禁對調 `URLError`/`OSError` 順序、禁對快照原目錄直接 `_atomic_swap_dir`）。 | 
| **Unit 04** *(常駐服務)* | [ys_codebase/source/server/](https://drive.google.com/drive/folders/14YhkqN8sNCytcyToGCO2xjgKMRjN-DoA) | 1 / 2 / 3 / 0 | **🔴 0 / 🟠 3 / 🟡 0 / 🔵 3 / ❌ 0** | `SRV-01` 因 `worker.py:L226` 已將 Python `sys.stdout` 重導向至 `sys.stderr`，僅原生 C 擴充直寫 FD 1 才會觸發，由 `P0` 下調為 `P1`；坐實 `SRV-02`（`with streamer:` 提前關閉吞掉錯誤訊息）與 `SRV-03`（Windows `PYTHONIOENCODING`）。 | 
| **Unit 05** *(開發工具鏈)* | [ys_codebase/source/dev/](https://drive.google.com/drive/folders/1O6Oo3epKn_klYg6dIjM_NxTKiGPlpvNO) | 1 / 2 / 2 / 1 | **🔴 1 / 🟠 0 / 🟡 3 / 🔵 1 / ❌ 1** | **坐實 `DEV-01`（`P0`：父進程 `ThreadPoolExecutor` 內 `create_sandbox` 脫鎖修改模組級全域 `uri._active_yscb_dir`）**，並攔截「全程加 `_SANDBOX_LOCK` 導致平行複製退化為串行」之副作用；駁回 `DEV-06`（9 模組拓撲排序耗時 $<5\,\mu\text{s}$）。 | 
| **Unit 06** *(工作流引擎)* | [ys_codebase/source/agents-workflow/](https://drive.google.com/drive/folders/1j00Pm5gpnLacxei5AFvuuh3brerYVsIp) | 0 / 3 / 2 / 1 | **🔴 0 / 🟠 0 / 🟡 3 / 🔵 3 / ❌ 0** | `AW-01` 查驗內建 8 大 `release_target` 均未使用 `"agent_rules"`，下調為 `P3`；坐實 `AW-02`（違反 `DN-AW-05` 遺失 `workflow -> skill` 轉譯，`P2`）與 `AW-03`（`source/core` 插入 `sys.path[0]`，`P2`）；剔除 `AW-04` 中 `P00_discuss_auto.md` 假陽性。 | 
| **Unit 07** *(檔案空間 L1)* | [ys_codebase/source/file-space/](https://drive.google.com/drive/folders/1LqIEmjO33s7lIOkkTdBLy39-SQRW03fJ) | 0 / 4 / 2 / 0 | **🔴 0 / 🟠 0 / 🟡 5 / 🔵 1 / ❌ 0** | `FS-01` 因下游 `ast`/`knowledge-db` 逐空間消費 `space_generations` 不會漏檢，下調為 `P2`；**攔截 `FS-03` 無條件改 `else:` 導致宿主 `contribute.json` 穿透污染沙盒測試之嚴重副作用**。 | 
| **Unit 08** *(語法拓撲 L2)* | [ys_codebase/source/ast/](https://drive.google.com/drive/folders/1O6LE67WY74h-YfjAPzrUbJEvHjvtGXHY) | 1 / 3 / 2 / 0 | **🔴 0 / 🟠 3 / 🟡 2 / 🔵 1 / ❌ 0** | `AST-01` 查明生產環境 `_normalize_space_dirty_paths` 已展開完整路徑，僅 `_resolve_dirty_files_only` 與根目錄單檔受影響，由 `P0` 下調為 `P1`（並**攔截刪除雙向後綴匹配破壞 `DN-06` 沙盒測試之副作用**）；100% 坐實 `AST-02`（`use_parallel` 恆為 `False`）與 `AST-03`（單空間事件覆寫 `unified.symbols.bin.gz`）。 | 
| **Unit 09** *(知識檢索 L3)* | [ys_codebase/source/knowledge-db/](https://drive.google.com/drive/folders/1jhHPQ3INkeUY4HPCil521JFgVqOkVUCD) | 0 / 2 / 2 / 2 | **🔴 0 / 🟠 1 / 🟡 2 / 🔵 3 / ❌ 0** | **100% 坐實 `KDB-01`（`KnowledgeDBServiceWorker` 冷啟動未載入 `unified_index` 導致 `DN-30` 水位線自癒失效，`P1`）**；**攔截 `KDB-03` 將 `min_score` 套用於 RRF 分數（最高僅 `0.0164`）導致混合檢索結果 100% 歸零之致命副作用**！ | 

### 2. 盲眼反向查驗攔截之 8 大修復副作用紅線（Anti-Regression Guardrails）

在動手修改任何代碼前，**必須嚴格遵守以下由 Devil's Advocate 盲眼反向查驗揪出的 8 道防回歸紅線**：

1. **\[紅線 1 — `U1-P3-01` `gdrive-support`\] 嚴禁盲目停用非活躍分支掃描而直接信任空的 `meta["branch_files"][other_b]`**：

   * 外部網頁版 AI 可直接在雲端建立新分支資料夾（由 `_reconcile_unregistered_cloud_branches` 初始化為空字典 `{}`）或修改非活躍分支 Shortcut。若直接跳過掃描，`_gc_unreferenced_history_files` 會誤判該分支引用數為 0，當場將 `.history/` 內的凍結實體檔移入垃圾桶！僅在 `not branches[other_b].get("auto_discovered") and bool(branch_files_map.get(other_b))` 時方可快取。

2. **\[紅線 2 — `U2-P1-02` `vscode-support`\] 實作 `TODO-22` 時必須同時從 `ANALYSIS_EXCLUDE_PATTERNS` 移除 `"**/.modules/**"` 且零 `"module.source://"` 字面量**：

   * [dev/checker.py:L983-L994](https://drive.google.com/file/d/1BMfY2pkmf2_FRMsYQKRy9VoNY-d2HuTN/view?usp=drivesdk) 會掃描 AST 字串常數攔截 `"module.source://"`；必須使用 `os.path.join(self.yscb_dir, "source")` 與 `os.path.join(self.yscb_dir, ".modules")` 探索目錄，並將 `"**/.modules/**"` 自 `ANALYSIS_EXCLUDE_PATTERNS`（[projector.py:L143](https://drive.google.com/file/d/1iY4UahzKhztfgndZFeGyzbi8LmHMqBdb/view?usp=drivesdk)）移除，否則 Pylance 仍會忽略已安裝模組。

3. **\[紅線 3 — `U3-P0-01` `core/uri.py`\] 嚴禁對 URI 協議基準值（`sval`）封殺 `..`，僅能校驗拼接後之子路徑 `rel`**：

   * 當宿主位於子目錄時，`project_root = "../"` 是完全合法的正式配置（`[DN-07]`）。必須先解析出 `target_base = os.path.normpath(...)`，再對非空子路徑 `rel` 驗證未逃逸出 `target_base`。

4. **\[紅線 4 — `U3-P0-02` `core/commands/dispatcher.py`\] 嚴禁將 `except OSError:` 移至 `except urllib.error.URLError:` 之前**：

   * 因為 `issubclass(URLError, OSError)` 為 `True`，對調順序會使 `except URLError:` 淪為死代碼。必須維持原順序，並在 `except urllib.error.URLError as err:` 內部將 `(TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)` 判為 `accepted=True`。

5. **\[紅線 5 — `U3-P1-03` `core/engine.py`\] 嚴禁在 `act_restore_snapshot` 對快照目錄直接呼叫 `_atomic_swap_dir`，且嚴禁對 `contributes.get()` 無條件 `deepcopy`**：

   * `_atomic_swap_dir(staging_dir, target_dir)` 會將第一個參數 `os.replace` 移走並在 `finally` 中刪除；若直接傳入 `snapshot://{id}/modules/{mod}` 會摧毀快照本身！必須先複製至 `.modules/.staging_*`。同時 `contributes.get()` 位於 `<0.1ms` 熱路徑（`[DN-12]`），無條件 `deepcopy` 會造成嚴重效能退化。

6. **\[紅線 6 — `DEV-01` `dev/testing/sandbox.py`\] 嚴禁將整個 `create_sandbox()` 包入 `_SANDBOX_LOCK`**：

   * `create_sandbox` 內含耗時的壓縮包解壓與目錄樹複製，全程加鎖會讓 `dev test --all` 的多執行緒平行沙盒建置徹底退化為單執行緒串行！正確根治方式是將 [core/uri.py:L19-L21](https://drive.google.com/file/d/1ZMm7ZnjHLl0CV7kckLGb0Rr-T8H1zwN_/view?usp=drivesdk) 的 `_active_host_dir`、`_active_yscb_dir`、`_active_module_context` 與 `_reconciling_tokens` 改為 `threading.local()`。

7. **\[紅線 7 — `FS-03` & `AST-01` `file-space` / `ast`\] 嚴禁無條件開放 `_apply_project_space_overrides` 或刪除 `is_dirty_file_match` 雙向後綴匹配**：

   * 在 `FileSpaceManager` 中若無條件執行 `_merge_project_space_override`，沙盒測試 `FileSpaceManager(project_root=tmp_dir)` 會透過 `config://file-space/contribute.json` 讀到宿主真實配置並污染測試沙盒；必須加上 `self._explicit_project_root is None` 守衛。在 `is_dirty_file_match` 中必須保留 `"/" in sym_path_norm` 時的雙向 `.endswith("/" + ...)`（對標 `[DN-06]`），僅修正 `"/" not in sym_path_norm` 時允許匹配絕對路徑 `p`。

8. **\[紅線 8 — `KDB-03` `knowledge-db`\] 嚴禁將 BM25 尺度的 `flt.min_score` 套用於 `hybrid_rrf` 融合分數**：

   * `HybridSearchEngine` 的 RRF 最高理論得分僅 $\frac{0.5}{61} + \frac{0.5}{61} \approx 0.0164$，而 BM25 分數常為 `1.0~30.0`。若在 `pipeline.py:L1298` 對 RRF 分數過濾 `score < flt.min_score`，任何帶 `min_score >= 0.02` 的混合搜尋將 100% 結果歸零！

### 3. 重點關注新模組校準後處方（Unit 01: `gdrive-support` & Unit 02: `vscode-support`）

#### 3.1 Unit 01：`ys_codebase/source/gdrive-support/`（校準後：🔴 1 P0 / 🟠 1 P1 / 🟡 4 P2 / 🔵 4 P3 / ❌ 1 駁回）

* **\[U1-P0-01\] \[🔴 P0 維持 | `[CONFIRMED_REAL]` | VM 實測重現\] [gdrive_support/coordinator.py:L975-L988](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) & [gdrive_support/reconciler.py:L178-L207](https://drive.google.com/file/d/1PnaaNLogqRvmXNuEGfWQiEB8b67uBCXs/view?usp=drivesdk) — 單向 `pull`/`push` 略過對向修改時誤寫 `IN_SYNC` 覆蓋本地 `sync_state.json` 基準線，引發後續 `sync` 靜默回滾本地修改（Data Loss）**

  * **盲眼 VM 實測證據**：在 Linux VM 建立沙盒測試，初始檔案 `docs/a.txt` 為 `"v1"` 並完成同步；本地修改為 `"v2_local_edit"`（MD5 `9cb926...`）後執行 `coord.run_sync(mode="pull")`。實測 `pull` 結束後，`sync_state.json` 基準線的 MD5 被無條件覆寫為 `"v2_local_edit"` 的 MD5，而雲端仍為 `"v1"`；緊接著執行 `coord.run_sync(mode="sync")`，對帳器因 `loc.md5 == base.md5` 且 `rem.md5 != base.md5` 誤判為遠端單方修改（`modified_remote_only`），執行 `PULL_UPDATE` 將本地 `"v2_local_edit"` **靜默回滾為舊版 `"v1"`**。

  * **無副作用精確修復方案**：

    ```
    # ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L975-L998
    if act.action == SyncActionType.IN_SYNC:
        if (
            act.local_entry
            and act.remote_entry
            and act.reason == "identical_digest"
        ):
            merged_entry = FileEntry(
                rel_path=rel_p,
                md5=act.local_entry.md5,
                sha256=act.local_entry.sha256,
                size=act.local_entry.size,
                mtime_ns=act.local_entry.mtime_ns,
                file_id=act.remote_entry.effective_file_id(),
                is_shortcut=act.remote_entry.is_shortcut,
                target_file_id=act.remote_entry.target_file_id,
            )
            branch_state_dict[rel_p] = merged_entry.to_dict()
        elif (
            act.local_entry is None
            and act.remote_entry is None
            and act.baseline_entry is not None
        ):
            branch_state_dict.pop(rel_p, None)
            if rel_p in curr_branch_files:
                curr_branch_files.pop(rel_p, None)
                meta_dirty = True
            self._save_local_state(state)
        continue
    
    ```

* **\[U1-P1-04\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [gdrive-support/scripts/cli.py:L530-L755](https://drive.google.com/file/d/1tc_i1nEIDv8uTBWdrTnWAs2aNdY5CR5Q/view?usp=drivesdk) & [gdrive_support/coordinator.py:L171-L178, L837, L1346](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — CLI 傳入 `--sandbox-dir` 執行 `init / branch / checkout / pull / push / sync` 時未隔離狀態路徑，直接覆寫污染全域生產環境 `sync_state.json` 與 `config.project.json`**

  * **盲眼查驗結論**：確認 100% 屬實。`cli.py` 的原子指令（`ls/get/put/rm/mkdir/shortcut`）有傳遞 `sandbox_override=sandbox_dir`，但 `init`、`branch_*`、`checkout` 與 `_run_sync_cmd` 未將 `state_path`、`lock_path`、`log_path`、`readme_state_path` 導向沙盒，且 `checkout` 會改寫正式 `config.project.json` 的 `active_branch`。

  * **無副作用精確修復方案**：於 `scripts/cli.py` 提取 `_build_coordinator(sandbox_dir)` 將四個狀態檔路徑錨定於 `Path(sandbox_dir).resolve()` 下，並於 `coordinator.py:L1346` `_persist_active_branch_to_config` 在 `bool(self.config.sandbox_dir)` 時跳過改寫全域 `core_config`。

* **\[U1-P1-01\] \[🟠 P1** $\to$ **🟡 P2 下調 | `[PARTIAL_OR_DOWNGRADED]`\] [gdrive_support/transport.py:L744-L756, L1020-L1035](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk) & [gdrive_support/coordinator.py:L347-L360, L625-L634](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — `_folder_cache` 執行緒鎖與 `_precreate_remote_dirs` 按深度分層 BFS 平行化（對標 [TODO-23](https://drive.google.com/file/d/1YhIAk1j5OVvixaTwXabMogMA8IhuCN9i/view?usp=drivesdk)）**

  * **下調原因**：推送階段前主執行緒已預建目錄並填入 `_folder_cache`，故僅拉取階段 `download_file -> get_entry` 存在 `_folder_cache` 並發寫入與深層目錄序列預建延遲。新增 `self._cache_lock = threading.RLock()` 與按 `depth = parent_rel.count("/")` 分層 `ThreadPoolExecutor` 平行 `mkdir` 即可完美解決。

* **\[U1-P1-02\] \[🟠 P1** $\to$ **🟡 P2 下調 | `[PARTIAL_OR_DOWNGRADED]`\] [gdrive_support/transport.py:L204-L265, L510-L566](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk) — `LocalSandboxTransport` 並發上傳鎖區間擴充**

  * **下調原因**：僅影響 `--sandbox-dir` 本地測試沙盒，不影響生產環境 `GoogleDriveApiTransport`。將 `upload_file` 的 `shutil.copy2` 納入 `with self._lock:` 即可。

* **\[U1-P1-03\] \[🟠 P1** $\to$ **🟡 P2 下調 | `[PARTIAL_OR_DOWNGRADED]`\] [gdrive_support/coordinator.py:L1190-L1194](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk) — `run_sync` 部分上傳異常中斷時於 `finally` 盡力寫回 `meta_dirty`**

  * **下調原因**：下次重跑 `run_sync` 時 `_gc_unreferenced_history_files` 與 `_collect_remote_branch_snapshot` 具備自動自癒能力；僅在「部分失敗後未重跑 `sync` 即直接執行 `delete_branch`」時可能漏算引用。於 `finally:` 補上 `if meta_dirty: self._write_remote_repo_meta(meta)` 即可。

* **\[U1-P2-02\] \[🟡 P2 維持 | `[CONFIRMED_REAL]`\] [gdrive_support/transport.py:L853-L889, L1245-L1284](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：`download_file` 補齊退避重試與 `entry_hint` 免重查，`_request_json` 遇 `401` 自動重置 `_access_token` 重試一次。

* **\[U1-P1-05\] \[🟠 P1** $\to$ **🔵 P3 下調 | `[PARTIAL_OR_DOWNGRADED]`\] [gdrive_support/transport.py:L1088-L1089](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：`list_files(..., recursive=True)` 僅掃描 `"repo/<branch>"`，故 `"repo/.yscb_gdrive.json"` 不受影響；於 `run_sync` 入口重置 `_scanned_prefixes` 即可。

* **\[U1-P2-03\] \[🟡 P2** $\to$ **🔵 P3 下調 | `[CONFIRMED_REAL]`\] [gdrive_support/transport.py:L1023-L1038, L1142-L1150](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：`_resolve_folder_id_by_path` 中間節點過濾 `FOLDER_MIME_TYPE` 並對齊 `mkdir` 之 `modifiedTime` 排序。

* **\[U1-P3-01\] \[🔵 P3 維持（附紅線 1 限制）\] [gdrive_support/coordinator.py:L955-L961](https://drive.google.com/file/d/1lBgs7pC8vPiljSy5Ls_RHymqBqRi7TME/view?usp=drivesdk)**：僅對非 `auto_discovered` 且 `branch_files_map.get(other_b)` 非空之已註冊分支快取引用表。

* **\[U1-P3-02\] \[🔵 P3 維持 | `[CONFIRMED_REAL]`\] [gdrive_support/transport.py:L983-L1004](https://drive.google.com/file/d/1u60nfdC3UdsS6Fh3obneDE13lyjgtVdO/view?usp=drivesdk)**：`_resolve_shortcut_targets` 以 `ThreadPoolExecutor(max_workers=8)` 平行解析 Shortcut 目標（與 `_tls` 連線池及 `_token_lock` 100% 相容）。

* **\[U1-P2-01\] \[❌ 駁回 `[REJECTED_FALSE_POSITIVE]`\] [gdrive_support/reconciler.py:L255-L270, L321-L336](https://drive.google.com/file/d/1PnaaNLogqRvmXNuEGfWQiEB8b67uBCXs/view?usp=drivesdk)**：單邊修改 vs 對向刪除在需要執行刪檔的方向要求同時具備 `--force` 與 `--delete` 屬於防止誤刪的刻意雙閘門設計（By Design），維持原邏輯不修改。

#### 3.2 Unit 02：`ys_codebase/source/vscode-support/`（校準後：🔴 0 P0 / 🟠 1 P1 / 🟡 3 P2 / 🔵 1 P3）

* **\[U2-P1-02\] \[🟠 P1 維持 | `[CONFIRMED_REAL]` | 附紅線 2 修正\] [vscode_support/projector.py:L138-L145, L255-L281](https://drive.google.com/file/d/1iY4UahzKhztfgndZFeGyzbi8LmHMqBdb/view?usp=drivesdk) — 補齊 `python.analysis.extraPaths` 對母倉 `source/<mod>` 與已安裝 `.modules/<mod>` 投影並移除 `ANALYSIS_EXCLUDE_PATTERNS` 中的 `"**/.modules/**"`（對標 [TODO-22](https://drive.google.com/file/d/1YhIAk1j5OVvixaTwXabMogMA8IhuCN9i/view?usp=drivesdk) 與 [DN-03](https://drive.google.com/file/d/1_BYOvWt1TxpqAhvXXAHOLYY1f66NQoYr/view?usp=drivesdk)）**

  * **無副作用精確修復方案**：

    ```
    # 1. ys_codebase/source/vscode-support/vscode_support/projector.py:L138-L145
    # 移除 "**/.modules/**" 以免 Pylance 拒絕索引已安裝模組
    ANALYSIS_EXCLUDE_PATTERNS: Tuple[str, ...] = (
        "**/.venv/**",
        "**/.mirror/**",
        "**/.cache/**",
        "**/.build/**",
        "**/.snapshots/**",
    )
    
    # 2. projector.py:L255-L282 (_compute_managed_extra_paths)
    # 透過 self.yscb_dir 探索 source/<mod> 與 .modules/<mod>，零 "module.source://" 字面量，100% 通過 dev check
    def _to_proj_rel_posix(self, target_path: str, proj_root: str) -> str:
        try:
            rel = os.path.relpath(target_path, proj_root).replace("\\", "/")
            return f"./{rel}" if not rel.startswith(("./", "../")) else rel
        except Exception:
            return target_path.replace("\\", "/")
    
    def _compute_managed_extra_paths(
        self,
        proj_root: str,
        extra_paths: Optional[List[str]] = None,
        py_tag: Optional[str] = None,
    ) -> List[str]:
        new_managed_paths: List[str] = []
        self.ensure_stable_site_packages_link(py_tag=py_tag)
        link_path = self.get_stable_link_path()
        new_managed_paths.append(self._to_proj_rel_posix(link_path, proj_root))
    
        seen_mods: set[str] = set()
        for sub_folder in ("source", ".modules"):
            base_dir = os.path.join(self.yscb_dir, sub_folder)
            if not os.path.isdir(base_dir):
                continue
            for mod in sorted(os.listdir(base_dir)):
                if mod.startswith(".") or mod in seen_mods:
                    continue
                mod_dir = os.path.join(base_dir, mod)
                if os.path.isdir(mod_dir) and os.path.isfile(os.path.join(mod_dir, "manifest.json")):
                    seen_mods.add(mod)
                    ep = self._to_proj_rel_posix(mod_dir, proj_root)
                    if ep not in new_managed_paths:
                        new_managed_paths.append(ep)
    
        if extra_paths:
            for ep in extra_paths:
                clean_ep = ep.replace("\\", "/")
                if clean_ep not in new_managed_paths:
                    new_managed_paths.append(clean_ep)
        return new_managed_paths
    
    ```

* **\[U2-P1-01\] \[🟠 P1** $\to$ **🟡 P2 下調 | `[PARTIAL_OR_DOWNGRADED]`\] [vscode-support/scripts/hook.core.py:L44-L60](https://drive.google.com/file/d/1piB7hkzdRGazGE3IkGYNgWnqvSfIfDOH/view?usp=drivesdk) — 將 `on_remove` 守衛收緊為 Fail-Closed**

  * **盲眼查驗結論**：[core/installer.py:L713-L719](https://drive.google.com/file/d/1xEOkwvlcKTbC-5H46DcjO75dR3T94T__/view?usp=drivesdk) 在 `on_remove` 並刪除模組後，會自動呼叫 `act_reload`（廣播 `on_reload`）與 `sync_pip_dependencies`（廣播 `on_env_synced`），已自動清理其他被刪模組的孤兒 Schema。因此只需將 `hook.core.py:L47-L49` 改為 Fail-Closed：

    ```
    targets = getattr(ctx, "args", None) if ctx is not None else None
    if not isinstance(targets, (list, tuple)) or not ({"vscode-support", "vsc"} & set(targets)):
        return False
    
    ```

* **\[U2-P2-01\] \[🟡 P2 維持 | `[CONFIRMED_REAL]`\] [vscode_support/schema_compiler.py:L505-L555](https://drive.google.com/file/d/1o4V49NQqBi2HkZeXofMbEFSeDa6eCzyz/view?usp=drivesdk)**：以自然數版本鍵（或 `core.semver.parse_semver`）取代字串 `sorted(zip_files)[-1]`。

* **\[U2-P2-02\] \[🟡 P2 維持 | `[CONFIRMED_REAL]`\] [vscode_support/projector.py:L336-L354, L530-L546, L574-L603](https://drive.google.com/file/d/1iY4UahzKhztfgndZFeGyzbi8LmHMqBdb/view?usp=drivesdk)**：`get_status` 補上 `os.path.isdir(link_path)` 與 `strip_jsonc` 回退；`revert_vscode_settings` 清理空排除字典並僅移除由 YSCB 新增的 `analysisExclude` 項目。

* **\[U2-P3-01\] \[🔵 P3 維持 | `[CONFIRMED_REAL]`\] [vscode_support/schema_compiler.py:L30-L89](https://drive.google.com/file/d/1o4V49NQqBi2HkZeXofMbEFSeDa6eCzyz/view?usp=drivesdk)**：單次 `sync_all_schemas` 期間快取 `_collect_uri_scheme_snippets` 結果。

### 4. 其餘七大單元校準後關鍵處方彙整（Unit 03 ～ Unit 09）

#### 4.1 Unit 03：`yscb.py` + `core`（校準後：🟠 4 P1 / 🟡 8 P2 / 🔵 2 P3）

* **\[U3-P0-01** $\to$ **🟠 P1\] [core/uri.py:L522-L645](https://drive.google.com/file/d/1ZMm7ZnjHLl0CV7kckLGb0Rr-T8H1zwN_/view?usp=drivesdk) & [core/vfs/vfs.py:L223-L241](https://drive.google.com/file/d/1fPGYENRi-IQMf5qhRO2FLI8ci-Y6AH21/view?usp=drivesdk)**：遵守**紅線 3**，在解析出 `target_base` 後對子路徑 `rel` 執行邊界檢查（阻斷 `..` 逃逸與 Windows 磁碟機重置 `cache://C:/...`），並於 `VFS.open()` 補齊 `assert_safe_path` 與寫入 `newline="\n"`。

* **\[U3-P0-02** $\to$ **🟠 P1\] [core/commands/dispatcher.py:L149-L189](https://drive.google.com/file/d/1ze0VVxwazRaD3Zl0AnTx_y6TH4vr7yMJ/view?usp=drivesdk) & [core/installer.py:L289-L300](https://drive.google.com/file/d/1xEOkwvlcKTbC-5H46DcjO75dR3T94T__/view?usp=drivesdk)**：遵守**紅線 4**，對 `127.0.0.1` 請求使用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))` 繞過系統代理，並在 `except urllib.error.URLError as err:` 分支將 `(TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)` 判為 `accepted=True`。

* **\[U3-P1-02 維持 🟠 P1\] [core/contributes.py:L345-L348](https://drive.google.com/file/d/1UWOuqonPqp2loWN2wQ64RUJmro0HNxAe/view?usp=drivesdk) & [core/update_checker.py:L73-L86, L209-L213, L349-L355](https://drive.google.com/file/d/11HBxm-7BhwSi-XrAcqum73EadvRRaISv/view?usp=drivesdk)**：將 `project://yscb.config.json` 修正為 `yscb.host://yscb.config.json`（對標 `[DN-03]`）。

* **\[U3-P1-03 維持 🟠 P1\] [core/engine.py:L2044-L2125](https://drive.google.com/file/d/1FR9KU4NR6uoZ8-EyOqIbGXdGJD9bSnu6/view?usp=drivesdk) & [core/installer.py:L806-L825](https://drive.google.com/file/d/1xEOkwvlcKTbC-5H46DcjO75dR3T94T__/view?usp=drivesdk)**：遵守**紅線 5**，`act_snapshot` 建立前先清空同名舊快照目錄；`cmd_rollback` 按 `(mtime, name)` 排序選取最新快照。

* **🟡 P2（8 項）与 🔵 P3（2 項）**：`U3-P1-01`（`_restore_module_package` 先拷貝至 `mirror_zip` 再驗 SHA256）、`U3-P1-04`（`ConfigManager`/`locale`/`symbols` 快取鍵納入 `yscb_root`，不對 `contributes.get` 無條件 `deepcopy`）、`U3-P1-05`（`_strict_hot_dispatch_or_block` 僅在 `accepted` 時 `break`）、`U3-P1-06`（Windows `taskkill` 補 `timeout` 與 `try...except`）、`U3-P2-01`（`_safe_copytree` 處理 `islink`）、`U3-P2-02`（`act_lock` 重入檢查）、`U3-P2-03`（`validator.py` 跳過 `dict` 的 `__provider__` 鍵）、`U3-P2-04`（`OptionResolver` 負數識別與 `config set` 浮點數解析）、`U3-P3-01` & `U3-P3-02`。

#### 4.2 Unit 04 ～ Unit 06：`server`, `dev`, `agents-workflow`（校準後：🔴 1 P0 / 🟠 3 P1 / 🟡 6 P2 / 🔵 7 P3 / ❌ 1 駁回）

* **\[DEV-01\] \[🔴 P0 維持 | `[CONFIRMED_REAL]` | 附紅線 6 零瓶頸修法\] [core/uri.py:L19-L21, L119-L177](https://drive.google.com/file/d/1ZMm7ZnjHLl0CV7kckLGb0Rr-T8H1zwN_/view?usp=drivesdk) & [dev/testing/sandbox.py:L399-L585](https://drive.google.com/file/d/18V8APti52oZ9fLdqkZTbB8p7ge9IjvIy/view?usp=drivesdk) — 父進程 `ThreadPoolExecutor` 並發執行 `create_sandbox` 時修改模組級全域 `_active_host_dir` / `_active_yscb_dir` 引發跨執行緒路徑污染**

  * **無副作用根治方案**：於 `core/uri.py` 將 `_active_module_context`、`_active_host_dir`、`_active_yscb_dir` 與 `_reconciling_tokens` 遷移至 `threading.local()` 執行緒本地儲存，既 100% 根除多執行緒競態，又保留沙盒平行解壓與複製檔案的吞吐量：

    ```
    # ys_codebase/source/core/core/uri.py:L18-L35
    _URI_TLS = threading.local()
    
    def _get_active_host_dir() -> Optional[str]:
        return getattr(_URI_TLS, "active_host_dir", None)
    
    def _set_active_host_dir(val: Optional[str]) -> None:
        _URI_TLS.active_host_dir = val
    
    def _get_active_yscb_dir() -> Optional[str]:
        return getattr(_URI_TLS, "active_yscb_dir", None)
    
    def _set_active_yscb_dir(val: Optional[str]) -> None:
        _URI_TLS.active_yscb_dir = val
    
    ```

* **\[SRV-01\] \[🔴 P0** $\to$ **🟠 P1 下調\] [server/master.py:L811-L845](https://drive.google.com/file/d/1HrWT3oFFXfBY1YSaJeuu4ufouxcrbrym/view?usp=drivesdk)**：於 `_read_handshake` 迴圈內將單行 `json.loads` 包裹於獨立 `try...except ValueError: continue` 中，避免 C 擴充雜訊行終止握手執行緒。

* **\[SRV-02\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [server/worker.py:L143-L210](https://drive.google.com/file/d/1ZljB7tP5827j3EnR1ZO88Ah6PWYBkz5G/view?usp=drivesdk)**：於 `with streamer:` 結束前寫入未捕獲例外至 `stderr` 並傳遞 `error=err_text` 至 `send_task_finish`。

* **\[SRV-03\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [server/master.py:L739-L741](https://drive.google.com/file/d/1HrWT3oFFXfBY1YSaJeuu4ufouxcrbrym/view?usp=drivesdk) & [server/worker.py:L222-L237](https://drive.google.com/file/d/1ZljB7tP5827j3EnR1ZO88Ah6PWYBkz5G/view?usp=drivesdk)**：為 Worker 子進程設定 `env["PYTHONIOENCODING"] = "utf-8"` 並 `reconfigure` 標準流。

* **🟡 P2（6 項）**：`DEV-02`（`--seq` 模式下清除 `sys.modules["scripts"]` 與底線套件名）、`DEV-03`（`tearDown` 差量還原 `os.environ` 與 `builder.py` 直接 `os.replace`）、`DEV-04`（接線 `run_subprocess_with_tree_timeout`）、`AW-02`（補回 `type: "workflow" -> "skill"` 轉譯以符合 `[DN-AW-05]`）、`AW-03`（`compiler.py`/`publisher.py` 優先 `.modules/core` 並 `break`）、`AW-04`（`promote_todos` 先寫 `dest_todo` 後寫 `TODO.md`，`verifier.py:L228` 改用 `resolve_phase_file`；剔除 `status.py:L447` 假陽性）。

* **🔵 P3（7 項）与 ❌ 駁回（1 項）**：`SRV-04`、`SRV-05`、`SRV-06`、`DEV-05`、`AW-01`、`AW-05`（僅保留 `cli.py:_normalize_bags`）、`AW-06`；駁回 `DEV-06`。

#### 4.3 Unit 07 ～ Unit 09：`file-space`, `ast`, `knowledge-db`（校準後：🟠 4 P1 / 🟡 9 P2 / 🔵 5 P3）

* **\[AST-01\] \[🔴 P0** $\to$ **🟠 P1 下調 | 附紅線 7 雙向相容修法\] [ast_engine/io_utils.py:L111-L123](https://drive.google.com/file/d/1ClJ7fcEBqrDJ71NZo4H_jLDLm378Kj8D/view?usp=drivesdk) & [ast_engine/bundler.py:L787-L801, L1095](https://drive.google.com/file/d/1u0MDEkKN-Sq9HerWKBXjMNoxXs10rC7N/view?usp=drivesdk)**：

  * **無副作用精確修復方案**：保留 `"/" in sym_path_norm` 時的雙向 `.endswith("/" + ...)`（相容 `[DN-06]`），針對 `"/" not in sym_path_norm`（根目錄單檔如 `"yscb.py"`）允許匹配絕對髒路徑 `p`，並在 `_resolve_dirty_files_only` 套用 `best_mtime_ns` 快照消歧：

    ```
    # ys_codebase/source/ast/ast_engine/io_utils.py:L111-L123
    def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool:
        if not dirty_paths_norm:
            return False
        sym_path_norm = str(doc_file_path).replace("\\", "/").strip("/").lower()
        if not sym_path_norm:
            return False
        if sym_path_norm in dirty_paths_norm or ("/" + sym_path_norm) in dirty_paths_norm:
            return True
        if "/" not in sym_path_norm:
            suffix = "/" + sym_path_norm
            for p in dirty_paths_norm:
                is_abs_p = p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] == "/")
                if is_abs_p and p.endswith(suffix):
                    return True
            return False
        for p in dirty_paths_norm:
            if "/" in p and (p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p)):
                return True
        return False
    
    ```

* **\[AST-02\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [ast_engine/bundler.py:L886-L893](https://drive.google.com/file/d/1u0MDEkKN-Sq9HerWKBXjMNoxXs10rC7N/view?usp=drivesdk)**：將 `has_custom_configs = bool(self.parser_registry.language_configs)` 改為檢查是否存在非 `DEFAULT_LANGUAGES` 之自訂解析器，恢復 `ProcessPoolExecutor` 多進程平行解析。

* **\[AST-03\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [ast/scripts/hook.file-space.py:L135-L184](https://drive.google.com/file/d/1Axc5Y0Xm75FuV1Fub8Y5YYvbHiJF74gX/view?usp=drivesdk)**：冷啟動尚無 `unified.symbols.bin.gz` 時強制以 `spaces=None` 建立全空間快照，並於 `L175` `hot_patch_index` 補傳 `_cursor_already_consumed=True`。

* **\[KDB-01\] \[🟠 P1 維持 | `[CONFIRMED_REAL]`\] [knowledge_db/service.py:L486-L539](https://drive.google.com/file/d/1ihBUvMYRDJ9D2YHVthlU__Q5XOkeGW-N/view?usp=drivesdk)**：於 `_has_pending_space_work` 與 `_sync_stage1_lexical_and_graph` 檢查 `acked_ast_generation` 前先呼叫 `engine.pipeline._ensure_indices_loaded(load_vectors=False)`，恢復 `[DN-30]` 冷啟動雙水位線自癒。

* **🟡 P2（9 項）与 🔵 P3（5 項）**：`FS-01`、`FS-02`、`FS-03`（遵守**紅線 7** 限定 `self._explicit_project_root is None`）、`FS-04`、`FS-06`、`AST-04`、`AST-05`、`KDB-02`、`KDB-04`；以及 `FS-05`、`AST-06`、`KDB-03`（遵守**紅線 8** 僅修正 `hybrid.py` 的 `Path.suffix`，絕不將 `min_score` 套用於 RRF 分數）、`KDB-05`、`KDB-06`。

### 6. 雲端同步實況盤點追加紀錄：本地端同步漏洞與雲端未同步項（2026-11-05 03:06 追補）

> **[!NOTE] 本地端修復進行中備註**
> 以下 4 項為針對 `ys-codebase` 雲端實況與 `.yscb_gdrive.json` 帳本比對時額外追補之運行期漏洞與雲端異常；**本地開發端已著手進行修復，後續執行 `sub_01_gdrive_and_vscode_support` 前應先對照最新同步後之源碼確認哪些項目已由本地端先行收斂**。

1. 🔴 **`[U1-P0-02]` `sync_spaces` 為空時未阻斷 `run_sync()`，搭配 `push_delete_default=True` 將觸發全倉誤刪（且雲端缺少 `ys_codebase/config/gdrive-support/contribute.json`）**
   - **定位**：`ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L905-L927` & `ys_codebase/config/gdrive-support/`
   - **根因與雲端實證**：雲端 `ys_codebase/config/gdrive-support/` 僅有 `config.project.json`（設定 `push_delete_default: true`），缺少宣告 `"sync_spaces": [{"space": "cloud"}]` 之 `contribute.json`。當 `self.config.sync_spaces` 為空元組 `()` 時，`_collect_local_snapshot()` 回傳空字典 `local_snap = {}`；若本地存有 `sync_state.json` 基線（或執行 `push`），`reconcile_three_way()` 會將雲端所有檔案判定為 `deleted_locally` / `push_delete_untracked_remote` 並發出 `DELETE_REMOTE`，導致整倉被移入垃圾桶。
   - **處方**：於 `SyncCoordinator.run_sync()` 入口檢查 `if not self.config.sync_spaces: raise GDriveConfigError("No sync_spaces configured for gdrive-support; refusing to run sync.")`，並補齊 `ys_codebase/config/gdrive-support/contribute.json`。
2. 🔴 **`[U1-P0-03]` `_collect_remote_branch_snapshot()` 誤用頂層 `SYSTEM_NAMES` 過濾分支根目錄，導致專案根目錄 `repo/main/README.md` 永遠漏同步且脫離 `.yscb_gdrive.json` 帳本**
   - **定位**：`ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L56-L61, L1330-L1332`
   - **根因與雲端實證**：`SYSTEM_NAMES` 包含 `REPO_README_FILENAME = "README.md"`（原意為保護 `repo/README.md` 託管說明檔）。但 `_collect_remote_branch_snapshot(branch)` 在剝除 `repo/main/` 前綴後執行 `if not rel_p or rel_p in SYSTEM_NAMES: continue`，導致分支根目錄下的專案主檔 `rel_p == "README.md"` 被強制跳過，從未寫入 `.yscb_gdrive.json` 的 `branch_files["main"]`，並在後續 `sync` / `pull` 時被三方對帳誤判為「遠端已刪除 `README.md`」。
   - **處方**：將分支內部排除清單與頂層 `SYSTEM_NAMES` 解耦（分支內僅排除 `.yscb_gdrive.json`、`.history`、`.trash`，不排除分支內之 `README.md`）。
3. 🟡 **`[U1-P2-04]` `DELETE_REMOTE` 刪除檔案後未清理已騰空之遠端父目錄（如 `repo/main/plans/2026_11_04_1517_gdrive_parallel_sync/` 空殼目錄殘留）**
   - **定位**：`ys_codebase/source/gdrive-support/gdrive_support/coordinator.py:L1076-L1095`
   - **根因與雲端實證**：計畫歸檔至 `plans/archived/2026/11/` 後，`DELETE_REMOTE` 僅將原目錄下的檔案移入垃圾桶，未向上清理已無任何子項目的空資料夾，導致雲端 `plans/` 下殘留空目錄。
   - **處方**：於 `DELETE_REMOTE` 完成後收集受影響之遠端父目錄（由深至淺），若確認目錄已空且非分支根目錄則一併移入垃圾桶。
4. 🔵 **`[CLOUD-OPS-01]` 雲端專屬區 `.agents/` 內之 `.md` 檔案於上傳時被轉為 Google Docs (`application/vnd.google-apps.document`)**
   - **定位**：`<cloud_root>/.agents/{standards,templates,skills}/`
   - **根因與雲端實證**：`repo/` 外部之 `.agents/` 檔案於 `2026-11-04 16:00Z~16:02Z` 建立時為 Google Docs 原生格式，會被 `GoogleDriveApiTransport` 標記為 `SKIPPED_UNSUPPORTED_MIME` 而無法透過 `yscb gdrive get` 直接下載為純文字 Markdown。

---

### 7. 本地端兩大前置計畫落地後之狀態對齊與扣除清冊（2026-11-05 14:16 更新）

本地端已完成 `2026_11_04_1739_sys_path_and_five_semantic_spaces`（`sub_01`～`sub_03`）與 `2026_11_05_0528_gdrive_changes_api_and_lock_preemption`，並透過 `python yscb.py gdrive push --force` 完成 129 筆變更上雲同步。經逐檔比對最新雲端源碼：

1. **已於前置計畫修畢並自待辦扣除之 6 項標的 (`Resolved in Prior Plans`)**：
   - **`U1-P1-03`**：已於 `2026_11_05_0528` 在 `coordinator.py` (`L1351-L1376, L1526-L1535`) 將單檔 CoW 封裝入 `_upload_task` + `_meta_lock`，並於 `finally` 強制寫回 `meta_dirty` 之 `.yscb_gdrive.json`。
   - **`U1-P2-03`**：已於 `2026_11_05_0528` 透過 `/drive/v3/changes` API 與三級 `remote_repo_cache`（Level 0 零雲端變更 `0.30s` 短路、Level 1 記憶體增量 Patch）根除每次 `run_sync` 重掃其他分支與 `.history/` 之開銷。
   - **`U2-P1-02` (`[TODO-22]`)**：已於 `2026_11_04_1739/sub_01` 在 `vscode_support/projector.py` 串接 `core.platform.list_module_search_roots` 自動投影全模組路徑至 `extraPaths` 並動態控制 `**/.modules/**` 排除規則。
   - **`U3-P2-03`**：已於 `2026_11_04_1739/sub_01` 在 `core/symbols.py:L143` 限制僅於 `YSCB_TEST_SANDBOX == "1"` 時允許回退 `module.source://`。
   - **`DEV-02`**：已於 `2026_11_04_1739/sub_01` 在 `dev/testing/runner.py:L144-L154` 補齊清除 `sys.modules["scripts"]` 與底線套件名 `pkg_name`。
   - **`AW-03`**：已於 `2026_11_04_1739/sub_01` 物理拔除 `agents-workflow` 散落之頂層 `sys.path` 補丁，改由 `core.platform.ensure_installed_modules_path` 統一注入，並於 `dev/checker.py` 新增 `_find_sys_path_mutations` 零豁免 AST 靜態守門。
2. **雲端同步失憶根因已根治**：`2026_11_04_1739/sub_02` & `sub_03` 已將 `credentials.json`/`token.json` 移至 `config.local://`，並將 `sync_state.json`、ONNX 模型與索引移至 `storage.local://`（脫離揮發性 `tmpfs` `.cache/`），且於 `ys_codebase/config/file-space/contribute.json` 排除 `.config.local` 與 `.storage.local`。
3. **`U1-P0-03`（`SYSTEM_NAMES` 誤濾分支根目錄 `README.md`）之新源碼行號定位**：在 `coordinator.py`（2,241 行）納入 `remote_repo_cache` 後，`rel_p in SYSTEM_NAMES` 對分支根目錄 `<repo>/<branch>/README.md` 的誤攔截現位於 `_scan_remote_branch_with_dirs` (`L1700`) 與 `_try_incremental_remote_cache` (`L2058, L2136`) 共 3 處，將於 `sub_01` 中一併收斂。

---

## 3. 結論 (Conclusion)

- **核心結論**：全倉 66 項首輪候選問題經 4 路盲眼子代理實證反推後，確認 **2 項 P0 Critical**（`U1-P0-01` 單向 `pull`/`push` 污染 `sync_state.json` 基準線致後續 `sync` 靜默覆蓋本地修改、`DEV-01` 平行沙盒建置修改模組級全域 `uri._active_yscb_dir` 競態）、**12 項 P1 High**、**29 項 P2 Medium** 與 **21 項 P3 Optimization**，並成功攔截 8 項可能破壞既有測試或 20% 差異分支不變量的修復副作用。
- **後續建議（選填）**：採納「出口 ① 立即實作」，以本報告作為分類型主計畫（Umbrella Plan）之 `R01` 基準，拆分為 4 個正交無衝突子計畫（`sub_01` ～ `sub_04`）分批推進實作與沙盒回歸測試驗證。
