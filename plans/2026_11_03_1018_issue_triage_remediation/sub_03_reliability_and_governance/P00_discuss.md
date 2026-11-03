# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：可靠性強化與工程治理修復 (sub_03_reliability_and_governance)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Reliability & Governance  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依主計畫 [R01_issue_triage.md](../R01_issue_triage.md) 與 [umbrella_overview.md](../umbrella_overview.md) §2，開立 `sub_03_reliability_and_governance`，針對查核確認之 7 項 P1 ~ P2 可靠性與工程治理問題（T-03, T-04, T-06, T-07, T-14, T-15, T-16）進行根因修復。
- **核心目標**：
  - **T-03 (Y-01, P1)**：建立遠端模組 `.zip` 下載與 `yscb.py self-update` 的 SHA-256 完整性驗證與確定性壓縮防呆：
    1. **SSOT 與舊版一次性全量回填**：以 `ys_codebase/release/<mod>/index.json` 之 `releases[<ver>]["sha256"]` 為唯一真理來源（SSOT）；從 `origin/releases` 讀取現有 7 個模組全部 `active` 版本的真實 SHA-256 並一次性回填至 `index.json`。
    2. **確定性壓縮（Deterministic Zip）**：於 `dev/builder.py` 與 `.github/workflows/release-publish.yml` 採用確定性壓縮（檔案字典序、固定 `ZipInfo.date_time = (2020, 1, 1, 0, 0, 0)` 與權限 `0o644`、文字檔換行符正規化為 LF），確保相同源碼內容跨環境打包之 SHA-256 恆等。
    3. **下載端強制驗證與 `--ignore-sha256` 逃生閥（`@build` 豁免）**：正式版（非 `@build`）於 `core/engine.py` 與 `yscb.py` 下載安裝時強制要求 `index.json` 具備有效 `sha256` 並通過比對，缺失或不符立即報錯中斷；僅允許透過顯式 `--ignore-sha256` 跳過檢查；`@build` 本地開發版自部署完全無此限制。`self-update` 除語法與必備結構（`__version__`/`main`）外，強制驗證 `--sha256` 或伴隨 `.sha256`（除非傳入 `--ignore-sha256`）。
  - **T-04 (Y-03, P1)**：消除 `WarmWorker.execute_task`（`server/worker.py`）中 `os.environ.clear()` 與 `os.chdir()` 對同進程背景常駐服務執行緒（`file-space-watcher`、`knowledge-db-worker`）造成的環境變數瞬間清空與工作目錄競態。改用差量環境變數還原（僅更新/新增/刪除變動鍵值），並搭配執行鎖與 `uri.host_scope` / `uri.yscb_scope` 保護。
  - **T-06 (Y-05, P1)**：移除 `OSBackend.atomic_write`（`core/vfs/os_backend.py`）在 Windows `os.replace` 重試耗盡後非原子的 `os.remove(norm_target)` + `shutil.copy2` 破壞性回退；當 `os.replace` 重試耗盡仍失敗時直接拋出 `OSError`，確保目標原檔不因中途失敗而毀損或遺失，並由 `finally` 清理暫存檔。
  - **T-07 (Y-08, P1)**：於 `.github/workflows/ci.yml` 建立自動化 CI 工作流，在 `push` / `pull_request` 時執行 `python yscb.py dev check --all`、`python yscb.py contributes check` 與全模組 pytest 測試套件。
  - **T-14 (Y-06, P2)**：修正 `OSBackend.remove`（`core/vfs/os_backend.py`）對目錄執行 `shutil.rmtree(norm_path, ignore_errors=missing_ok)` 時，因 `missing_ok=True` 傳入 `ignore_errors=True` 而連帶靜默吞掉 `PermissionError` 等非缺失錯誤之缺陷；改為僅忽略 `FileNotFoundError`（`errno.ENOENT`），保留唯讀檔 `chmod` 重試並正常拋出權限或佔用異常。
  - **T-15 (Y-07, P2)**：收斂 `core`、`server` 與 `yscb.py` 非清理路徑之寬泛靜默 `except Exception: pass`（改為精確例外捕捉或補充 `logger.debug` 診斷紀錄），並於 `dev check`（`dev/checker.py`）新增對源碼裸 `except:`（Bare Except）之 AST 靜態檢查告警。
  - **T-16 (Y-09, P2)**：強化 `yscb.py` 宿主啟動腳本版本與內容漂移偵測。遞增 `yscb.py` `__version__`（反映近期主倉變更），並於 `UpdateChecker._check_host_script_update`（`core/update_checker.py`）加入腳本 SHA-256 比對：當本地與遠端/母倉 `yscb.py` 的 `__version__` 相同但內容雜湊不一致（且非純換行符差異）時，能精準偵測並回報內容漂移（Drift）提示更新。
- **既有組件復用與查重 (Reuse Discovery)**：
  - SHA-256 計算與比對復用 Python 標準庫 `hashlib.sha256`；`index.json` 結構擴充直接復用 `dev/builder.py:_update_release_index` 與 `core/engine.py:_download_from_remote_tier` 既有 `releases[<ver>]` 字典。
  - `WarmWorker` URI 範圍綁定復用 `core.uri.host_scope` 與 `core.uri.yscb_scope`。
  - `dev check` 裸 `except:` 檢查直接掛載於 `dev/checker.py:ModuleChecker` 既有 AST 掃描流程。
- **邊界排除 (Explicitly Excluded)**：
  - P3 雜項與打磨項目（T-22 ~ T-40 及 `DEV-01`）一律留待 `sub_04_p3_polish` 處理。
  - 不破壞既有舊版 `release/<mod>/index.json`（無 `sha256` 欄位之歷史版本維持向下相容安裝）。
- **架構影響範圍**：`yscb.py`、`core`（`engine.py`, `update_checker.py`, `vfs/os_backend.py`）、`server`（`worker.py`）、`dev`（`builder.py`, `checker.py`）、`.github/workflows/`（`ci.yml`, `release-publish.yml`）及對應單元測試與 `docs/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 本子計畫分流為 Full Track（涵蓋 `yscb.py`、`core`、`server`、`dev` 與 GitHub Actions CI 工作流之 7 項 P1~P2 可靠性與治理修復）。
- **[P00:DR-02]**（Q1 / T-03 定案）以 `index.json` 之 `releases[<ver>]["sha256"]` 為 SSOT：
  1. 從 `origin/releases` 將現有全部 `active` 舊版本的真實 SHA-256 一次性回填至 `ys_codebase/release/<mod>/index.json`。
  2. `dev/builder.py` 與 `.github/workflows/release-publish.yml` 採用確定性壓縮（Deterministic Zip：排序檔案、固定 `date_time` 與 `external_attr`、文字檔 LF 正規化），確保相同文件內容產出完全一致的 `sha256` 並自動寫入 `index.json`。
  3. `core/engine.py` 與 `yscb.py` 下載正式版模組 `.zip` 時強制要求 `index.json` 具備 `sha256` 且校驗一致（缺失或不符即拋出異常中斷）；僅可透過 `--ignore-sha256` 顯式跳過；`@build` 本地開發版自部署完全豁免。`yscb.py self-update` 驗證 `ast.parse` + 必備頂層符號（`__version__` 與 `main`）並校驗 `--sha256 <hex>` 或遠端伴隨 `.sha256`（支援 `--ignore-sha256`）。
- **[P00:DR-03]**（Q2 / T-04 定案）採方案 A：`WarmWorker.execute_task` 移除 `os.environ.clear()`，改以差量方式（`_restore_env_diff`）同步與還原 `os.environ`，避免同進程背景執行緒在任務切換瞬間讀不到 `PATH` / `HOME` / `YSCB_*`；同時在前台任務執行期間結合任務鎖與 `uri.host_scope(Path(cwd))` 確保 URI 解析與工作目錄一致。
- **[P00:DR-04]**（Q3 / T-06 & T-14 定案）採方案 A：`OSBackend.atomic_write` 移除 Windows 重試耗盡後 `os.remove(norm_target)` + `shutil.copy2` 之非原子回退，重試失敗時直接拋出最後一次 `OSError` 以保全原目標檔；`OSBackend.remove` 移除 `ignore_errors=missing_ok`，改為目錄不存在且 `missing_ok=True` 時直接返回，並於 `onerror` 僅忽略 `FileNotFoundError` 與處理唯讀檔 `chmod` 重試，其餘 `PermissionError` / `OSError` 照常拋出。
- **[P00:DR-05]**（Q4 / T-15 & T-16 & T-07 定案）採方案 A：收斂 `core` / `server` / `yscb.py` 非清理路徑之靜默 `except Exception: pass`，並於 `dev/checker.py` 新增裸 `except:` 靜態檢查告警；`yscb.py` 版本號遞增並於 `UpdateChecker._check_host_script_update` 支援同版本號下之 SHA-256 內容漂移偵測；新增 `.github/workflows/ci.yml` 執行合規檢查與各模組 pytest。

---

## 3. 開放議題與確認紀錄

- **全部議題已定案**：Q1→DR-02、Q2→DR-03、Q3→DR-04、Q4→DR-05。以下保留原評估紀錄：

- **Q1（T-03 / Y-01 遠端下載與 self-update 完整性校驗機制）**：
  - **推薦 (A)**：於 `index.json` 寫入各版本 zip 之 `sha256`（舊版無欄位向下相容跳過），`self-update` 驗證語法 + 必備結構（`__version__`/`main`）並支援 `--sha256` / 伴隨 `.sha256` 校驗。
  - **(B)**：僅在模組 zip 下載時驗證 `index.json` 之 `sha256`，`self-update` 僅擴充必備符號結構檢查。

- **Q2（T-04 / Y-03 WarmWorker 全域 `os.chdir` / `os.environ` 與背景服務執行緒之競態防護）**：
  - **推薦 (A)**：差量還原 `os.environ`（移除 `os.environ.clear()` 避免背景執行緒瞬間遺失環境變數），並於前台任務執行期間以執行鎖/URI scope 保護工作目錄與環境變數。
  - **(B)**：前台任務執行期間直接暫停（pause/resume）Worker 內所有背景常駐服務執行緒，並搭配差量環境變數還原。

- **Q3（T-06 / Y-05 & T-14 / Y-06 `OSBackend` 原子寫入回退與目錄刪除錯誤傳遞）**：
  - **推薦 (A)**：`atomic_write` 重試耗盡後直接拋出 `OSError`（移除 `os.remove + copy2` 破壞性回退以保全原檔）；`OSBackend.remove(missing_ok=True)` 僅忽略 `FileNotFoundError`，保留 `PermissionError` 等異常拋出。
  - **(B)**：`atomic_write` 保留回退但先備份原檔；`OSBackend.remove` 僅忽略 `FileNotFoundError`。

- **Q4（T-15 / Y-07 廣泛 `except Exception: pass` 治理與靜態檢查範圍）**：
  - **推薦 (A)**：收斂 `core` / `server` / `yscb.py` 非清理路徑之靜默 `except Exception: pass`（改為精確例外或 `logger.debug`），並於 `dev check` 新增對裸 `except:` 的靜態檢查告警。
  - **(B)**：僅收斂 `core` / `server` / `yscb.py` 非清理路徑之靜默吞錯，不在 `dev check` 新增規則。

