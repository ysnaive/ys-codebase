# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04_docs_standards_and_docstring_alignment  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

- [ ] **FR-01 (STANDARDS.md 協議對齊)**：更新 `docs/_project/STANDARDS.md` 中的 URI 協議表，刪除已廢止的 `temp://`、`module.root://`，補齊 `module.mirror://`、`cache.root://` 等當前真實協議，與 `python yscb.py uri list` 保持 100% 同步。
- [ ] **FR-02 (Core 文檔筆誤與規格對齊)**：修正 `docs/core/DESIGN_NOTES.md` 中 `DN-09` 標題筆誤（原誤植為 `DN-08`）；校準 `docs/core/SEMVER.md` 與宿主版本解析邏輯。
- [ ] **FR-03 (Dev 文檔與指令矩陣對齊)**：更新 `docs/dev/`，補齊 `release-check --all`、`test -k`、`-j`、`--target` 等 CLI 選項；修正 `DN-DEV-02` 與 `yscb-module-dev` 中的 `CmdBags` 範例代碼。
- [ ] **FR-04 (Server 模組 README 建立與架構文檔更新)**：新增 `source/server/README.md`；更新 `docs/server/` 對齊 Master/Worker IPC 職責劃分與 Worker `ServiceManager` 背景服務納管架構。
- [ ] **FR-05 (Knowledge-DB 指令手冊收斂)**：全面盤點 `docs/knowledge-db/`，清除已刪除之 `knowledge-db scan` 與 `bundle` 指令範例，完整更新為 8 大正交標準指令 (`status`, `index`, `search`, `callers`, `callees`, `impact`, `clean`, `model`)。
- [ ] **FR-06 (Agents-Workflow 架構說明與語法更新)**：更新 `docs/agents-workflow/`，明確說明 Stage 1 段落解算與 Stage 2 URI 解算之兩階段架構，並記載 `__$(起始錨點){uri}__` 語意語法。
- [ ] **FR-07 (Roadmap 演進狀態核對與同步)**：全面走訪 `plans/roadmap/`，將已在當前系統中具體落地的規劃（如常駐服務框架、8 大指令收斂、統一快取隔離等）狀態由 `Draft`/`In Progress` 標記為 `Completed`/`Landed`。

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

- **EC-01 (已刪除指令之文檔歷史兼容)**：若歷史 Release Note 提及已刪除指令，保留於歷史日誌並標註 Deprecated，避免無端改寫歷史發布紀錄。
- **EC-02 (自省協議超連結解析)**：自省協議 `@/` 需確保各文檔在本地與遠端渲染環境下皆具備可點擊或指向正確性。

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01 (文檔規範合規性)**：所有 Markdown 產物須符合專案文檔規範（包含標準 YAML Frontmatter、標題層級、GitHub Alert 語法與 Mermaid 圖表規範）。
- **NFR-02 (零死連結與零過期指令)**：全庫文檔超連結 100% 可存取，文檔中出現的 CLI 指令 100% 與目前系統行為一致且可實際執行。

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 修改 `STANDARDS.md` 時必須完全依據 `python yscb.py uri list` 之真實導出協議，嚴禁憑記憶填寫非現行協議名稱。


