# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  下游模擬完全純淨 Agents 安裝環境反饋 4 項問題：
  1. 下載位置錯誤：`init` 預設的下載網址 404，改用 `--provider` 指向正確位置。
  2. 選擇模式的指令寫法不同：`README` 的寫法（`--add claude`）沒有效果，要改成 `add claude --proj`。
  3. 索引範圍設定的位置不同：`README` 說設在 `config.project.json`，但程式只讀 `contribute.json`，已改放到正確位置。
  4. 誤刪 `AGENTS.md`：安裝時它先自動用 `antigravity` 模式寫了檔案，切換成 `Claude` 模式時，把整份 `AGENTS.md` 刪掉了。已從 git 還原，也再跑了一次發布，確認它不會再動這個檔案。
- **核心目標**：
  1. **宿主腳本自更新 URL 與套件 Provider URL 職責分離**：於 `yscb.py` 拆分 `DEFAULT_PROVIDER_URL`（指向 `.../main/ys_codebase/release`）與 `DEFAULT_SELF_UPDATE_URL`（指向 `.../main/yscb.py`），根除 `init` 預設 404 與 `self-update` 對 `provider` 路徑切割的耦合假設。
  2. **`agents-workflow release-target` CLI 語法互通與契約補齊**：修正 `scripts/cli.py:release_target` 中選項語法（`--add <t> [--proj]`、`--remove <t> [--proj]`）因 `bags.args` 為空而誤入 `--list` 分支以及誤用 `get_option()` 之缺陷，並在 `contributes/core.json` 補齊 `target` 參數與 `--proj` (`--project`) 選項宣告。
  3. **`knowledge-db` 空間設定引導回歸 `contribute.json` (SSOT)**：維持 `SpaceManager` 僅自 Contributes 體系（`config/knowledge-db/contribute.json`）讀取 `spaces` 之架構設計，全面修正 `README.md`、`source/knowledge-db/README.md`、`source/knowledge-db/manifest.json` (`onboarding`) 與 `docs/knowledge-db/` 中誤導使用者寫入 `config.project.json` 的錯誤指引。
  4. **`AGENTS.md` / `CLAUDE.md` 根目錄規範檔軟剝離 (Soft-Unmerge) 保護**：當 `release_target` 切換或移除時，針對軟合併管理的根目錄規範檔（`AGENTS.md`、`CLAUDE.md`），嚴禁直接 `os.remove()` 刪除整份檔案；改為精準剝除 YSCB 管理區塊（及自動生成的預設空殼尾塊），完整保留開發者自訂內容，僅在剝除後剩餘內容為空時才移除空檔。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `SpaceManager` 去讀取 `config.project.json` 中的 `spaces`（堅守 `contribute.json` 與 `config.project.json` 的職責邊界）。
  - 不搬移本倉庫既有 `ys_codebase/release/` 實體目錄位置。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `yscb.py` 宿主自更新來源與模組套件 Provider 來源正交拆分（方案 C）**：
  - **背景**：`yscb.py` 為官方唯一提供的核心入口檔案，來源固定為本專案倉庫根目錄（`https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py`）；而模組套件可由任何第三方或本地開發者提供，`provider` 本質可變（官方預設為 `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release`）。
  - **決策**：在 `yscb.py` 定義兩個獨立常數 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL`。`init` 使用 `DEFAULT_PROVIDER_URL`；`self-update` 預設直接使用 `DEFAULT_SELF_UPDATE_URL`（並支援 `--url` 顯式覆寫），不再透過字串切割 `/release` 猜測腳本位置。
- **[P00:DR-02] `knowledge-db` 之 `spaces` 堅持 `contribute.json` 單一真理來源**：
  - **背景**：在 YSCB 架構中，`spaces`、`thesaurus`、`languages`、`aliases`、`related` 屬於 Contributes 擴充宣告（定義於 `contributes/_format.json`，專案層級配置於 `config/knowledge-db/contribute.json`），而 `config.project.json` 僅存放執行期參數。
  - **決策**：保持 `SpaceManager` 程式碼不變，全面修正根目錄 `README.md`、`source/knowledge-db/README.md`、`source/knowledge-db/manifest.json` (`onboarding`) 及 `docs/knowledge-db/contributes_guide.md` 的設定範例與說明。
- **[P00:DR-03] `release-target` 雙語法相容與 `CmdBags.get_option_value` 修正**：
  - **決策**：修正 `agents-workflow/scripts/cli.py:release_target` 判斷優先序（先檢查 `add` / `remove` 動作與選項，無動作時才預設執行 `list`），改用 `bags.get_option_value("add")` / `get_option_value("remove")`，並於 `contributes/core.json` 補齊 `--proj` (`alias: ["project"]`) 與位置參數宣告，使 `--add claude --proj` 與 `add claude --proj` 均 100% 正常生效。
- **[P00:DR-04] 根目錄規範入口檔 (`agents_md`) 退出 Target 時之非破壞性軟剝離 (Soft-Unmerge)**：
  - **決策**：於 `ReleasePublisher` 新增 `_soft_unmerge_agents_text` / `_cleanup_stale_agents_md` 機制。當過期清理清單 (`files_to_remove`) 中的檔案屬於 `agents_md`（或含 `YSCB_AGENTS_BEGIN` 標記之根目錄規範檔）時：
    1. 僅移除 `<!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->` 區塊（以及當初由 YSCB 初始化的預設空殼占位段落）。
    2. 若剝離後仍有非空白之使用者自訂內容，原地覆寫保留自訂內容，絕不刪除檔案；若剝離後完全為空（代表無任何自訂內容），方移除該檔案。

---

## 3. 開放議題與確認紀錄

- [x] 確認問題 ① 採方案 C（拆分 `DEFAULT_PROVIDER_URL` 與 `DEFAULT_SELF_UPDATE_URL` 獨立常數）。
- [x] 確認問題 ③ 為文檔與 Onboarding 指引誤寫，維持 `SpaceManager` 讀取 `contribute.json` 架構不變並修正文檔。
- [x] 完成本機 `knowledge-db model download` 與 `index` 向量索引建置。

