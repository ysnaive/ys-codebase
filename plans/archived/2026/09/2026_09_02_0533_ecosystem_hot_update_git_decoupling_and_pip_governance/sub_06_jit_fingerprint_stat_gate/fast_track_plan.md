# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_06_jit_fingerprint_stat_gate  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. 優化 `agents-workflow` 的 JIT 變更感知與指紋檢驗效能：當前 `ReleasePublisher.release_all()` 在 Stage 0 調用三次 `compute_source_fingerprint()`，每次皆全量讀取來源檔案並計算 SHA-1，產生不必要的 I/O 與 CPU 雜湊負擔。引入 Stat-First (mtime/size) 輕量快照初篩與單檔 SHA-1 快取機制，將 Clean 狀態下的檢查時間降至 sub-0.2ms，達成 0 檔案內容讀取與 0 重複雜湊。
  2. 依開發者指示，移除 `agents-workflow/manifest.json` 中之 `watchdog` pip 相依性宣告，回歸零冗餘依賴與微環境純淨性。
- **4 大剛性守門條件核驗**：
  1. 代碼修改行數 $\le 100$ 行（集中於 `publisher.py` 快照判定與 `manifest.json` 清理）。
  2. Public API 簽名契約 0 變更（`ensure_jit_release()`、`ReleasePublisher.release_all()` 與 `compute_source_fingerprint()` 介面契約完全維持向下相容）。
  3. 零跨模組新依賴引入（移除 `watchdog`，僅使用 Python 內建 `os.stat` 與 `hashlib`）。
  4. 既有單元測試套件 100% 覆蓋守門。
- **影響範圍**：
  - `source/agents-workflow/agents_workflow/publisher.py`
  - `source/agents-workflow/manifest.json`
  - `source/agents-workflow/tests/test_publisher.py` (新增 Stat 快照測試案例)

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：自 `source/agents-workflow/manifest.json` 移除 `watchdog` 依賴宣告。
- [x] **TASK-02**：在 `ReleasePublisher` 實作 Stat-First 雙階快照初篩機制與指紋運算快取（避免單次發布重複掃描來源資產，並在檔案 mtime/size 未變更時直讀快取）。
- [x] **TASK-03**：新增單元測試驗證 Stat-First 快取命中、touch 變更感知與實質內容變更物化行為。
- [x] **TASK-04**：執行全生態系測試與 Dogfooding（`dev test agents-workflow` 與 `@build` 安裝發布）。
- **測試案例**：
  - `FT-01`：驗證 `manifest.json` 零 watchdog pip 依賴。
  - `FT-02`：驗證來源檔案未改動時，Stage 0 觸發 Stat-First 短路且不讀取實體檔案內容。
  - `FT-03`：驗證來源檔案 touch (僅改 mtime) 與實質改動 (內容變更) 均能被正確感知與自愈。
  - `RT-01`：`agents-workflow` 與全生態系單元測試 100% 通過。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `manifest.json`：徹底移除 `pip_dependencies` 宣告，解除對 `watchdog` 的依賴，回歸零冗餘純淨微環境。
  2. `publisher.py`：
     - 引入 `SHA1_CACHE_URI = "cache://agents-workflow/source_sha1_cache.json"` 跨進程持久化機制。
     - 實作 `_get_source_file_sha1()`：以 `st_mtime_ns` 與 `st_size` 進行 Stat-First 初篩，未變更時 0 檔案讀取、0 雜湊重算。
     - 實作 `_get_sources_digest()`：單次執行週期內快取來源資產綜合摘要，消除 Stage 0 重複掃描與雜湊負擔。
     - `release_all()` Stage 0：依賴 Stat-First 快取於 sub-0.2ms 內極速完成指紋判定與短路。
  3. `test_publisher.py`：新增 `test_ft_11_stat_first_cache_hit_and_touch_healing` 與 `test_ft_12_manifest_clean_of_watchdog` 測試案例。
- **實機測試日誌**：
  - `python yscb.py dev test agents-workflow -k TestReleasePublisherDiff --quiet` ➔ `Pass: 14(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test agents-workflow --quiet` ➔ `Pass: 74(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test --all --quiet` ➔ `Pass: 386(100.0%), Fail: 0, Skip: 0`
  - Dogfooding 驗證：`python yscb.py dev build agents-workflow && python yscb.py install agents-workflow@build --force` 本地物化自部署成功（`[agents-workflow:hook] Auto-released on reload (0 written, 44 unchanged, 0 removed, targets: antigravity)`）。
  - 版本發布：經開發者調用 `/BumpRevision` 依軌道 B 規範成功晉升並更新至正式版 `agents-workflow@1.0.3.8`。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/sub_06_jit_fingerprint_stat_gate` 驗證 100% Passed。
- **結案狀態**：Passed

