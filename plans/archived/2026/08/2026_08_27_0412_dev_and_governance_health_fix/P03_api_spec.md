# API 與介面規格書 (API & Interface Specification)

> 功能名稱：工程健檢缺陷修復與治理 (Dev Tests, PlanVerifier & Docs Alignment)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0412_dev_and_governance_health_fix  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanVerifier` | `source/agents-workflow/agents_workflow/plans/verifier.py` | Internal | 擴充 Header 別名集合，執行多類型計畫與調研手冊合規性審查 |
| `TestDevBuilder` | `source/dev/tests/test_builder.py` | Test | 驗證 builder 在動態版本下的打包與 index.json 產物 |
| `TestReleasePipeline` | `source/dev/tests/test_release_pipeline.py` | Test | 驗證 releaser 在動態版本下的 3-Gate 守門與強制覆蓋發布 |
| `TestSandboxArchitecture` | `source/dev/tests/test_sandbox.py` | Test | 驗證沙盒與打包單元在動態版本下的 hook 保留性 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `PlanVerifier.parse_plan_header` 與別名比對規格
```python
# source/agents-workflow/agents_workflow/plans/verifier.py

VALID_NAME_KEYS = {
    "功能名稱", "計畫名稱", "name", "title",
    "調研主題", "topic", "subject", "主題"
}
VALID_DATE_KEYS = {
    "建立日期", "完成日期", "date", "created_at",
    "日期", "time", "timestamp"
}
VALID_STATUS_KEYS = {
    "狀態", "status", "調研狀態", "research_status",
    "plan_status", "進度"
}

class PlanVerifier:
    def verify_single_file(self, file_path: Path) -> List[Dict[str, str]]:
        """
        稽核單一 Markdown 文件：
        1. 檢查模板指引註解殘留。
        2. 解析 Header metadata，檢查是否包含任一合法之 name, date, status 欄位別名。
        """
```

### 2.2 `dev.tests` 動態版本輔助邏輯
```python
# source/dev/tests 內部輔助

def _get_target_module_version(mod_name: str = "core") -> Tuple[str, str, str]:
    """
    動態取得模組之 (full_version, build_version_tag, release_zip_name)
    例如: ("1.0.1.0", "1.0.1.build", "1.0.1.0.zip")
    """
    manifest_uri = f"module.source://{mod_name}/manifest.json"
    manifest_data = uri.read_json(manifest_uri)
    full_ver = manifest_data.get("version", "1.0.0.0")
    
    # 依 SemVer 規則提取 triplet (如 "1.0.1")
    triplet = full_ver.rsplit(".", 1)[0] if full_ver.count(".") == 3 else full_ver
    build_ver_tag = f"{triplet}.build"
    build_zip_name = f"{build_ver_tag}.zip"
    release_zip_name = f"{full_ver}.zip"
    
    return full_ver, build_ver_tag, build_zip_name, release_zip_name
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: PlanVerifier 增強] 
    └─ source/agents-workflow/agents_workflow/plans/verifier.py (加入別名常數與判定)
[Step 2: dev 模組測試修復]
    ├─ source/dev/tests/test_builder.py (動態解算版本)
    ├─ source/dev/tests/test_release_pipeline.py (動態解算版本與最高 release)
    └─ source/dev/tests/test_sandbox.py (動態解算版本)
[Step 3: docs 知識地圖同步]
    └─ docs/README.md (更新模組表與版本矩陣)
```
