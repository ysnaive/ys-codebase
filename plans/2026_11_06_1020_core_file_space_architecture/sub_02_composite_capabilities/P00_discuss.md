# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_composite_capabilities  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：於分類型主計畫 `2026_11_06_1020_core_file_space_architecture` 推進第二階段 `sub_02_composite_capabilities`，先盤點現有 `module:file-space` 的快照/差異/導航功能，並確認三項核心設計決策皆採用推薦方案 A。
- **核心目標**：
  1. **空間組合代數 (`compose`)**：於 `SpaceDef` / `SpaceConfig` 支援 `compose: List[str]`（支援 `<owner>/<space>` 精準引用或 `<space>` 短名聯集引用），具備 DAG 循環依賴檢測（`SpaceCycleError`），將被組合子空間各自篩選後的檔案結果集取聯集，再疊加複合空間自身的 `entries` 與二次過濾規則（`presets` / `include` / `exclude`）。
  2. **導航與動態空間 API**：於 `SpaceRegistry` 與 `core.space` 門面補齊 `resolve_file_path(rel_path, space)`（將空間內相對路徑安全反解為磁碟絕對路徑，含符號連結邊界與空間歸屬驗證）與 `define_ephemeral_space(name, config)`（執行期記憶體臨時空間動態掛載）。
  3. **`YFP2` 單調世代二進位快照與雙階段增量掃描 (`SpaceScanner` & `BinarySnapshotManager`)**：於 `core.space` 內聚 `YFP2` 二進位快照讀寫（儲存於 `storage.local://core/space/snapshots/`）、Stage 1 Stat Gate（含 `10ms` Racy-Clean 防護）+ Stage 2 Blake2b 指紋計算、全量掃描 (`scan` / `refresh`)、局部路徑熱修補 (`patch_files`)、以及 $O(1)$ 快照與指紋讀取 (`snapshot` / `merkle_root`)。
  4. **多消費者獨立游標與 At-Least-Once 交易消費 (`CursorStore` & `consume_diff`)**：於 `storage.local://core/space/cursors/<consumer_id>.json`（跨進程鎖於 `cache://core/space/`）維護多消費者游標，提供 `diff`、`ack`、`reset_cursor` 與 `consume_diff` 交易式 Context Manager。
  5. **複合 CLI 子命令擴充 (`yscb.py fs <subcmd>` / `core file-space <subcmd>`)**：在 `sub_01` 已有的 5 個 L0 原子子命令（`spaces`, `presets`, `match`, `ls`, `hash`）基礎上，新增 `status`、`scan`、`diff [--consumer] [--ack]`、`clean [--consumer]` 四個複合子命令，並為 `ls` 擴充 `--pattern <glob>` 二次過濾旗標。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_01` 已建立之 `core.space.{schema,registry,hasher,exceptions}`（`SpaceConfig`、`CompiledRuleSet`、`SpaceRegistry`、`compute_file_hash`、`compute_space_merkle_root`）與 `core.vfs` 原子寫入、`core.platform.InterProcessLock` 跨進程鎖。
  - 吸收並精煉舊 `module:file-space` (`file_space/scanner.py`、`file_space/manager.py`) 之 `YFP2` 二進位序列化格式與 `CursorStore` 游標機制，消除外部模組依賴並統一至 `core.space`。
- **邊界排除 (Explicitly Excluded)**：
  - **不包含** `module:server` 背景 `watchdog` 監聽服務與 `on_file_space_changed` 事件 Hook 對接（明確歸屬 `sub_03_server_hook_integration`）。
  - **不包含** 下游模組（`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`）之 SDK/Contributes 遷移與舊 `module:file-space` 卸載移除（明確歸屬 `sub_04_ecosystem_migration_and_legacy_removal`）。
  - **不包含** `core.vfs` 單點式物理防誤改鎖（File Guard 職責已與 Space 解耦）。
- **架構影響範圍**：
  - `ys_codebase/source/core/contributes/_format.json`（`SpaceDef` 新增 `compose` 欄位）
  - `ys_codebase/source/core/contributes/core.json`（擴充 `file-space` / `fs` 複合子命令：`status`, `scan`, `diff`, `clean` 與 `ls --pattern`）
  - `ys_codebase/source/core/core/space/`（更新 `exceptions.py`, `schema.py`, `registry.py`, `__init__.py`；新增 `snapshot.py` / `scanner.py`）
  - `ys_codebase/source/core/scripts/cli.py`（新增 `status`, `scan`, `diff`, `clean` CLI 處理器與 `ls --pattern` 支援）
  - `ys_codebase/source/core/tests/test_space.py`（新增複合能力、DAG 循環檢測、`YFP2` 快照與游標交易測試）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

  - **[`[P00:DR-01]`] 一次完整內聚本地複合層、16-byte Blake2b 雜湊不變量對齊與臨時空間記憶體隔離（軸一：既有組件復用 & 軸五：邊界鎖定）**：
  - `sub_02` 完整涵蓋 `compose` 空間組合代數、導航與臨時空間 API（`resolve_file_path`、`define_ephemeral_space`）、`YFP2` 二進位世代快照、雙階段增量掃描與局部路徑修補（`scan`、`refresh`、`patch_files`、`snapshot`、`merkle_root`）、多消費者交易游標（`diff`、`ack`、`reset_cursor`、`consume_diff`）。
  - **雜湊長度跨切面不變量統一**：`YFP2` 快照之單檔 `content_hash` 與空間級 `merkle_root` 100% 委派 `core.space.hasher`（統一採 `BLAKE2B_DIGEST_SIZE = 16` / 32-char hex），確保 `fs hash` 與 `fs scan/status/diff` 輸出完全一致。
  - **臨時空間 (`define_ephemeral_space`) 記憶體隔離**：透過 `define_ephemeral_space` 動態註冊之臨時空間，其快照與消費者游標僅駐留於記憶體（In-Memory），絕不寫入正式 `storage.local://core/space/` 磁碟目錄，杜絕測試或臨時空間污染持久化狀態。
  - CLI (`yscb.py fs` / `yscb.py core file-space`) 新增 `status`、`scan`、`diff`、`clean` 四個子命令並為 `ls` 擴充 `--pattern <glob>`，維持 100% 純標準庫且零 `server` 依賴。
- **[`[P00:DR-02]`] `compose` 空間組合代數：`_format.json` 選填 `entries` 聯合校驗、`entry_path` 座標繼承與 DAG 循環防護（軸二：預設值副作用 & 軸三：異常逆向路徑）**：
  - **Schema 選填 `entries` 與聯合非空校驗**：將 `ys_codebase/source/core/contributes/_format.json` 中 `SpaceDef.entries` 調整為選填 `"list[uri]? | extend"`（預設 `[]`），支援純 `compose` 組合空間免填 `entries`；改於 `SpaceConfig.from_dict()` 執行語意聯合校驗，強制要求 `bool(entries) or bool(compose)`（至少一者非空，否則拋出 `SpaceError`）。
  - **結果集聯集與 `entry_path` 繼承之二次過濾語意**：當空間宣告 `compose: ["space_a", "space_b"]` 時，先遞迴解析各子空間（支援 `<owner>/<space>` 精準引用或 `<space>` 短名聯集引用；若偵測到引用環路立即拋出 `SpaceCycleError`）並取得各子空間**各自篩選後的檔案結果集聯集** $U_{\text{compose}}$，再與當前複合空間自身 `entries` 走訪出的候選集 $U_{\text{own}}$ 合併為 $U = U_{\text{compose}} \cup U_{\text{own}}$（同 `rel_path` 衝突時 `U_own` 優先於 `U_compose`，並合併 `matched_spaces`）。
  - 對 $U$ 執行當前複合空間自身的二次過濾與 `match_path` 時，**保留候選檔案原始匹配的 `candidate.entry_path`**，將 `(file_abs, candidate.entry_path, project_root)` 傳入複合空間的 `CompiledRuleSet` 進行三座標匹配（防止子空間匯入檔案因不在父空間 `entries` 下而喪失 `entry_rel` 座標或被誤判為 `outside_entries`）：
    1. **`exclude`（高優先級否決）**：永遠對 $U$ 全體生效，可從被組合的子空間結果中剔除特定檔案或子目錄。
    2. **`include`（白名單縮限）**：若複合空間維持預設 `include: ["*"]`（且 `presets` 未引入限制性 `include`），則保留 $U$ 中所有未被 `exclude` 剔除的檔案；若複合空間**顯式指定了非 `["*"]` 的 `include`**（如 `include: ["*.py"]`），則對 $U$ 全體執行白名單交集過濾。
  - `match_path` 同步支援 `compose` 溯源：當檔案經由子空間組合納入且通過複合空間二次過濾時，該複合空間亦列入 `matched_spaces` 並於規則明細標註來源子空間。
- **[`[P00:DR-03]`] 快照 (`YFP2`) 與消費者游標 (`Cursor`) 之規範化查詢目標 Key 定址、儲存隔離與多空間 `patch_files` 刪除定址協議（軸四：跨切面不變量）**：
  - 持久化快照存放於 `storage.local://core/space/snapshots/`，消費者游標存放於 `storage.local://core/space/cursors/<consumer_id>.json`，跨進程排他鎖存放於 `cache://core/space/`（避免污染 `project://` 且與舊 `storage.local://file-space/` 互不衝突）。
  - 快照與游標以**規範化查詢目標 Key** 定址：查詢短名 `"source"` 時對應聯集快照 `snapshots/source.yfp2.bin` 與游標 key `"source"`；查詢顯式 `"project/source"` 時對應 `snapshots/project__source.yfp2.bin` 與游標 key `"project/source"`；全空間查詢 (`space=None`) 時游標 `space_generations` 記錄各短名空間世代並維護 `__all__` 聚合視圖。
  - 目標空間的 `config_hash` 自動遞迴納入所有參與該短名聯集、所有 `compose` 展開子空間及所引用 `presets` 的規則指紋；一旦任一上游子空間或預設集定義變更，`config_hash` 改變即自動觸發該快照全量重算並推進 `head_generation`。
  - **多空間／組合空間下之 `patch_files(space_query, dirty_paths)` 定址協議**：① 若髒路徑於磁碟仍存在且通過 `registry.match_path(path, space_query)`，依 `matched_spaces[0]` 對應之 `SpaceConfig` 決定 `hash_policy` 與 `large_file_threshold_mb`；② 若路徑已從磁碟刪除或不再匹配空間，透過 `project_root` 及各參與空間（含 `compose` 展開子空間）之 `entry_path` 推算所有候選正規化相對路徑 `rel_path` 比對既有 `prev_state.entries`（或由快照條目紀錄反查），確保即使位於 `project://` 之外的外部 URI `entry` 檔案被刪除時，亦能 100% 精準命中快照條目並標記墓碑 `is_deleted = True`。

---

## 3. 開放議題與確認紀錄

- [x] `sub_02_composite_capabilities` 複合能力範疇與 CLI 子命令集合（已確認採用推薦方案 A：一次完整內聚本地複合層與 `status`/`scan`/`diff`/`clean`/`ls --pattern` CLI）
- [x] `compose` 結合自身 `entries` / `include` / `exclude` 的二次過濾語意（已確認採用推薦方案 A：結果集聯集 + `exclude` 全體剔除 + 顯式非 `["*"]` `include` 全體白名單交集）
- [x] 快照檔 (`YFP2`) 與消費者游標 (`Cursor`) 的命名空間定址粒度（已確認採用推薦方案 A：以規範化查詢目標 Key 獨立儲存於 `storage.local://core/space/`，並將 `compose` 與聯集拓撲納入 `config_hash`）
- [x] 盲眼子代理 (`/blind-subagent`) 方案完備性審查 4 項補強處方（已確認納入 `[P00:DR-01]` ~ `[P00:DR-03]`：統一 16-byte Blake2b 摘要與臨時空間記憶體隔離、`_format.json` `entries` 改選填搭配 `SpaceConfig` 聯合校驗、`compose` 二次過濾繼承 `candidate.entry_path`、以及多空間 `patch_files` 刪除定址協議）
