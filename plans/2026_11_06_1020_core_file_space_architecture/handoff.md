# 當前進度與暫停交接現場 (Handoff Context)

> 暫停時間：2026-11-06 12:04  
> 所屬計畫：2026_11_06_1020_core_file_space_architecture  
> 當前所在階段：sub_01_atomic_core_and_l0_cli (狀態: Completed) / 待啟動 sub_02_composite_capabilities (狀態: Pending)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 現場已完成事項
- [x] **主計畫 (`2026_11_06_1020_core_file_space_architecture`) 立項與五大支柱定案**：確立將 `file-space` 內聚併入 `module:core`，採 4 個增量階段子計畫推進（`sub_01` 原子核心與 L0 CLI、`sub_02` 複合能力、`sub_03` Server Hook 整合、`sub_04` 既有模組 SDK 遷移與舊 `module:file-space` 退役）。
- [x] **子計畫 1 (`sub_01_atomic_core_and_l0_cli`) 全週期開發、雙盲審與 P07 結案**：
  - 於 `ys_codebase/source/core/contributes/_format.json` 與 `contributes/core.json` 擴充 `PresetDef`、`SpaceDef`（`entries`、`presets`、`include`、`exclude`）及內建預設集（`core/common-ignore`、`core/python-ignore`、`core/yscb-runtime-ignore` 與動態 `@gitignore`）。
  - 於 `ys_codebase/source/core/core/space/` 實作 100% 純標準庫原子引擎（`exceptions.py`、`schema.py`、`registry.py`、`hasher.py`、`__init__.py`），支援 `<module>/<name>` 與 `project/<name>` 命名空間隔離、短名 `<name>` 自動聯集、三座標預編譯匹配（語意 URI、`project_rel`+`entry_rel` 雙基準相對路徑、檔名/目錄區段）、`os.scandir` 目錄級剪枝走訪與 Blake2b Merkle Root 計算。
  - 於 `core/scripts/cli.py` 與 `core/commands/dispatcher.py` 暴露 L0 CLI（`yscb.py core file-space <subcmd>` 與別名 `yscb.py fs <subcmd>`：`spaces`、`presets`、`match`、`ls`、`hash`），並實作未加 `core` 前綴時對已安裝同名外部模組 `module:file-space` 之自動優先避讓。
  - 通過 `dev check core`、`TestCoreSpaceAtomicEngine` (7/7)、263/263 全量單元測試、實機 6 步端到端驗收，以及 `/code-optimizer` (`D1~D5` `PASSED`) 與 `/testing-sop` (`T-01~T-06` `PASSED`) 雙盲眼子代理審查，完成 `P07_walkthrough.md` 與 `CHANGELOG.md` 結案並提交 Git Commit。

---

## 2. 現場未完成 / 進行中待辦
- [ ] **`sub_02_composite_capabilities` (`Pending`)**：基於 `sub_01` 已建立之 L0 原子操作，展開複合功能之 `P00` 需求討論與實作（涵蓋 `compose: ["space_a", "space_b"]` 空間結果集聯集與二次 `include`/`exclude` 微調、DAG 循環引用檢查、YFP2 持久化快照或差異感知 `diff`/游標機制、以及進階導航能力）。
- [ ] **`sub_03_server_hook_integration` (`Pending`)**：對接 `module:server` 常駐監控與事件 Hook（無 `server` 時天然靜默不觸發）。
- [ ] **`sub_04_ecosystem_migration_and_legacy_removal` (`Pending`)**：遷移 `ast`、`knowledge-db`、`gdrive-support`、`agents-workflow` 至 `core.space` 並正式移除舊 `ys_codebase/source/file-space/`。

---

## 3. 踩坑與注意事項 (Gotchas & Blockers)
- [WARN] **過渡期 CLI 路由避讓機制 (`core/commands/dispatcher.py:L746-L775`)**：在 `sub_04` 正式卸載並移除舊 `module:file-space` 前，頂層未加 `core` 前綴之 `python yscb.py file-space ...` 會優先避讓給外部 `module:file-space`；測試或呼叫 `core.space` 新 CLI 請使用 `python yscb.py fs <subcmd>` 或 `python yscb.py core file-space <subcmd>`。
- [WARN] **`compose` 語意核心共識（待於 `sub_02` 落實）**：先前與開發者已達成共識——`compose: ["space_a", "space_b"]` 合併的是子空間**「各自篩選後的檔案結果集（Evaluated File Set Union）」**（絕非把不同空間的 `include/exclude` 規則混在一鍋煮），且允許在合併後的結果集上再套用當前複合空間自身的 `entries`（補充入口）與 `include` / `exclude`（二次過濾），並支援 `<module>/<space>`、`project/<space>` 精準引用或 `<space>` 短名聯集引用。

---

## 4. 上下文交接 (Compressed Task Context)
- **任務核心脈絡與定案清單**：
  - 五大空間定義支柱中，支柱 ①（`entries`/`include`/`exclude` 三座標匹配）、支柱 ②（顯式 `presets` + `@gitignore`）、支柱 ④（`<owner>/<space>` 隔離與 `<space>` 短名聯集）、支柱 ⑤（多空間歸屬 `matched_spaces` 與 VFS Guard 解耦）已在 `sub_01` 100% 落地。
  - 支柱 ③（`compose` 空間組合代數）與衍生複合能力（快照、跨世代差異、複合 CLI）規劃於 `sub_02_composite_capabilities` 實作。
- **關鍵檔案與行號座標**：
  - `ys_codebase/source/core/contributes/_format.json:L36-L65`：`PresetDef` 與 `SpaceDef` Schema 定義（`sub_02` 將於 `SpaceDef` 擴充 `compose` 欄位）。
  - `ys_codebase/source/core/core/space/schema.py:L170-L315`：`PresetConfig`、`SpaceConfig` 與 `CompiledRuleSet` 預編譯匹配器。
  - `ys_codebase/source/core/core/space/registry.py:L170-L680`：`SpaceRegistry`（含 `_load_all`、`resolve_spaces`、`match_path`、`iter_space_files`；`sub_02` 將於此處擴充 `compose` DAG 拓撲排序與結果集合併）。
  - `ys_codebase/source/core/core/space/hasher.py:L55-L260`：`compute_file_hash` 與 `hash_target`。
  - `ys_codebase/source/core/scripts/cli.py:L660-L920`：`file_space_*` 與 `fs_*` CLI 處理器。
  - `ys_codebase/source/core/tests/test_space.py:L1-L715`：`TestCoreSpaceAtomicEngine` 測試套件。

---

## 5. 下一次接手時的第 1 步 (Immediate Next Action)
- 讀取 `plans/2026_11_06_1020_core_file_space_architecture/umbrella_overview.md` 與本 `handoff.md`，與開發者展開 **`sub_02_composite_capabilities`（步驟 2：基於核心原子功能衍生之複合能力，含 `compose` 空間組合與複合 CLI/快照能力）** 之 `Phase 0 (P00)` 邊界討論，確認後建立 `sub_02_composite_capabilities/P00_discuss.md` 並刪除本 `handoff.md`。
