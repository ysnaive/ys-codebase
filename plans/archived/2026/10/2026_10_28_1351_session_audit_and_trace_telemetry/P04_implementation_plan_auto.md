# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-05` 在 `P03_api_spec_auto.md` 中皆有 1:1 對應介面與 CLI 契約
- [x] **邊界防護**：`EC-01` ~ `EC-05` 皆具備確定性防禦（多候選不盲猜、多計畫/剛歸檔計畫處理、沙盒旁路、512KB 截斷、權限異常降級）
- [x] **依賴純淨**：100% 使用 Python 標準庫，符合 `NFR-01` ($\le 2\text{ms}$ 寫入) 與 `NFR-02` ($\le 150$ 行 Skill、輸出截斷) 約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md`, `docs/agents-workflow/README.md` | Modify | 補充 `core.telemetry` (`cache://core/telemetry.jsonl`) 與 `session-trace` / `/session-audit` 說明 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 新增 `/session-audit` 事後隱形摩擦自檢與 `session-trace` 操作指引 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AW-17]` 多宿主尾行自指信標定錨與跨階段 `mtime` 回寫消歧機制 |
| **微觀註解** | `core/telemetry.py`, `session_trace.py` Docstrings | Modify | 完整標註公開函式與類別之參數、回傳值與異常安全契約 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄本計畫完整變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當 `dev test` 平行啟動多個沙盒進程執行數百個 CLI 測試時，是否會同時競爭寫入宿主 `cache://core/telemetry.jsonl` 造成檔案鎖衝突或灌入大量測試廢料？  
> [*] **防護解法**：`should_record_telemetry()` 第一時間檢查 `os.environ.get("YSCB_TEST_SANDBOX") == "1"`，沙盒測試環境下預設直接返回 `False` 跳過寫入；僅在專門測試 Telemetry 的案例中透過 `YSCB_TELEMETRY_PATH` 指向沙盒內臨時檔案進行驗證，宿主快取 100% 零污染。

> [?] **尖銳問題 2**：在 Antigravity 或 Claude Code 中，若單一對話 `.jsonl` 長達數十 MB（包含大量 `read_file` 原文），`session-trace` 逐行解析是否會拖慢執行時間甚至耗盡記憶體？  
> [*] **防護解法**：(1) 候選檔案探測階段僅 `seek` 讀取檔案尾端 `64 KB` 檢查工作區指紋與尾行信標；(2) 解析鎖定之主 `.jsonl` 時，若檔案大於 `4 MB` 則僅流式讀取頭尾區段或逐行串流過濾，立即丟棄 `tool_response` 大型內文，且 `<thinking>` 摘要強制截斷於 `300` 字元內。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`core` 飛行紀錄器與派發攔截)**：建立 `ys_codebase/source/core/core/telemetry.py`，更新 `core/__init__.py` 與 `core/commands/dispatcher.py`，實作 `cache://core/telemetry.jsonl` 寫入、512KB 滾動截斷與讀取 API (`FR-01`, `EC-03`, `EC-04`, `NFR-01`)。
2. **TASK-02 (`session-trace` 三級軌跡提取與五大訊號引擎)**：建立 `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` 並匯出於 `plans/__init__.py` 與 `agents_workflow/__init__.py`，實作多 `release_targets` 尾行信標定錨、Telemetry 時間窗切片、`mtime` 與 `changelog.md` 回寫消歧、五大摩擦訊號偵測與 Tier 3 逆向審訊保底 (`FR-02` ~ `FR-04`, `EC-01`, `EC-02`, `EC-05`)。
3. **TASK-03 (CLI 掛載與初版 `/session-audit` 技能導出)**：更新 `agents-workflow/scripts/cli.py`、`contributes/core.json`、`contributes/agents-workflow.json` 與 `contributes/_manifest.md`，建立初版 `assets/skills/session-audit/SKILL.md` (`FR-05`, `NFR-02`)。
4. **TASK-04 (子系統 1:1 單元與邊界測試與 `@build` 部署驗證)**：於 `core/tests/test_cli_router.py` 與 `agents-workflow/tests/test_plans_toolchain.py` 補齊正負雙向單元測試，通過 `contributes check`、`dev check`、`dev test` 並安裝 `core@build` 與 `agents-workflow@build` 同步物化 (`FT-01` ~ `FT-05`, `ET-01` ~ `ET-05`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 主視窗直接執行實作**：本計畫新增邏輯集中於 2 個獨立新模組檔（`core/telemetry.py` 約 140 行、`session_trace.py` 約 380 行）與小幅 CLI 註冊，總修改規模精練且邊界清晰，直接於主視窗一氣呵成完成實作與測試。

