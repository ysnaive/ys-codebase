# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_02_composite_capabilities  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`compose` 空間組合代數、DAG 環路檢測與保留 `entry_path` 之二次過濾 (`FR-01`, `FR-02`, `EC-01`, `EC-02`)**：於 `contributes/_format.json` 將 `SpaceDef.entries` 改為選填 `"list[uri]? | extend"` 並新增 `"compose": "list[str]? | extend"`；於 `SpaceConfig` 強制校驗 `bool(entries) or bool(compose)`（皆空時拋出 `SpaceError`）；於 `SpaceRegistry` 實作 `compose` 引用展開（支援 `<owner>/<space>` 與短名 `<space>` 聯集）、呼叫堆疊 DAG 循環檢測（拋出 `SpaceCycleError`）、保留子空間候選檔 `candidate.entry_path` 之父空間二次過濾（`exclude` 全體剔除 + 顯式 `include` 白名單交集）及 `match_path` 之 `compose:<child_qname>` 溯源。
  2. **導航與執行期動態空間 API (`FR-03`, `EC-03`)**：於 `SpaceRegistry` 與 `core.space` 門面新增 `resolve_file_path(rel_path, space_query=None)` 反解空間內標準相對路徑為實體 `Path`（驗證存在性、符號連結邊界與空間規則匹配），以及 `define_ephemeral_space(name, config)` 動態掛載記憶體空間（`is_ephemeral=True`，快照與游標完全隔離於記憶體字典，零磁碟殘留）。
  3. **`YFP2` 單調世代二進位快照與雙階段增量掃描 (`FR-04`, `EC-04`, `EC-05`)**：新建 `core/space/scanner.py`，實作 `BinarySnapshotManager`（Magic `b"YFP2"` + 16-byte Blake2b Checksum，透過 `core.vfs` 原子寫入至 `storage.local://core/space/snapshots/<target_key>.yfp2.bin`，損毀自動回退 `head_generation=0` 重建）與 `SpaceScanner`（Stage 1 `(mtime_ns, size)` + `10ms` Racy-Clean 防護、Stage 2 統一委派 `core.space.hasher` 計算 16-byte / 32-char hex Blake2b 單檔與 Merkle Root 指紋、支援 `scan`/`refresh`、`patch_files` 多入口刪除定址、`snapshot`、`merkle_root` 與遞迴 `config_hash` 變更自動全掃）。
  4. **多消費者獨立水位游標與複合 CLI (`FR-05`, `FR-06`, `EC-06`)**：實作 `CursorStore`（`storage.local://core/space/cursors/<consumer_id>.json`，受 `RLock` 與 `InterProcessLock` 保護）與 `diff`、`ack`、`reset_cursor`、`clean`、`consume_diff` At-Least-Once 交易 Context Manager；於 `core.json` 與 `core/scripts/cli.py` 為 `file-space` 及 `fs` 擴充 `status`、`scan`、`diff`、`clean` 四大子命令（並將 `--space` 與 `--consumer` 拆分至正交群組 `scope` 與 `consumer`）。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/contributes/_format.json` | Modify | 將 `SpaceDef.entries` 改為選填 `"list[uri]? \| extend"` 並新增 `"compose": "list[str]? \| extend"` |
| `ys_codebase/source/core/core/space/exceptions.py` | Modify | 新增 `SpaceCycleError(SpaceError)` 循環引用異常類別 |
| `ys_codebase/source/core/core/space/schema.py` | Modify | 新增 `compose`、`unresolved_compose`、`is_ephemeral`、`has_explicit_include` 與聯合校驗，並統一 Windows `os.path.normcase` 正斜線正規化 |
| `ys_codebase/source/core/core/space/registry.py` | Modify | 實作 `compose` DAG 展開與循環檢測、二次過濾 `entry_path` 繼承、`match_path` 溯源、`resolve_file_path`、`define_ephemeral_space` 與 `compute_config_hash` |
| `ys_codebase/source/core/core/space/scanner.py` | New | 實作 `FileFingerprint`、`ScanDiffDetail`、`ScanDiffResult`、`SnapshotState`、`BinarySnapshotManager` (`YFP2`)、`CursorStore`、`SpaceScanner` 與門面函式 |
| `ys_codebase/source/core/core/space/__init__.py` | Modify | 匯出所有複合資料結構、`SpaceScanner`、`BinarySnapshotManager`、`CursorStore` 與門面函式 |
| `ys_codebase/source/core/contributes/core.json` | Modify | 為 `file-space` 與 `fs` 新增 `status`、`scan`、`diff`、`clean` 子命令與正交選項群組 |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 實作 `cmd_space_status`、`cmd_space_scan`、`cmd_space_diff`、`cmd_space_clean` 與雙路由入口 |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 新增 4 組完整測試方法涵蓋 `FR-01`~`FR-06`、`EC-01`~`EC-06` 與 `OptionResolver` 正交組合驗證 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 修正 `valid.py` 測試夾具寫入時固定 `newline="\n"` 確保跨平台 SHA-256 一致 |
| `docs/core/README.md` | Modify | 更新 `core.space` 架構說明與 `status`/`scan`/`diff`/`clean` CLI 手冊 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev check core` 0 error / 0 warning (`PASSED`)；`python yscb.py dev test core -q` 266 Passed, 0 Failed, 1 Skipped（100% 通過，其中 `test_space.py` 11/11 全數通過）。
- **實機 UX / 人工驗證**：打包熱部署 `core@1.2.7.build` 並重載常駐 Server 後，全數通過 `scan`、`status`、`diff`、`clean` 與 `ls --pattern` 所有正交選項組合實機測試，並通過 Pre-UX 盲眼靜態審查 (`REVIEW_STATUS: PASSED`)。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 同步追加 `sub_02_composite_capabilities` 核心成果摘要 |
| **中觀 (Meso)** | `docs/core/README.md` | 已完成 | 增補 `core.space` 複合能力（`compose`、`YFP2` 快照、游標與 CLI）說明 |
| **中觀 (Meso)** | `docs/core/uri_protocols.md` | 免更 | 本次未新增頂層 URI Scheme |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 免更 | 設計均為正交清晰合約，無反直覺妥協 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | `core/space/*.py` 與 `core/scripts/cli.py` 公開介面 Docstring 完整對齊 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(core): implement space compose algebra, YFP2 incremental scanner, consumer cursors, and composite CLI (sub_02)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
