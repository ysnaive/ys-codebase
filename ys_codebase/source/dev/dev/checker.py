"""
Compliance & Architecture Checker for YS-Codebase modules.
Implements 5-step compliance check pipeline, 3-tier severity classification,
and AST static security/anti-pattern analysis.
"""
import os
import ast
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, List, Dict, Optional, Any
from core import uri
from core import semver

class CheckSeverity(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

@dataclass
class CheckIssue:
    severity: CheckSeverity
    category: str        # "MANIFEST", "CONTRIBUTES", "PROBING", "STRUCTURE", "ANTIPATTERN", "SYNTAX"
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }

@dataclass
class CheckReport:
    module: str
    issues: List[CheckIssue] = field(default_factory=list)

    @property
    def has_fails(self) -> bool:
        return any(i.severity == CheckSeverity.FAIL for i in self.issues)

    @property
    def has_warns(self) -> bool:
        return any(i.severity == CheckSeverity.WARN for i in self.issues)

    @property
    def status(self) -> CheckSeverity:
        if self.has_fails:
            return CheckSeverity.FAIL
        elif self.has_warns:
            return CheckSeverity.WARN
        return CheckSeverity.PASS

    @property
    def passed(self) -> bool:
        return not self.has_fails

    @property
    def errors(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == CheckSeverity.FAIL]

    @property
    def warnings(self) -> List[str]:
        return [i.message for i in self.issues if i.severity == CheckSeverity.WARN]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "status": self.status.value,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
        }

    def __iter__(self):
        # Backward compatibility with (passed, errors) tuple unpacking
        return iter((self.passed, self.errors))

    def __getitem__(self, index):
        return (self.passed, self.errors)[index]

    def __len__(self):
        return 2


class Checker:
    def __init__(self):
        pass

    def check_module(self, name: str) -> CheckReport:
        report = CheckReport(module=name)
        src_uri = f"module.source://{name}"
        if not uri.exists(src_uri):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Module source not found at {src_uri}.",
                )
            )
            return report

        real_dir = uri.resolve(src_uri)

        # 1. Check manifest.json
        self._check_manifest(name, real_dir, report)

        # 2. Check Core injection (contributes/core.json)
        self._check_core_injection(name, real_dir, report)

        # 3. Check File Structure & Configurable templates
        self._check_file_structure(name, real_dir, report)

        # 4. Check AST Syntax, Zero Probing & Anti-patterns in Python files
        self._check_source_files(name, real_dir, report)

        # 5. Check Test Classes (YSCBTestCase inheritance & mark_passed)
        self._check_test_classes(name, real_dir, report)

        # 6. Check Sandbox Lifecycle Hooks (scripts/hook.dev.py)
        self._check_sandbox_hooks(name, real_dir, report)

        # 7. Check Documentation Path Pollution
        self._check_docs_pollution(name, real_dir, report)

        return report

    def _check_manifest(self, name: str, real_dir: str, report: CheckReport) -> None:
        manifest_path = os.path.join(real_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message="Missing 'manifest.json'.",
                    file_path="manifest.json",
                )
            )
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m_data = json.load(f)

            for field_name in ("name", "version", "entry", "dependencies"):
                if field_name not in m_data:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message=f"Missing required field '{field_name}' in manifest.json.",
                            file_path="manifest.json",
                        )
                    )

            m_name = m_data.get("name")
            if m_name and m_name != name:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Manifest name '{m_name}' does not match directory name '{name}'.",
                        file_path="manifest.json",
                    )
                )

            m_ver = m_data.get("version")
            if m_ver:
                try:
                    semver.parse_semver(str(m_ver))
                except Exception:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message=f"Manifest version '{m_ver}' is not a valid SemVer format.",
                            file_path="manifest.json",
                        )
                    )


            deps = m_data.get("dependencies")
            if deps is not None:
                if not isinstance(deps, (list, dict)):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'dependencies' field must be a list or object.",
                            file_path="manifest.json",
                        )
                    )
                elif name != "core":
                    dep_names = deps if isinstance(deps, list) else list(deps.keys())
                    if "core" not in dep_names:
                        report.issues.append(
                            CheckIssue(
                                severity=CheckSeverity.FAIL,
                                category="MANIFEST",
                                message="Module must explicitly declare 'core' in 'dependencies'.",
                                file_path="manifest.json",
                            )
                        )

            opt = m_data.get("optional")
            if opt is not None:
                if not isinstance(opt, dict):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="MANIFEST",
                            message="'optional' field must be an object/dict mapping module names to config.",
                            file_path="manifest.json",
                        )
                    )
                else:
                    for opt_mod, opt_cfg in opt.items():
                        if not isinstance(opt_cfg, dict):
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.FAIL,
                                    category="MANIFEST",
                                    message=f"Optional module '{opt_mod}' configuration must be an object with 'version' and 'hint'.",
                                    file_path="manifest.json",
                                )
                            )
                        else:
                            if "version" not in opt_cfg or not isinstance(opt_cfg["version"], str) or not opt_cfg["version"].strip():
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="MANIFEST",
                                        message=f"Optional module '{opt_mod}' missing non-empty string 'version'.",
                                        file_path="manifest.json",
                                    )
                                )
                            if "hint" not in opt_cfg or not isinstance(opt_cfg["hint"], str) or not opt_cfg["hint"].strip():
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="MANIFEST",
                                        message=f"Optional module '{opt_mod}' missing non-empty string 'hint'.",
                                        file_path="manifest.json",
                                    )
                                )

            self._check_pip_dependencies(name, m_data, report)
        except Exception as e:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message=f"Invalid JSON in manifest.json: {e}",
                    file_path="manifest.json",
                )
            )

    def _check_pip_dependencies(self, name: str, m_data: Dict[str, Any], report: CheckReport) -> None:
        """
        檢核 manifest.json 中 pip_dependencies 欄位：
        - 若存在，必須為 dict 型態 (否則 CheckIssue FAIL)
        - 鍵名必須為合法的非空套件名稱 (否則 CheckIssue FAIL)
        - 約束值必須為字串或 None (否則 CheckIssue FAIL)
        """
        if "pip_dependencies" not in m_data:
            return

        pip_deps = m_data.get("pip_dependencies")
        if not isinstance(pip_deps, dict):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="MANIFEST",
                    message="'pip_dependencies' field must be an object (dict).",
                    file_path="manifest.json",
                )
            )
            return

        for pkg_name, spec in pip_deps.items():
            if not isinstance(pkg_name, str) or not pkg_name.strip():
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Invalid package name in 'pip_dependencies': '{pkg_name}'. Must be a non-empty string.",
                        file_path="manifest.json",
                    )
                )
            elif spec is not None and not isinstance(spec, str):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="MANIFEST",
                        message=f"Invalid version specification for package '{pkg_name}' in 'pip_dependencies': expected string or null, got {type(spec).__name__}.",
                        file_path="manifest.json",
                    )
                )

    def _check_core_injection(self, name: str, real_dir: str, report: CheckReport) -> None:
        if name == "core":
            return
        core_contribute_path = os.path.join(real_dir, "contributes", "core.json")
        if not os.path.exists(core_contribute_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="CONTRIBUTES",
                    message="Module lacks 'contributes/core.json' declaration. Consider declaring CLI commands or URI schemes.",
                    file_path="contributes/core.json",
                )
            )

        contrib_dir = os.path.join(real_dir, "contributes")
        if not os.path.exists(contrib_dir) or not os.path.isdir(contrib_dir):
            return

        from core.validator import ContributesValidator
        from core import contributes as core_contrib

        # 1. Meta-Check: _format.json if present
        fmt_path = os.path.join(contrib_dir, "_format.json")
        if os.path.exists(fmt_path):
            try:
                with open(fmt_path, "r", encoding="utf-8") as f:
                    fmt_data = json.load(f)
                meta_res = ContributesValidator.validate_format_schema(fmt_data)
                for err in meta_res.errors:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="CONTRIBUTES",
                            message=f"Invalid _format.json schema: [{err.path}] {err.message}",
                            file_path="contributes/_format.json",
                        )
                    )
                for w in meta_res.warnings:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="CONTRIBUTES",
                            message=f"_format.json note: [{w.path}] {w.message}",
                            file_path="contributes/_format.json",
                        )
                    )
            except Exception as e:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Syntax error in 'contributes/_format.json': {e}",
                        file_path="contributes/_format.json",
                    )
                )

        # 2. Ingress & Egress Boundary Check on <target>.json
        try:
            files = [f for f in os.listdir(contrib_dir) if f.endswith(".json")]
        except Exception:
            files = []

        for fname in files:
            if fname.startswith("_"):
                continue  # Special schema / metadata file
            target = fname[:-5]
            f_path = os.path.join(contrib_dir, fname)
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
            except Exception as e:
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Syntax error in 'contributes/{fname}': {e}",
                        file_path=f"contributes/{fname}",
                    )
                )
                continue

            target_fmt = core_contrib.get_format(target)
            if target_fmt is None:
                # Target has not declared _format.json yet (gradual tolerance)
                continue

            val_res = ContributesValidator.validate(target, c_data, donor_mod=name, format_schema=target_fmt, strict_points=True)
            for err in val_res.errors:
                hint = f" ({err.suggestion})" if err.suggestion else ""
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message=f"Schema violation in 'contributes/{fname}': [{err.path}] {err.message}{hint}",
                        file_path=f"contributes/{fname}",
                    )
                )
            for w in val_res.warnings:
                hint = f" ({w.suggestion})" if w.suggestion else ""
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.WARN,
                        category="CONTRIBUTES",
                        message=f"Schema warning in 'contributes/{fname}': [{w.path}] {w.message}{hint}",
                        file_path=f"contributes/{fname}",
                    )
                )

    def _check_file_structure(self, name: str, real_dir: str, report: CheckReport) -> None:
        # 1. Entry point check
        cli_path = os.path.join(real_dir, "scripts", "cli.py")
        if not os.path.exists(cli_path):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Missing entry point 'scripts/cli.py'.",
                    file_path="scripts/cli.py",
                )
            )
        else:
            self._check_cli_compliance(name, cli_path, report)

        # 2. Check for scattered config.*.json at root
        for item in os.listdir(real_dir):
            if item.startswith("config.") and item.endswith(".json"):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="STRUCTURE",
                        message=f"Scattered config template found at module root: '{item}'. Templates must be placed under 'configurable/' directory.",
                        file_path=item,
                    )
                )

        # 3. Check configurable/ templates validity if present
        cfg_dir = os.path.join(real_dir, "configurable")
        if os.path.isdir(cfg_dir):
            for cfg_f in os.listdir(cfg_dir):
                if not (cfg_f.startswith("config.") and cfg_f.endswith(".json")):
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="STRUCTURE",
                            message=f"Non-standard configuration template naming in 'configurable/{cfg_f}'. Expected pattern 'config.*.json'.",
                            file_path=f"configurable/{cfg_f}",
                        )
                    )
                if cfg_f.endswith(".json"):
                    cfg_full = os.path.join(cfg_dir, cfg_f)
                    try:
                        with open(cfg_full, "r", encoding="utf-8") as f:
                            json.load(f)
                    except Exception as e:
                        report.issues.append(
                            CheckIssue(
                                severity=CheckSeverity.FAIL,
                                category="STRUCTURE",
                                message=f"Invalid JSON in 'configurable/{cfg_f}': {e}",
                                file_path=f"configurable/{cfg_f}",
                            )
                        )

        # 4. Check for leftover temp files
        for root, _, files in os.walk(real_dir):
            if "__pycache__" in root or ".pytest_cache" in root or ".git" in root:
                continue
            for f in files:
                if f.endswith((".tmp", ".bak", ".DS_Store")) or f.endswith("~"):
                    rel_p = os.path.relpath(os.path.join(root, f), real_dir).replace("\\", "/")
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.WARN,
                            category="STRUCTURE",
                            message=f"Found leftover temporary/junk file: '{rel_p}'.",
                            file_path=rel_p,
                        )
                    )

        # 5. Check contributes/_manifest.md presence
        contrib_dir = os.path.join(real_dir, "contributes")
        if os.path.isdir(contrib_dir):
            manifest_doc = os.path.join(contrib_dir, "_manifest.md")
            if not os.path.exists(manifest_doc):
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="CONTRIBUTES",
                        message="Module defines 'contributes/' directory but lacks 'contributes/_manifest.md' declaration index.",
                        file_path="contributes/_manifest.md",
                    )
                )
        legacy_fmt_doc = os.path.join(real_dir, "contributes.format.md")
        if os.path.exists(legacy_fmt_doc):
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.WARN,
                    category="CONTRIBUTES",
                    message="Legacy 'contributes.format.md' detected. Please migrate to 'contributes/_manifest.md'.",
                    file_path="contributes.format.md",
                )
            )

    def _check_cli_compliance(self, name: str, cli_path: str, report: CheckReport) -> None:
        """
        以 AST 靜態檢核 scripts/cli.py 的合規性：
        1. 必須宣告函式 def process(args)
        2. 絕對不可有 def main(...)
        3. 絕對不可有 if __name__ == '__main__':
        4. 頂層節點除 Docstring、Import、ImportFrom、FunctionDef、ClassDef 外，
           嚴禁任何未包覆在 func/class 內的執行陳述式。
        """
        try:
            with open(cli_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=cli_path)
        except Exception as e:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="SYNTAX",
                    message=f"Syntax error in 'scripts/cli.py': {e}",
                    file_path="scripts/cli.py",
                )
            )
            return

        has_process_func = False
        has_main_func = False
        has_if_name_main = False
        invalid_top_level_nodes = []

        declared_funcs = set()
        for node in tree.body:
            # 頂層節點白名單過濾
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)):
                continue
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                declared_funcs.add(node.name)
                if node.name == "process":
                    has_process_func = True
                elif node.name == "main":
                    has_main_func = True
                continue
            elif isinstance(node, ast.Expr):
                # 僅允許作為字串常量（如 module docstring）
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    continue
                else:
                    invalid_top_level_nodes.append((getattr(node, "lineno", 0), "top-level expression"))
            elif isinstance(node, ast.If):
                # 檢測是否為 if __name__ == '__main__':
                is_name_main = False
                if isinstance(node.test, ast.Compare):
                    left = node.test.left
                    if isinstance(left, ast.Name) and left.id == "__name__":
                        for comp in node.test.comparators:
                            if isinstance(comp, ast.Constant) and comp.value == "__main__":
                                is_name_main = True
                                break
                if is_name_main:
                    has_if_name_main = True
                else:
                    invalid_top_level_nodes.append((getattr(node, "lineno", 0), "top-level if-statement"))
            else:
                stmt_type = type(node).__name__
                invalid_top_level_nodes.append((getattr(node, "lineno", 0), f"top-level statement '{stmt_type}'"))

        # 檢測規則 1: 必須宣告 process，或宣告新版 commands.cmd 定義之精確命令函式
        is_new_contract = False
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(cli_path)))
        contrib_file = os.path.join(module_dir, "contributes", "core.json")
        if os.path.isfile(contrib_file):
            try:
                import json
                with open(contrib_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    cmd_map = cdata.get("commands", {}).get("cmd", {})
                    if isinstance(cmd_map, dict) and cmd_map:
                        if any(cmd_name in declared_funcs or f"cmd_{cmd_name}" in declared_funcs for cmd_name in cmd_map):
                            is_new_contract = True
            except Exception:
                pass

        if not has_process_func and not is_new_contract:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Missing required entry function 'def process(args)' in 'scripts/cli.py'.",
                    file_path="scripts/cli.py",
                )
            )

        # 檢測規則 2: 禁絕 main
        if has_main_func:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Forbidden function 'main' found in 'scripts/cli.py'. Module CLI entries must only declare 'def process(args)'.",
                    file_path="scripts/cli.py",
                )
            )

        # 檢測規則 3: 禁絕 if __name__ == '__main__':
        if has_if_name_main:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="STRUCTURE",
                    message="Forbidden 'if __name__ == \"__main__\":' execution block found in 'scripts/cli.py'. Module CLI must be purely importable.",
                    file_path="scripts/cli.py",
                )
            )

        # 檢測規則 4: 禁絕未包覆在 func/class 之頂層執行內容
        for lineno, desc in invalid_top_level_nodes:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="ANTIPATTERN",
                    message=f"Forbidden {desc} outside function/class at line {lineno} in 'scripts/cli.py'. All executable statements must be enclosed inside functions or classes.",
                    file_path="scripts/cli.py",
                    line_number=lineno,
                )
            )

    def _check_source_files(self, name: str, real_dir: str, report: CheckReport) -> None:
        for root, _, files in os.walk(real_dir):
            if "__pycache__" in root or ".pytest_cache" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue

                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                is_test_file = rel_p.startswith("tests/")

                try:
                    with open(full_p, "r", encoding="utf-8") as py_f:
                        content = py_f.read()
                    tree = ast.parse(content, filename=rel_p)
                except SyntaxError as se:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"SyntaxError in {rel_p}:{se.lineno}: {se.msg}",
                            file_path=rel_p,
                            line_number=se.lineno,
                        )
                    )
                    continue
                except Exception as e:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"Error parsing {rel_p}: {e}",
                            file_path=rel_p,
                        )
                    )
                    continue

                # AST string literal inspections
                for node in ast.walk(tree):
                    # Check string constants in AST
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        s_val = node.value
                        lineno = getattr(node, "lineno", None)

                        # FR-03: Zero Probing for source space
                        if name not in ("dev", "core") and not is_test_file:
                            if "module.source://" in s_val:
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="PROBING",
                                        message=f"Zero Probing violation: 'module.source://' access detected in '{rel_p}:{lineno}'.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )

                        # FR-07: Anti-Pattern Check (Reinventing the wheel)
                        if name not in ("core", "dev") and not is_test_file:
                            if s_val in ("config.project.json", "config.local.json"):
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="ANTIPATTERN",
                                        message=f"Reinventing the wheel: direct access to '{s_val}' detected in '{rel_p}:{lineno}'. Use 'core.config.get()' / 'core.config.set()' SDK instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )
                            elif s_val == "contributes.merged.json":
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.FAIL,
                                        category="ANTIPATTERN",
                                        message=f"Direct contributes probing: access to '{s_val}' detected in '{rel_p}:{lineno}'. Use 'core.contributes.get()' SDK instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )


    def _check_test_classes(self, name: str, real_dir: str, report: CheckReport) -> None:
        tests_dir = os.path.join(real_dir, "tests")
        if not os.path.isdir(tests_dir):
            return

        def _extract_tokens(expr_node: ast.AST) -> List[str]:
            tokens = []
            for n in ast.walk(expr_node):
                if isinstance(n, ast.Attribute):
                    tokens.append(n.attr)
                elif isinstance(n, ast.Name):
                    tokens.append(n.id)
            return tokens

        def _check_require_node(target_node: ast.AST, t_file: str) -> None:
            for dec in getattr(target_node, "decorator_list", []):
                if isinstance(dec, ast.Call):
                    func_name = ""
                    if isinstance(dec.func, ast.Name):
                        func_name = dec.func.id
                    elif isinstance(dec.func, ast.Attribute):
                        func_name = dec.func.attr
                    
                    if func_name == "require" and dec.args:
                        tokens = _extract_tokens(dec.args[0])
                        if "LOGIC" in tokens and ("ISOLATED_SANDBOX" in tokens or "ISOLATE_SANDBOX" in tokens):
                            node_kind = "class" if isinstance(target_node, ast.ClassDef) else "function"
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.WARN,
                                    category="ANTIPATTERN",
                                    message=(
                                        f"Anti-Pattern: Test {node_kind} '{getattr(target_node, 'name', '')}' in tests/{t_file}:{target_node.lineno} "
                                        f"is marked with both 'LOGIC' and 'ISOLATED_SANDBOX'. Pure logical tests should not request dedicated per-method sandbox isolation."
                                    ),
                                    file_path=f"tests/{t_file}",
                                    line_number=target_node.lineno,
                                )
                            )

        for t_file in os.listdir(tests_dir):
            if t_file.startswith("test_") and t_file.endswith(".py"):
                t_full = os.path.join(tests_dir, t_file)
                try:
                    with open(t_full, "r", encoding="utf-8") as tf:
                        tree = ast.parse(tf.read(), filename=t_file)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            if node.name.startswith("Test"):
                                base_names = []
                                for b in node.bases:
                                    if isinstance(b, ast.Name):
                                        base_names.append(b.id)
                                    elif isinstance(b, ast.Attribute):
                                        base_names.append(b.attr)
                                if "TestCase" in base_names and "YSCBTestCase" not in base_names:
                                    report.issues.append(
                                        CheckIssue(
                                            severity=CheckSeverity.FAIL,
                                            category="STRUCTURE",
                                            message=f"Security Guard: Test class '{node.name}' in tests/{t_file}:{node.lineno} directly subclasses 'unittest.TestCase'. Must inherit from 'dev.testing.case.YSCBTestCase'.",
                                            file_path=f"tests/{t_file}",
                                            line_number=node.lineno,
                                        )
                                    )
                                else:
                                    # AST Static Inspection: Check self.mark_passed() in test_* methods
                                    for item in node.body:
                                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                                            is_none_req = False
                                            for dec in getattr(item, "decorator_list", []):
                                                if isinstance(dec, ast.Call):
                                                    f_name = getattr(dec.func, "id", getattr(dec.func, "attr", ""))
                                                    if f_name == "require" and dec.args:
                                                        if "NONE" in _extract_tokens(dec.args[0]):
                                                            is_none_req = True
                                                            break
                                            if not is_none_req:
                                                has_mark = False
                                                for sub_n in ast.walk(item):
                                                    if isinstance(sub_n, ast.Call):
                                                        cf = sub_n.func
                                                        if isinstance(cf, ast.Attribute) and cf.attr == "mark_passed":
                                                            if isinstance(cf.value, ast.Name) and cf.value.id == "self":
                                                                has_mark = True
                                                                break
                                                if not has_mark:
                                                    report.issues.append(
                                                        CheckIssue(
                                                            severity=CheckSeverity.WARN,
                                                            category="STRUCTURE",
                                                            message=f"Test method '{item.name}' in tests/{t_file}:{item.lineno} lacks 'self.mark_passed()' call. Unhandled tests will be marked as UNKNOWN in test runner.",
                                                            file_path=f"tests/{t_file}",
                                                            line_number=item.lineno,
                                                        )
                                                    )
                            _check_require_node(node, t_file)
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            _check_require_node(node, t_file)
                except Exception as e:
                    report.issues.append(
                        CheckIssue(
                            severity=CheckSeverity.FAIL,
                            category="SYNTAX",
                            message=f"Error parsing test file tests/{t_file}: {e}",
                            file_path=f"tests/{t_file}",
                        )
                    )

    def _check_sandbox_hooks(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        Verify compliance of 'scripts/hook.dev.py' lifecycle hook script.
        Enforces:
        1. Syntax validity via AST parsing.
        2. Forbidden top-level executable statements (only imports, defs, classes, or docstrings allowed).
        3. Mandatory function signatures for on_test_setup / on_test_teardown (must accept context argument).
        """
        hook_path = os.path.join(real_dir, "scripts", "hook.dev.py")
        if not os.path.exists(hook_path):
            return

        rel_p = "scripts/hook.dev.py"
        try:
            with open(hook_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=hook_path)
        except SyntaxError as se:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="SYNTAX",
                    message=f"SyntaxError in {rel_p}:{se.lineno}: {se.msg}",
                    file_path=rel_p,
                    line_number=se.lineno,
                )
            )
            return
        except Exception as e:
            report.issues.append(
                CheckIssue(
                    severity=CheckSeverity.FAIL,
                    category="SYNTAX",
                    message=f"Error parsing {rel_p}: {e}",
                    file_path=rel_p,
                )
            )
            return

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in ("on_test_setup", "on_test_teardown"):
                        total_args = len(node.args.args) + (1 if node.args.vararg else 0)
                        if total_args < 1:
                            report.issues.append(
                                CheckIssue(
                                    severity=CheckSeverity.FAIL,
                                    category="STRUCTURE",
                                    message=f"Hook function '{node.name}' in {rel_p}:{node.lineno} must accept at least 1 parameter ('context').",
                                    file_path=rel_p,
                                    line_number=node.lineno,
                                )
                            )
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            elif isinstance(node, ast.Assign):
                continue
            else:
                stmt_type = type(node).__name__
                lineno = getattr(node, "lineno", 0)
                report.issues.append(
                    CheckIssue(
                        severity=CheckSeverity.FAIL,
                        category="ANTIPATTERN",
                        message=f"Forbidden top-level statement '{stmt_type}' in {rel_p}:{lineno}. Hook scripts must only declare imports, functions, or classes.",
                        file_path=rel_p,
                        line_number=lineno,
                    )
                )

    def _check_docs_pollution(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        Scan module's 'docs/' folder to detect hardcoded local development paths.
        Enforces documentation perspective boundaries:
        Third-party guides must use semantic URIs (e.g. 'module://<mod>/') instead of 'project://source/'.
        """
        docs_dir = os.path.join(real_dir, "docs")
        if not os.path.isdir(docs_dir):
            return

        for root, _, files in os.walk(docs_dir):
            for f in files:
                if not f.endswith(".md"):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as df:
                        for lineno, line in enumerate(df, start=1):
                            if "project://source/" in line:
                                report.issues.append(
                                    CheckIssue(
                                        severity=CheckSeverity.WARN,
                                        category="DOCUMENTATION",
                                        message=f"Documentation path pollution: Hardcoded 'project://source/' detected in '{rel_p}:{lineno}'. Downstream developers have no source/ directory; use 'module://<mod>/' semantic URI instead.",
                                        file_path=rel_p,
                                        line_number=lineno,
                                    )
                                )
                except Exception:
                    pass


    def check_all(self) -> Dict[str, CheckReport]:
        results = {}
        src_root_uri = "module.source://"
        if not uri.exists(src_root_uri):
            return results

        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.check_module(item)

        return results
