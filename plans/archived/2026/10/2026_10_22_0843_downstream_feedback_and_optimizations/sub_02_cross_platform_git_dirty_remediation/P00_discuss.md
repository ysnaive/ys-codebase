# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：在跨平台協作情境（例如 Linux 與 Windows 交替開發同一專案）下，執行任何 `python yscb.py` CLI 指令或啟動 YSCB Server，YSCB 會自動就地改寫版本庫追蹤中的兩個檔案：`.vscode/settings.json` 與 `.yscb/storage/agents-workflow/release_manifest.json`，導致未修改業務代碼卻陷入持續性的 Git Working Tree Dirty（ping-pong diff）。
- **核心目標**：
  1. 解決 `agents-workflow` 之 `release_manifest.json` 跨平台 CRLF/LF 指紋漂移與運行期物化狀態檔污染 Git 工作區問題（方案 B1）。
  2. 解決 `core` 之 `IdeProjector` 對 `.vscode/settings.json` 注入單一平台 `.venv` 路徑與 `python.defaultInterpreterPath` 導致跨平台互相覆寫問題（方案 A1）。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動開發者在 `.vscode/settings.json` 中非 `_yscb_managed` 託管之自訂設定項目。
  - 不影響 `storage://` 協議下其他需納入版控共享之靜態資產语义。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `release_manifest.json` 跨平台 LF 正規化與本地狀態隔離（方案 B1）**：
  1. **計算雜湊前強制 LF 正規化**：`ReleasePublisher._get_source_file_sha1` 無論讀取單一文字檔或遞迴走訪目錄型資產（如 `assets/skills/`），在計算 SHA-1 前一律將 `\r\n` 正規化為 `\n`（二進位讀取若可 UTF-8 解碼或含 `\r\n` 時執行 `.replace(b"\r\n", b"\n")`），消除 Windows `core.autocrlf=true` 與 Linux 間的來源指紋差異。
  2. **狀態追蹤檔移至 `cache://` 並納入 `.yscb/.gitignore` 防護**：既然 `.agents/` 物化產物屬 gitignored 的本機生成檔案，將 Project Tier 的發布狀態清單 `PROJECT_MANIFEST_STORAGE_URI` 遷移至 `cache://agents-workflow/project_release_manifest.json`（或統一由 `cache://agents-workflow/` 託管，並在執行時自動平滑遷移與清理舊版 `storage://agents-workflow/release_manifest.json` 殘留檔案）；同時於 `core.installer.INTERNAL_IGNORE_PATTERNS` 及 `PipManager._ensure_gitignore` 增列 `/storage/agents-workflow/release_manifest.json` 確保向後防禦零死角。（依 `[P05:DR-01]` 修訂：不新增任何忽略規則，根治方式為資產轉入 `cache://`）
  3. **時間戳恆定保護**：當 `fingerprint`、`active_targets` 與 `published_files` 均未改變時，嚴禁更新 `updated_at` 或重複寫盤。
- **[P00:DR-02] `.vscode/settings.json` 跨平台雙路徑恆定注入與移除 `defaultInterpreterPath` 自動覆寫（方案 A1）**：
  1. **`python.analysis.extraPaths` 跨平台雙路徑恆定陣列**：`PipManager` 新增 `get_cross_platform_site_packages_dirs(py_tag)`（同時回傳 POSIX `lib/pythonX.Y/site-packages` 與 Windows `Lib/site-packages` 兩種標準結構路徑）。當微環境目錄已存在時，`IdeProjector.sync_vscode_settings` 將雙平台相對路徑一併寫入 `python.analysis.extraPaths` 與 `_yscb_managed.extraPaths`，使檔案內容在 Windows 與 Linux 下 100% 恆定不變，且兩端 Pylance 皆能自動識別有效路徑。
  2. **停止寫入並自動清理舊託管之 `python.defaultInterpreterPath`**：`IdeProjector.sync_vscode_settings` 不再向共用的 `.vscode/settings.json` 寫入隨 OS 變動的 `python.defaultInterpreterPath`；若檢測到現有 `settings.json` 中的 `python.defaultInterpreterPath` 等於舊版 `_yscb_managed.defaultInterpreterPath`（或匹配 `./.yscb/.venv/...` 託管格式），則自動將該鍵值自 `settings.json` 與 `_yscb_managed` 清理移除（若為使用者手動自訂之非託管直譯器路徑則 100% 保留）。

---

## 3. 開放議題與確認紀錄

- [x] 已確認 `release_manifest.json` 採用方案 B1（LF 正規化 + 遷入 `cache://` / 清理舊 `storage://` 殘留並補齊 `.yscb/.gitignore`）。
- [x] 已確認 `.vscode/settings.json` 採用方案 A1（`extraPaths` 跨平台雙路徑恆定注入 + 停止寫入並清理舊託管 `defaultInterpreterPath`）。
- [x] 已確認於增量主計畫下開立 `sub_02_cross_platform_git_dirty_remediation`（Full Track）。

