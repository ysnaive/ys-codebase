"""
sop_synthesizer.py — SOP 模板 Slot 插槽動態注入與標記剝除合成引擎
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class SOPSynthesizer:
    """SOP 模板 Slot 插槽動態注入與標記剝除合成引擎"""

    SLOT_PATTERN = re.compile(r'<!--\s*YSCB_SLOT:([a-zA-Z0-9_]+)\s*-->')

    @classmethod
    def extract_slots(cls, content: str) -> List[str]:
        """提取文字中宣告的所有 Slot 名稱清單"""
        return cls.SLOT_PATTERN.findall(content)

    @classmethod
    def synthesize_sop(
        cls,
        template_content: str,
        patches: List[Dict[str, Any]],
        contributing_module_root: Optional[Path] = None
    ) -> str:
        """
        將 patches 宣告之內容注入 template_content 對應的 Slot 插槽中。

        :param template_content: 原始基準模板字串 (來自 workflows/commands/*.md)
        :param patches: List of Dict (含 target_slot, position, content_file 或 content)
        :param contributing_module_root: 貢獻模組根目錄，用於解析 content_file 相對路徑
        :return: 注入後的 Markdown 字串 (尚未剝除標記，支援多模組鏈式疊加)
        """
        result = template_content
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            target_slot = patch.get("target_slot")
            position = patch.get("position", "append")
            content_rel_path = patch.get("content_file")
            inline_content = patch.get("content")

            injected_text = ""
            if inline_content:
                injected_text = inline_content.strip()
            elif content_rel_path and contributing_module_root:
                content_file = contributing_module_root / content_rel_path
                if not content_file.is_file():
                    continue
                try:
                    injected_text = content_file.read_text(encoding="utf-8").strip()
                except Exception:
                    continue
            else:
                continue

            if not injected_text:
                continue

            slot_marker = f"<!-- YSCB_SLOT:{target_slot} -->"

            if slot_marker in result:
                if position == "prepend":
                    replacement = f"\n\n{injected_text}\n\n{slot_marker}"
                else:  # append (default)
                    replacement = f"{slot_marker}\n\n{injected_text}\n"
                result = result.replace(slot_marker, replacement, 1)
            else:
                # 找不到對應插槽時，優雅降級附加至檔案末尾 (ET-01)
                result = result.rstrip() + f"\n\n{injected_text}\n"

        return result

    @classmethod
    def strip_slot_markers(cls, content: str) -> str:
        """
        安全正則剝除所有未命中或殘留的 YSCB_SLOT HTML 註解標記，確保輸出純淨。

        :param content: 包含 Slot 標記的 Markdown 字串
        :return: 100% 純淨的 Markdown 字串
        """
        return re.sub(r'<!--\s*YSCB_SLOT:[a-zA-Z0-9_]+\s*-->\n?', '', content)
