# 專題調研與分析報告：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (R01_declarative_readonly_file_lock_sdk_research.md)

> 調研主題：宣告式受控檔案唯讀鎖定 SDK（純 `spaces.readonly` 架構）與五大模組 VFS 透明穿隧碰撞點深度盤點  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_0025_declarative_readonly_file_lock_sdk  
> 調研狀態：Concluded  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 專案中由 CLI 專責編譯、聚合或維護之全託管檔案涵蓋二層物化產物（如 `.modules/`、`.mirror/`、`.snapshots/`、`.vscode/schemas/`、`.agents/.yscb/` 與受管 `.agents/skills/`）及結構化帳本與凍結歷史檔（`plans/*/changelog.md`、`plans/archived/**`、`plans/roadmap/TODO.md`）。
  - 現況下該類檔案於磁碟靜止態仍維持一般可寫權限（`0o644`），一旦 AI Agent 於長任務上下文壓縮後直接調用宿主寫檔工具，或開發者於 IDE 中誤改，極易造成校驗雜湊失效、帳本損毀或於下次 CLI 執行時遭無預警覆寫。
  - 若直接將受控檔案設為作業系統級唯讀（POSIX `0o444`/`0o555`、Windows `FILE_ATTRIBUTE_READONLY`），必須全面徹查 `core`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 五大模組中所有原生檔案寫入、替換、刪除與複製原語，防範 Windows 下 `PermissionError: [WinError 5]` 與唯讀位元跨區污染。
- **調研目標與定案範疇**：
  1. **宣告機制統一為純 `spaces.readonly`**：100% 對齊 `core.gitignore`（`spaces.gitignore`）設計範式，透過各模組 `contributes/core.json` 之 `spaces.readonly` 與 `on_register_file_spaces` 事件動態註冊 `<owner>/readonly`，由 `SpaceRegistry` 自動合成為全域 `/readonly` 聯集空間，零額外 Schema 欄位與零重複動態快取檔。
  2. **盤點 `core/vfs/`（`OSBackend` 與 `VFS`）唯讀穿隧缺口**：定位所有寫入、替換、複製、移動與刪除路徑之唯讀剝離缺口與寫後自動重鎖攔截點。
  3. **五大模組繞過 VFS 原生呼叫定位與範圍收斂**：定位 `core`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 共 18 處原生 `os`/`shutil` 呼叫座標；依開發者決策，本期納入 `core`（含 `snapshot://`）、`vscode-support`、`agents-workflow`（含 `workflow.archived://**`）之 `spaces.readonly` 宣告，而 `dev` 之發布與版本描述檔（`index.json`, `manifest.json`, `yscb.config.json`）則留待 `declarative_dev_changeset_and_auto_bump` 管線計畫由 `dev` 統一管理。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 候選架構方案對比

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：純靜態 Glob 清單（無 `SpaceRegistry` 動態合成與 VFS 穿隧）** | 僅在 JSON 宣告靜態 Glob，每次由各業務模組手動呼叫 `unlock` / `lock` | `core.vfs` 修改極少 | 業務層充斥 `try...finally: lock()` 樣板代碼；無法精確鎖定 `agents-workflow` 依設定動態投射之 `published_files`（易誤鎖使用者自建 Skill 或 `AGENTS.md`） | ★★☆☆☆ |
| **方案 B：另立頂層 `readonly_files` + `file_lock_dynamic.json` 雙軌私有表** | 於 `contributes/_format.json` 新增 `readonly_files` 並另建 `cache://core/file_lock_dynamic.json` | 具備靜態與動態鎖能力 | 與既有 `SpaceRegistry` (`spaces.gitignore` + `on_register_file_spaces`) 機制重複造輪，增加額外持久化檔案與 Schema 維護成本 | ★★★☆☆ |
| **方案 C（最終定案）：純 `spaces.readonly`（靜態 `contributes` + `on_register_file_spaces` 動態合成 `/readonly`）+ `OSBackend` 全透明穿隧** | 100% 復用 `SpaceRegistry` 之 `<owner>/readonly` 與 `/readonly` 合成空間（預編譯 `CompiledRuleSet`）及 `RuntimeContext`；`agents-workflow` 比照 `gitignore` 於 `on_register_file_spaces` 動態注入已發布受管檔案；`OSBackend` 寫前解鎖、寫後依 `/readonly` 自動重鎖並阻斷唯讀位元外洩 | 1. 架構 100% 與 `spaces.gitignore` 正交一致，零多餘設定檔<br>2. 業務模組 `vfs.write_*` 100% 零感知透明穿隧<br>3. 精確保護受管 Skill、歷史歸檔計畫與回滾快照，絕不誤鎖 `AGENTS.md` / `.vscode/settings.json`<br>4. 原生支援 `yscb core file-space` 與 `yscb core file-lock <status\|sync\|lock\|unlock>` | 需同步將五大模組中繞過 VFS 的 18 處原生 `os`/`shutil` 呼叫收斂至 `vfs` | ★★★★★ |

### 2.2 本期納入 `spaces.readonly` 之各模組受控規則總表

| 所屬模組 | 空間識別碼 | 註冊方式 | `entries` | `include` / `exclude` 規則 | 保護標的與邊界說明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`core`** | `core/readonly` | 靜態 (`contributes/core.json`) | `["module://", "module.mirror://", "snapshot://"]` | `include`: `["*"]`<br>`exclude`: `["__pycache__", "*.pyc", "*.pyo", "*.pyd"]` | 保護 `.yscb/.modules/**` 部署態模組源碼、`.yscb/.mirror/**` 鏡像包與 `.yscb/.snapshots/**` 環境回滾快照（候選二）；排除 Python 編譯快取與根目錄 `yscb.py` |
| **`vscode-support`** | `vscode-support/readonly` | 靜態 (`contributes/core.json`) | `["project://"]` | `include`: `["project://.vscode/schemas/**"]` | 保護 `SchemaCompiler` 自動編譯之單檔 JSON Schema；嚴格豁免共管之 `.vscode/settings.json` 與 `.vscode/extensions.json` |
| **`agents-workflow`** | `agents-workflow/readonly` | 靜態 (`contributes/core.json`) + 動態 (`hook.core.py:on_register_file_spaces`) | 靜態：`["workflow.plans://", "workflow.archived://", "workflow.roadmap://"]`<br>動態追加：`["project://"]` | 靜態 `include`: `["workflow.plans://**/changelog.md", "workflow.archived://**", "workflow.roadmap://TODO.md"]`<br>動態 `include`: `publisher.collect_readonly_patterns()`（含 `.agents/.yscb/**` 及 `release_manifest*.json` 之 `published_files`，扣除 `AGENTS.md`、`CLAUDE.md` 與 `mode=="inject"` 軟合併檔） | 保護計畫變更日誌、歷史歸檔計畫庫（候選一）、輕量待辦帳本與工作流編譯投射資產；保留進行中計畫規格書（`P00`~`P07`, `R{NN}`, `roadmap.md`）與自建 Skill 可寫 |
| **`dev`** *(延後至 #2)* | *(暫不宣告 `dev/readonly`)* | 留待 `declarative_dev_changeset_and_auto_bump` | — | — | `module.release://*/index.json`、`module.release://*/*.zip`、`manifest.json` 與 `yscb.config.json` 留待 `dev release` 變更集管線計畫一併納管 |

> **註**：`SpaceRegistry._compile_pass_two()` 在合併 Stage 4 執行期空間時，將針對 `short_name in ("gitignore", "readonly")` 設為 `collapse_wildcard=False`，確保 `core/readonly` 的 `include: ["*"]`（作用於 `module://`, `module.mirror://`, `snapshot://`）與 `agents-workflow/readonly`、`vscode-support/readonly` 的具體路徑規則在各別 `RuleItem` 上精確綁定各自 `entries`，絕不會把 `project://` 根目錄下的非受控檔案誤吸納為萬用字元 `["*"]`。

### 2.3 `core/vfs` 唯讀剝離缺口與寫後重鎖攔截點分析

| 檔案與函式 / 方法 | 行號座標 | 現況缺口剖析 | 穿隧與重鎖處方 |
| :--- | :---: | :--- | :--- |
| `core/vfs/os_backend.py` `write_text` / `write_bytes` (`atomic=False`) | L472-475, L495-498 | 當 `atomic=False` 時直接呼叫 `open(norm_path, "w"/"wb")`，遇唯讀檔立即拋出 `PermissionError`，且寫後未重鎖。 | 開檔前若目標存在且唯讀則先呼叫 `strip_lock_bits(norm_path)`；`finally` 中呼叫 `relock_if_protected(norm_path)`。 |
| `core/vfs/os_backend.py` `atomic_write` | L669-725 | 同目錄新建 `.tmp` 為 `0o644`，`robust_replace` 覆蓋後原唯讀鎖遺失。 | `robust_replace` 完成後呼叫 `relock_if_protected(norm_target)`。 |
| `core/vfs/os_backend.py` `robust_replace` | L96-149 | 1. Windows 下若 `dst_norm` 唯讀，首次 `os.replace` 必敗並觸發 `time.sleep(0.05)` 退避，平白浪費 50ms。<br>2. `EXDEV` 跨分區分支 (L115-133) 未先剝離 `dst_norm` 與 `src_norm` 唯讀位元。 | 執行 `os.replace` 前若 `dst_norm` 存在且唯讀，預先剝離唯讀位元（免除 50ms 延遲）；替換完成後在返回前呼叫 `relock_if_protected(dst_norm)`（確保 `gdrive-support` 後續 `stat()` 取得最終 `st_mtime_ns`）。 |
| `core/vfs/os_backend.py` `copy` & `_safe_copytree` | L592-653 | 1. 目標 `dst` 若已存在且唯讀，`shutil.copy2` 直接崩潰。<br>2. 若來源 `src` 為唯讀（如 `.modules`），`shutil.copy2` 會將 `0o444` 複製污染至非受控目標區（如設定檔或測試沙盒）。 | 覆蓋前先剝離目標唯讀；複製後若目標命中 `/readonly` 則上鎖，若目標**不受保護**則強制補回 `stat.S_IWRITE`（阻斷唯讀位元跨區外洩）。 |
| `core/vfs/os_backend.py` `move` & `atomic_swap_directory` | L336-395, L655-666 | `move` 若退回跨分區 `shutil.move`，刪除唯讀來源會失敗；`atomic_swap_directory` 交換 `.staging_*` 後新目錄內檔案為 `0o644` 未自動上鎖。 | `move` 跨分區分支改用 `copy` + `robust_rmtree`（搬移後對目標檔案依 `is_protected` 重算鎖狀態）；`atomic_swap_directory` 完成後對命中 `/readonly` 之 `target_abs` 執行批次上鎖。 |
| `core/vfs/vfs.py` `VFS.open` | L223-243 | 當 `mode` 含 `"w"`, `"a"`, `"x"`, `"+"` 時直接 `open(resolved, mode)`，未經過 `OSBackend` 穿隧。 | 寫入模式開啟前先剝離唯讀，並透過代理物件於 `close()` / `__exit__()` 時呼叫 `relock_if_protected(resolved)`。 |

### 2.4 五大模組繞過 VFS 之原生檔案操作碰撞矩陣

| 模組 | 檔案路徑與 File ID | 行號座標 | 原生呼叫寫法 | 唯讀鎖定下之失效模式 | 定案修繕方案 |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **`core`** | `core/engine.py` (`1zyTZnKHKz0bYxtDkyfGCvt08kNBtqVpx`) | L255, L739 | `os.replace(tmp_zip, dest_zip_real)` | Windows 下若 `.mirror/<mod>/<ver>.zip` 已存在且為唯讀，直接拋出 `WinError 5`。 | 改用 `vfs.robust_replace`。 |
| **`core`** | `core/engine.py` (`1zyTZnKHKz0bYxtDkyfGCvt08kNBtqVpx`) | L259, L579, L589, L696, L708 | `shutil.copy2(..., dest_zip_real)` | 目標 `.zip` 若唯讀會覆寫失敗；且複製後未觸發受控重鎖。 | 改用 `vfs.copy`。 |
| **`core`** | `core/engine.py` (`1zyTZnKHKz0bYxtDkyfGCvt08kNBtqVpx`) | L1628, L1653, L1673, L1633, L1727 | `os.remove` / `shutil.rmtree` | 清理已部署於 `module://` 之 `configurable/` 模板或 `act_delete(purge=True)` 遇唯讀檔在 Windows 失敗。 | 改用 `vfs.remove` 與 `vfs.robust_rmtree`；並於 `act_reload` Stage 4 (L1878) 掛載 `file_lock.sync(emit_event=False)`。 |
| **`core`** | `core/installer.py` (`1NAVTAFqDFfxcN0ZrdCJUW3lMLpcIDzUM`) | L91, L129, L1064, L1077, L1109, L1119 | `shutil.rmtree` / `shutil.copy2` / `os.remove` | 還原 `.mirror` / `.snapshots` 封包或清理 `.staging_*` 時遇唯讀檔在 Windows 拋錯。 | 改用 `vfs.robust_rmtree`、`vfs.copy`、`vfs.remove`。 |
| **`dev`** | `dev/testing/sandbox.py` (`1KrXTlB_4nN2mTQR_h-QUNwQBftvw62yB`) | L489, L618, L625, L628, L641 | `shutil.rmtree(..., ignore_errors=True)` / `shutil.copytree` | `ignore_errors=True` 在 Windows 靜默殘留 `0o444` 檔案，導致隨後的 `_safe_extract_zip` (L622) 因無法覆寫唯讀檔而崩潰。 | L489, L618, L625, L628 改用 `vfs.robust_rmtree(..., ignore_errors=True)`；L641 複製後確保沙盒目標可正常重部署。 |
| **`dev`** | `dev/builder.py` (`1zjEQWLW2jdjdFjsm1_nTBJ1GatNzIoig`) | L136, L352 | `os.replace` / `os.remove` | 替換或清理既有產物時未穿隧唯讀位元。 | 改用 `vfs.robust_replace` 與 `vfs.remove`。 |
| **`vscode-support`** | `vscode_support/schema_compiler.py` (`1GZdO2Gkoy7q8S11r05MnNABsTiNJAMWc`) | L744 | `os.remove(fpath)` (於 `except OSError: pass` 內) | Windows 下無法刪除 `0o444` 的孤兒 Schema 檔，且錯誤被靜默吞沒。 | 改用 `vfs.remove(fpath, missing_ok=True)`；於 `contributes/core.json` 宣告 `spaces.readonly` 鎖定 `project://.vscode/schemas/**`。 |
| **`agents-workflow`** | `agents_workflow/publisher.py` (`1_95g9k1NW3QFcpfJALuVR492vp6flGhw`) | L773, L981-993 | `os.remove(f_rem)` | Windows 下無法刪除已鎖為 `0o444` 的舊投射檔。 | L773 改用 `vfs.remove(f_rem, missing_ok=True)`；新增 `collect_readonly_patterns()` 供 `hook.core.py:on_register_file_spaces` 註冊 `agents-workflow/readonly`，並於 `publish()` 收尾刷新空間與執行 `file_lock.sync("agents-workflow/readonly")`。 |
| **`agents-workflow`** | `agents_workflow/plans/archiver.py` (`13kWsP8OQFBG1KIdFGIe6QmRDMftBGoO8`) | L130, L138 | `h_target.unlink()` / `shutil.move` | 歸檔計畫時跨分區搬移含唯讀 `changelog.md` 之目錄或覆蓋 `workflow.archived://` 既有唯讀歸檔時拋錯。 | L130 改用 `vfs.remove`、L138 改用 `vfs.move`（搬入 `workflow.archived://` 後自動依 `agents-workflow/readonly` 全樹上鎖為唯讀）。 |
| **`gdrive-support`** | `gdrive_support/transport.py` (`1TII6hYz0kBdPdiRmAn4cxYeoEZvXXuGN`) | L734 | `os.replace(tmp_dst, dst)` | 雲端拉取覆寫本地唯讀受控檔時在 Windows 拋出 `WinError 5`。 | 改用 `vfs.robust_replace(str(tmp_dst), str(dst))`，確保於返回前完成重鎖，使 `coordinator.py` L1367 `stat()` 擷取最終 `st_mtime_ns`。 |
| **`gdrive-support`** | `gdrive_support/sandbox_transport.py` (`1PLgyKUA5klffHS-BKcLLgXpK1EX3f-nR`) | L394, L487, L566 | `shutil.copy2` / `os.replace` / `dst_phys.unlink()` | L394 `upload_file` 將本地 `0o444` 複製至沙盒遠端檔 `dst`，導致第二次上傳覆寫 `dst` 拋出 `PermissionError`。 | L394 複製前/後剝離沙盒遠端儲存檔唯讀位元；L487 改用 `vfs.robust_replace`；L566 改用 `vfs.remove`。 |
| **`gdrive-support`** | `gdrive_support/coordinator.py` (`1Y0v1GOtZC2hoyeIeWZq1BV-sEIh4Lmoo`) | L81, L662, L1206 | `shutil.copy2` / `abs_local.unlink()` | 分支切換或遠端刪除同步時無法刪除本地 `0o444` 受控檔。 | L81 剝離 `.conflict.*.bak` 唯讀；L662 與 L1206 改用 `vfs.remove(str(abs_local), missing_ok=True)`。 |

### 2.5 `core.file_lock` SDK 公開介面與 CLI 命令契約

- **公開 API 契約 (`core/file_lock.py`)**：
  - 查詢與判定（委派 `SpaceRegistry` 之 `/readonly` 空間）：
    - `is_protected(path_or_uri, *, registry=None, project_root=None, yscb_dir=None) -> bool`
    - `inspect_path(path_or_uri, *, registry=None, project_root=None, yscb_dir=None) -> FileLockMatchInfo`
    - `is_file_readonly(path_or_uri) -> bool`
    - `status(target=None, *, registry=None, project_root=None, yscb_dir=None) -> Dict[str, Any]`
  - 權限控制與穿隧：
    - `apply_lock_bits(path_or_uri) -> bool`（POSIX `mode & ~0o222`，保留執行位元；Windows `stat.S_IREAD`）
    - `strip_lock_bits(path_or_uri) -> bool`（POSIX `(mode & 0o777) | 0o200`；Windows `stat.S_IWRITE | stat.S_IREAD`）
    - `relock_if_protected(path_or_uri, *, registry=None) -> bool`（尊重 `RuntimeContext` 之 `writable_scope` 重入深度）
    - `lock_path(target=None, *, registry=None) -> Dict[str, Any]`
    - `unlock_path(target=None, *, registry=None) -> Dict[str, Any]`
    - `sync(space_query="/readonly", *, emit_event=False, registry=None) -> FileLockSyncResult`
    - `@contextmanager writable_scope(path_or_uri=None)`
- **CLI 命令樹 (`core/contributes/core.json` & `core/scripts/cli.py`)**：
  - `python yscb.py core file-lock <status|sync|lock|unlock> [target] [--json]`（支援頂層直呼 `python yscb.py file-lock ...`，全數標註 `server_compatible: true`）。

---

## 3. 結論 (Conclusion)

- **核心結論**：
  1. 透過將宣告機制 100% 統一於 `spaces.readonly`（靜態 `contributes/core.json` + 動態 `on_register_file_spaces` $\to$ `SpaceRegistry` `/readonly` 合成空間），並於 `OSBackend` / `VFS` 植入寫前透明解鎖與寫後自動重鎖，可在不增加任何多餘設定檔與 Schema 欄位的前提下，達成全倉受控資產（含 `.modules/`、`.mirror/`、`.snapshots/`、`.vscode/schemas/`、`.agents/` 受管資產、`changelog.md`、`plans/archived/**` 與 `TODO.md`）之作業系統級 `0o444`/`0o555` 靜止態唯讀保護。
  2. 五大模組中共有 18 處繞過 VFS 的原生 `os`/`shutil` 寫刪操作會在開啟唯讀鎖後引發 Windows `WinError 5` 或權限外洩污染，均已精確定位行號並制定 `vfs` 標準原語替換方案。
- **後續行動**：
  - 本調研報告已與 `P00_discuss.md` 完成 100% 需求對齊（`Concluded`），可直接推進階段 B 全自動實作與 VM 沙盒測試驗證。
