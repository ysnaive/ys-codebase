"""
C dialect adapter for module:ast.
"""

from pathlib import Path
import re
from typing import Dict

from .cpp import CppDialect


class CDialect(CppDialect):
    language = "c"
    scope_separator = "::"
    supports_partial_aggregation = False

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        inc_re = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)
        for m in inc_re.finditer(source_text):
            header = m.group(1).strip()
            stem = Path(header).stem
            imports[header] = header
            imports[stem] = header
        return imports
