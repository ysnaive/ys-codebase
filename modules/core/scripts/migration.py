# -*- coding: utf-8 -*-
"""
YS-Codebase 鏈式線性增量遷移框架 (MigrationRunner)

提供各模組 _migration.py 以裝飾器形式註冊 Minor 代際步階（例：@runner.step("1.1.x")），
並在跨版本升級時以 O(N) 線性順序執行 old < step <= new 區間內的所有遷移邏輯。
"""

import sys
from pathlib import Path
from typing import Callable, List, Tuple, Optional, Union, Dict, Any

from semver import SemVer


def _parse_step_base(step_tag: str) -> SemVer:
    """
    將步階標籤解析為基準 SemVer 物件。
    例如："1.1.x" ➔ SemVer("1.1.0"), "1.2.*" ➔ SemVer("1.2.0"), "2.0.0" ➔ SemVer("2.0.0")
    """
    cleaned = step_tag.strip().replace(".x", ".0").replace(".X", ".0").replace(".*", ".0")
    return SemVer(cleaned)


class MigrationRunner:
    """
    鏈式線性增量遷移執行器。
    """
    def __init__(self):
        self._steps: List[Tuple[SemVer, str, Callable[[Path, Path], None]]] = []

    def step(self, milestone: str) -> Callable:
        """
        裝飾器：註冊特定 Minor 代際步階 handler。
        
        :param milestone: 代際字串 (例: "1.1.x", "1.2.x", "2.0.x" 或 "1.1.0")
        :example:
            @runner.step("1.1.x")
            def migrate_to_1_1(project_root: Path, module_dir: Path):
                # 執行 1.0.x -> 1.1.x 的設定轉移
                pass
        """
        base_ver = _parse_step_base(milestone)

        def decorator(func: Callable[[Path, Path], None]) -> Callable:
            self._steps.append((base_ver, milestone.strip(), func))
            # 依基準版本由小到大排序
            self._steps.sort(key=lambda item: item[0])
            return func

        return decorator

    def run(
        self,
        old_version: Union[str, SemVer],
        new_version: Union[str, SemVer],
        project_root: Optional[Path] = None,
        module_dir: Optional[Path] = None
    ) -> List[str]:
        """
        執行鏈式增量遷移。
        
        :param old_version: 升級前舊版本號
        :param new_version: 升級後目標新版本號
        :param project_root: 專案根目錄 (預設由執行環境動態推導)
        :param module_dir: 模組目錄 (預設為呼叫端路徑)
        :return: 已成功執行的步階標籤清單
        :raises Exception: 任一步階執行失敗時直接拋出例外，供上層觸發 Rollback
        """
        old_v = SemVer(old_version)
        new_v = SemVer(new_version)

        if old_v >= new_v:
            # 降級或相同版本無需遷移
            return []

        # 自動解析路徑
        if module_dir is None:
            module_dir = Path.cwd()
        if project_root is None:
            # 嘗試向上查找專案根目錄
            curr = module_dir.resolve()
            found_root = curr
            while curr != curr.parent:
                if (curr / "yscb_config.json").is_file() or (curr / "AGENTS.md").is_file():
                    found_root = curr
                    break
                curr = curr.parent
            project_root = found_root

        executed_steps: List[str] = []

        for step_base, step_tag, handler in self._steps:
            # 僅執行大於舊版本且不大於新版本的步階
            if old_v < step_base <= new_v:
                print(f"[MIGRATION] 執行增量步階: ➔ {step_tag} ({handler.__name__})...")
                try:
                    handler(project_root, module_dir)
                    executed_steps.append(step_tag)
                except Exception as e:
                    print(f"[ERROR] 執行遷移步階 {step_tag} 失敗: {e}")
                    raise

            if step_base > new_v:
                break

        return executed_steps
