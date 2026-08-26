# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01~P03：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 測試計畫：[P06_test_plan.md](./P06_test_plan.md) (Confirmed)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：`FR-01` ~ `FR-08` 在 API 規格書（`P03_api_spec.md`）中有 100% 完整的介面簽名與行為規格。
- [x] **邊界防護**：`EC-01` ~ `EC-08` 均定義了專屬例外型別（`ReleaseVersionExistsError`, `VersionRollbackError`, `CyclicDependencyError`）與阻斷防禦機制。
- [x] **依賴純淨**：100% 基於 Python 3.8+ 標準庫（`zipfile`, `json`, `os`, `shutil`, `subprocess`），零外部第三方依賴（符合 `NFR-01`）。
- [x] **Test-First 定稿**：`P06_test_plan.md` 測試案例（`FT-01` ~ `FT-08`, `ET-01` ~ `ET-07`, `RT-01`, `UX-01`）已剛性定稿。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據專案知識庫 7 大抽象維度標準，預排本次交付必須新建或更新的 `docs/` 文件：

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度一** | `workflow.docs://dev/README.md` | Update | 更新 Dev 工具鏈定位、核心功能矩陣與指令索引 |
| **維度二** | `workflow.docs://dev/architecture.md` | Update | 更新 Dev 分層架構、3-Gate 發布守門模型與 3-Revision 滑動窗口演算法 |
| **維度三** | `workflow.docs://dev/user_guide.md` | Update | 撰寫全新 CLI 指令手冊（`build`, `release`, `test`, `bump-*`, `release-check`, `release-git`） |
| **維度七** | `workflow.docs://dev/topics/release_governance.md` | New | 建立「發布產物治理與版本時序滑動窗口」專題架構手冊 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：  
> 若使用者在執行 `dev release-git <mod> "<msg>"` 前，工作區同時存在其他未完成模組的修改，直接執行 `git add -A` 是否會產生污染？  
> 💡 **防護解法**：  
> `Releaser.release_git` 實作時，優先將變更加入範圍鎖定於該模組專屬路徑（`source/<mod>/`、`release/<mod>/`），並在控制台明確提示即將提交的變更摘要，確保本地 Commit 精確可控。

> ❓ **尖銳問題 2**：  
> 若 `release/<mod>/` 歷史倉庫中意外存在無法解析的畸形 zip 檔名（如非標準命名），3-Revision 淘汰演算法是否會崩潰？  
> 💡 **防護解法**：  
> 在 `Builder._update_release_index` 遍歷現存檔案時，使用 `try...except` 嚴格過濾非標準 SemVer 命名的 zip 檔案，跳過非法檔案並輸出 Warning，保障核心發布流程之極致健壯性。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

```text
[TASK-01] 重構 Builder 物理打包與 3-Revision 滑動窗口淘汰演算法
  ├── 檔案: source/dev/dev/builder.py
  ├── 實作 build_module(): 預設自動清空 build/<mod>/，保留 tests/
  ├── 實作 package_release(): 純淨打包 release/<mod>/<ver>.zip
  └── 實作 _update_release_index(): 3-Revision 滑動窗口保留 + 跨三元組升級舊版收斂 + index.json SSOT

[TASK-02] 升級 Tester 端到端測試流水線
  ├── 檔案: source/dev/dev/tester.py
  └── 實作 _run_test(): 預設自動前置執行 Builder.build_module/build_all，支援 --no-build

[TASK-03] 重構 Releaser 純淨發布調度器
  ├── 檔案: source/dev/dev/releaser.py
  ├── 定義例外型別: ReleaseVersionExistsError, VersionRollbackError, CyclicDependencyError
  ├── 實作 release_check(): Gate 1 靜態合規 + Gate 2 版本未重複 + Gate 3 版本未倒退
  ├── 實作 release_module(): 3-Gate 校驗 ➔ Builder.package_release
  ├── 實作 release_all(): Kahn 演算法 DAG 拓撲排序批次發布
  └── 實作 release_git(): test ➔ release-check ➔ release ➔ 本地 git commit & tag (禁 push)

[TASK-04] 重構 CLI 表現層路由派發與邊界防呆
  ├── 檔案: source/dev/scripts/cli.py
  ├── 簡化 build / release 路由解析（對標極簡簽名）
  ├── 重構 test 路由（支援 --no-build）
  ├── 新增 bump-major, bump-minor, bump-patch, bump-revision 路由
  ├── 新增 release-check 路由（阻斷 --all）
  └── 新增 release-git 路由

[TASK-05] 自動化單元與整合測試驗證
  ├── 檔案: test/test_dev_toolchain_refactor.py
  └── 實作 FT-01~08, ET-01~07 自動化測試，執行全系統回歸 RT-01

[TASK-06] 知識庫文檔交付與 Dogfooding 同步
  ├── 交付 docs/dev/ (README.md, architecture.md, user_guide.md, topics/release_governance.md)
  └── 四步閉環流水線 (Build ➔ Regression ➔ Sync ➔ AGENTS.md 軟合併)
```

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立 6 大實作任務嚴格依拓撲層級推進。
- **[P04:DR-02]** 剛性定稿 `P06_test_plan.md`，實作與驗證階段 100% 對齊 FT/ET/RT 測試矩陣。
