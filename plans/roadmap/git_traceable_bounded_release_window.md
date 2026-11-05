# 技術路線圖：基於 Git 確定性溯源之有界發布視窗與歷史包按需重建機制 (Roadmap)

> 主題：基於 Git 確定性溯源之有界發布視窗與歷史包按需重建機制  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：dev / core 發布生命週期治理、二維度滑動視窗與 Git 歷史確定性重建體系  
> 前置解鎖條件：[Tier 1 - 排序 #2b] 與 #2 (declarative_dev_changeset_and_auto_bump) 及 [TODO-01] 合流推進（同屬 dev/releaser.py 與 index.json 發布管線升級）  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **跨版本三元組之二進位發布包長期累積風險**：雖然發布分支已採單一無父節點孤立提交（Orphan Commit）隔離歷史被淘汰的修訂版（Revision），但若跨語意版本三元組（`Major.Minor.Patch`）皆無限期保留至少一份二進位壓縮包，長期高頻迭代下單一提交樹內的二進位檔案總數仍將隨三元組數量呈線性無界增長。
  - **二進位保存與版本歷史完整性的假性取捨**：由於模組發布壓縮包已實施確定性封裝（固定時間戳、固定權限、字典序排列與換行正規化），且主分支完整保存每一次發布對應之純文字源碼與版本帳本（`index.json`），二進位 `.zip` 本質上僅為特定 Git 源碼樹之確定性衍生快取，無須依賴永久囤積二進位實體檔來維持歷史紀錄完整性。
  - **本機開發與建置快取空間無界堆積**：本機開發建置區（`module.build://`）、安裝鏡像庫（`module.mirror://`）與母倉遠端分支追蹤規則若缺乏自動邊界治理，易隨開發週期在本地磁碟累積冗餘二進位包與遠端追蹤物件。
- **長期願景與目標定位**：
  - 建立「**熱快取有界滑動視窗（$O(1)$ 常數空間上限） + 冷歷史 Git 確定性溯源重建（100% 位元級無損重現）**」的雙層發布儲存架構，確保遠端發布分支與本機快取空間永久封頂於極小常數規模，同時賦予任意歷史已淘汰（`pruned`）版本隨時從主分支 Git 歷史一鍵精確重建並驗證 SHA-256 的能力。
- **範疇與邊界約束**：
  - 涵蓋 `dev` 發布索引滑動視窗策略、歷史版本溯源重建工具鏈、`core` 跨版本向下相容遞補解析，以及母倉與本機快取空間之自動化衛生治理；維持對外部消費端既有 Provider URL 契約之 100% 向下相容。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **熱快取空間常數上界不變量 ($O(1)$ Bounded Active Window)**：遠端發布分支與活躍版本清單（`versions`）僅作為近期活躍版本之「高速下載熱快取層」，每個模組同時保留之活躍二進位包數量必須受雙重上界（同三元組修訂上限 $\times$ 跨三元組保留上限）嚴格約束，徹底消除隨時間線性增長之維度。
  - **源碼樹雙重錨定與可重現封裝不變量 (`git_tree_sha` + Versioned Deterministic Packer)**：版本帳本（`releases[<ver>]`）永久保留全歷史版本之元數據、相依宣告、`.zip` 之 `sha256`、打包格式版本（`pack_format_version`）以及該模組源碼目錄之 **`git_tree_sha`（Git Tree Object SHA-1）** 與 Commit 座標。將源碼完整性驗證錨定於 `git_tree_sha` 並固定打包器壓縮參數與排除規則版本，徹底防範未來 `releaser.py` 演進或跨 Python 版本 `zlib` 壓縮字典微調導致歷史重建包雜湊漂移；同時於執行 `dev release` 前強制驗證目標模組目錄為 **Clean Worktree（無未 commit 之修改）**。
  - **消費端無感相容不變量 (Transparent Consumer Fallback)**：當外部下游專案請求已移出熱快取視窗之歷史 `pruned` 版本時，解析引擎須具備相容版本區間內之自動平滑遞補或按需溯源重建能力，確保舊專案環境初始化與還原不中斷。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **二維度有界滑動視窗 (2D Bounded Sliding Window)**：在既有「同三元組保留最新 $N$ 個 Revision」基礎上，引入「跨三元組僅保留最近 $K$ 個歷史三元組最高版本」之第二維度淘汰規則，將超出視窗之古老三元組自動轉為 `pruned` 並回收實體二進位包。
  - **版本帳本源碼座標綁定與確定性時光機 (Source-Anchored Ledger & Deterministic Rebuilder)**：發布時於 `index.json` 帳本記錄源碼樹溯源錨點；提供按需重建指令，可直接從 Git 歷史提取指定版本之模組源碼樹，於記憶體或暫存區執行確定性封裝並強制校驗產物與帳本 `sha256` 一致性。
  - **本機快取與母倉 Git 追蹤自動治理 (Local Cache & Refspec Hygiene)**：對本機 `.build/` 與 `.mirror/` 實施自動滑動清理，並於母倉開發環境自動維護遠端 `releases` 分支之負向 Refspec（`^refs/heads/releases`）排除規則，確保開發端零二進位追蹤負擔。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：**[Tier 1 - 排序 #2b]** 建議與 `#2 (declarative_dev_changeset_and_auto_bump)` 及 `[TODO-01]` 於同一發布管線升級計畫中合流實作（透過 `roadmap promote` 追加合併至同一計畫目錄之 `roadmap.md`），避免二次拆改 `dev/releaser.py`。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（帳本溯源錨點與按需確定性重建）**：擴充發布流程於 `index.json` 記錄源碼溯源座標（並回填存量版本錨點），實作從 Git 歷史重建指定 `pruned` 版本 `.zip` 並通過 `sha256` 校驗之工具鏈。
  2. **Stage 2（二維度有界滑動視窗與跨三元組平滑遞補）**：升級索引滑動視窗為「同三元組 $N$ 個 + 跨三元組 $K$ 個」雙重封頂，並擴充 `core` 與單檔宿主對古老 `pruned` 版本之同 `Major.Minor` 相容遞補機制。
  3. **Stage 3（本機 `.build`/`.mirror` 快取修剪與母倉 Refspec 自動防呆）**：為本地建置與鏡像空間導入自動容量淘汰機制，並將母倉 `^refs/heads/releases` 排除規則納入開發環境自檢閉環。

