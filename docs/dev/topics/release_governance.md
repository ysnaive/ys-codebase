---
target: "Dev"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/dev/dev/builder.py"
  - "yscb://source/dev/dev/releaser.py"
  - "yscb://source/core/core/semver.py"
related_docs:
  - "../README.md"
  - "../architecture.md"
  - "../user_guide.md"
last_updated: "2026-11-01"
---

# 發布產物治理與版本時序滑動窗口深度解析 (Release Governance & Retention Policy)

> 本專題文檔深度解析 YS-Codebase 的發布產物治理哲學、3-Revision 時序滑動窗口演算法、跨三元組收斂機制、雙軌釋出元數據 (`type`/`urgency`/`summary`) 與事後相容性修補 (`dev index-patch`) 架構。

---

## 1. 產物治理之設計背景與問題意識

在模組化套件體系中，頻繁的本地發布與 Revision 修正容易導致以下兩大痛點：
1. **產物無節制膨脹**：若每次 `dev release` 均無條件追加 zip，磁碟與遠端 Provider 將累積數百個無用的中間過渡包。
2. **極端清空導致回退失效**：若每次發布清空所有舊產物，當發現最新發布有嚴重缺陷時，使用者與依賴方將失去快速回退（Rollback）至同版本上一 Revision 的彈性。

因此，YS-Codebase 確立了**「有限時序滑動窗口（Bounded Temporal Sliding Window）＋跨階收斂（Cross-Triplet Convergence）」**的產物治理標準。

---

## 2. 產物保留核心演算法架構

```text
[同三元組頻繁發布 (例: 1.0.0.x)]
  發布 1.0.0.0 ──> 保留 [1.0.0.0]
  發布 1.0.0.1 ──> 保留 [1.0.0.1, 1.0.0.0]
  發布 1.0.0.2 ──> 保留 [1.0.0.2, 1.0.0.1, 1.0.0.0]  (滿 3 份)
  發布 1.0.0.3 ──> 淘汰 1.0.0.0 ──> 保留 [1.0.0.3, 1.0.0.2, 1.0.0.1]

[跨三元組升級觸發收斂 (例: 升級至 1.0.1.0)]
  發布 1.0.1.0 ──> 舊三元組 1.0.0 淘汰 1.0.0.1 與 1.0.0.2
                ──> 舊三元組 1.0.0 僅保留最高 [1.0.0.3]
                ──> 總在庫保留: [1.0.1.0, 1.0.0.3]
```

### 2.1 規則一：同三元組至多 3 份 Revision 滑動窗口
在相同的三元主版本號 `X.Y.Z` 內，系統最多同時維護 3 個最新 Revision zip 檔案：
$$\text{Active Revisions} = \{ X.Y.Z.W_n, X.Y.Z.W_{n-1}, X.Y.Z.W_{n-2} \}$$
任何第 4 份及更早的 Revision zip 檔案將在發布時被自動物理刪除（`os.remove`）。

### 2.2 規則二：跨三元組升級舊版收斂至 1 份 Revision
當模組發布了新的 Patch、Minor 或 Major 版本（即三元組由 $T_A$ 升級至 $T_B$），代表過往版本進入維護/凍結狀態：
- 系統自動掃描所有小於或不等於當前三元組的歷史三元組。
- 對於每個歷史三元組，**僅保留其歷史最高 Revision（$X.Y.Z.W_{\max}$）**，將其餘中間過渡 Revision 物理刪除。
- 這樣既保證了歷史大版本均有 1 份穩定基準包可供解析安裝，又徹底清除了所有舊版歷史殘留。

### 2.3 規則三：索引雙軌帳本 SSOT 與四元尾號容忍
- **雙軌版本帳本 (`versions` + `releases`)**：`Builder._update_release_index` 對既有 `index.json` 與本地 `.zip` 執行 3-Revision 滑動視窗後，將活躍可下載版本寫入頂層 `versions` 清單，並於 `releases[<ver>]` 永久保存全歷史版本帳本（標記 `"status": "active" | "pruned"`、`dependencies` 與釋出元數據）。
- **安裝相容性保證**：YS-Codebase 的依賴求解器（`core.semver`）支援三段式語意匹配（如 `>=1.0.0`），且當舊專案鎖定之特定 revision 已標為 `pruned` 時，`yscb.py` 與 `core` 會自動平滑遞補同三元組 (`X.Y.Z.*`) 最高可用 `active` 版本。

---

## 3. 釋出元數據、事後相容性修補與跨版本嚴重度治理

### 3.1 雙軌釋出元數據 (`type` / `urgency` / `summary`)
發布模組時，可透過 `dev release` 或 `dev release-git` 附加選填元數據旗標：
```bash
python yscb.py dev release <module> --type=bugfix --urgency=critical --summary="修復關鍵競爭漏洞"
```
- **雙軌同步寫入**：`Releaser` 會在打包前將 `{"type", "urgency", "summary"}` 寫入 `module.source://<module>/manifest.json["release"]`，並由 `Builder._update_release_index` 同步提取至 `release/<module>/index.json["releases"][<ver>]`。
- **向前相容解析 (Forward-Safe Parsing)**：`UpdateChecker` 對未知 `type` 或 `urgency` 字串絕不拋出例外，未知 `type` 自動轉為大寫標籤 `[<TYPE>]`，未知 `urgency` 安全降級為一般更新提示。

### 3.2 免重打包事後修補 (`dev index-patch`)
當某個已發布版本事後發現與新版 `core` 不相容，或需補齊歷史版本的嚴重度標記時，無須重壓 `.zip` 或遞增版號，可直接執行：
```bash
python yscb.py dev index-patch <module> --ver=1.2.3.0 --dep="core:>=1.1.0,<1.4.0;server:>=1.0.0" --urgency=recommended --summary="標註相容性上界"
```
- **覆寫優先權與離線鏡像快取**：`AtomicEngine` 在依賴求解與 `cmd_update` 時，`index.json["releases"][<ver>]["dependencies"]` 優先權高於 `.zip` 內建之 `manifest.json`，並自動過濾與當前已安裝 `core` 版本衝突之候選版本；同時每次下載或讀取 `index.json` 均會快取至 `module.mirror://<module>/index.json`，並於 `reload` / `rollback` 物化時動態覆寫 `.modules/<module>/manifest.json`，確保離線環境 100% 冪等生效。

### 3.3 跨版本區間掃描與 `[CRITICAL UPDATE]` 告警
- `UpdateChecker` 在探測到可用更新 `latest_ver` 時，會掃描 `index.json["releases"]` 中 `(current_ver, latest_ver]` 區間內的所有版本（**包含已被滑動視窗標記為 `pruned` 的中間版本**）。
- 只要區間內任一版本帶有 `urgency: "critical"`（或 `type: "hotfix"`），即向舊版使用者輸出雙線醒目警告橫幅 `[!] [CRITICAL UPDATE]` 與修補摘要。
