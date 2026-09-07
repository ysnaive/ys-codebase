"""
Contributes Schema Validator and Lightweight DSL Engine.
100% Python Standard Library, Zero Third-Party Dependencies.
"""
from typing import Dict, Any, List, Optional, Tuple, NamedTuple, Set
import difflib
import copy
import re


class ValidationIssue(NamedTuple):
    path: str
    message: str
    severity: str = "ERROR"  # "ERROR" | "WARNING"
    suggestion: Optional[str] = None

    def __str__(self) -> str:
        s = f"[{self.severity}] {self.path}: {self.message}"
        if self.suggestion:
            s += f" ({self.suggestion})"
        return s


class ValidationResult:
    def __init__(self, is_valid: bool, issues: List[ValidationIssue], payload: Optional[Dict[str, Any]] = None):
        self.is_valid: bool = is_valid
        self.issues: List[ValidationIssue] = issues
        self.payload: Optional[Dict[str, Any]] = payload

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    def format_report(self, file_label: str = "") -> str:
        lines = []
        header = f"Contributes Validation Report: {file_label}" if file_label else "Contributes Validation Report"
        lines.append(f"=== {header} ===")
        if self.is_valid and not self.warnings:
            lines.append("✅ All definitions are valid.")
            return "\n".join(lines)
        for issue in self.issues:
            icon = "❌" if issue.severity == "ERROR" else "⚠️"
            line = f"{icon} [{issue.path}] {issue.message}"
            if issue.suggestion:
                line += f"\n   💡 {issue.suggestion}"
            lines.append(line)
        return "\n".join(lines)


class ContributesValidator:
    """
    Lightweight Type Signature DSL Parser & Rigid Validator for YSCB Contributes.
    """
    MAX_RECURSION_DEPTH = 20

    # Type alias normalization map
    TYPE_ALIASES = {
        "string": "str",
        "boolean": "bool",
        "integer": "int",
        "number": "float",
    }

    @classmethod
    def parse_type_signature(cls, sig: str) -> Dict[str, Any]:
        """
        Parse type signature string:
        - "str!" -> type: "str", required: True
        - "str?" or "str" -> type: "str", required: False
        - "enum(a, b, c)!" -> type: "enum", enum_values: ["a", "b", "c"], required: True
        - "bool? = false" -> type: "bool", required: False, default: False
        - "$TypeName" -> type: "ref", ref_name: "TypeName", required: False
        - "$TypeName!" -> type: "ref", ref_name: "TypeName", required: True
        - "list[str]" -> type: "list", item_type: "str"
        - "dict[str, str]" -> type: "dict", key_type: "str", value_type: "str"
        """
        raw = sig.strip()
        required = False
        default_val: Any = None
        has_default = False

        # Extract default value: "= <default>"
        if " = " in raw or "=" in raw:
            parts = raw.split("=", 1)
            raw = parts[0].strip()
            def_str = parts[1].strip()
            has_default = True
            # Parse def_str
            if def_str.lower() in ("true", "false"):
                default_val = def_str.lower() == "true"
            elif def_str.isdigit():
                default_val = int(def_str)
            elif def_str.startswith('"') and def_str.endswith('"'):
                default_val = def_str[1:-1]
            elif def_str.startswith("'") and def_str.endswith("'"):
                default_val = def_str[1:-1]
            elif def_str == "[]":
                default_val = []
            elif def_str == "{}":
                default_val = {}
            else:
                default_val = def_str

        # Check required/optional modifier
        if raw.endswith("!"):
            required = True
            raw = raw[:-1].strip()
        elif raw.endswith("?"):
            required = False
            raw = raw[:-1].strip()

        # Type Reference: $TypeName
        if raw.startswith("$"):
            ref_name = raw[1:].strip()
            return {
                "type": "ref",
                "ref_name": ref_name,
                "required": required,
                "has_default": has_default,
                "default": default_val,
                "raw": sig
            }

        # Enum: enum(a, b, c)
        if raw.startswith("enum(") and raw.endswith(")"):
            inner = raw[5:-1]
            enum_vals = [v.strip() for v in inner.split(",") if v.strip()]
            return {
                "type": "enum",
                "enum_values": enum_vals,
                "required": required,
                "has_default": has_default,
                "default": default_val,
                "raw": sig
            }

        # Container: list[T]
        list_match = re.match(r"^list\[(.*)\]$", raw)
        if list_match:
            item_sig = list_match.group(1).strip()
            return {
                "type": "list",
                "item_type": cls.parse_type_signature(item_sig),
                "required": required,
                "has_default": has_default,
                "default": default_val if has_default else [],
                "raw": sig
            }

        # Container: dict[K, V]
        dict_match = re.match(r"^dict\[(.*),(.*)\]$", raw)
        if dict_match:
            k_sig = dict_match.group(1).strip()
            v_sig = dict_match.group(2).strip()
            return {
                "type": "dict",
                "key_type": cls.parse_type_signature(k_sig),
                "value_type": cls.parse_type_signature(v_sig),
                "required": required,
                "has_default": has_default,
                "default": default_val if has_default else {},
                "raw": sig
            }

        # Normalize primitive type
        norm_type = cls.TYPE_ALIASES.get(raw.lower(), raw.lower())
        return {
            "type": norm_type,
            "required": required,
            "has_default": has_default,
            "default": default_val,
            "raw": sig
        }

    @classmethod
    def validate_node(
        cls,
        data: Any,
        schema: Any,
        path: str,
        types_map: Dict[str, Any],
        depth: int = 0
    ) -> Tuple[Any, List[ValidationIssue]]:
        issues: List[ValidationIssue] = []

        if depth > cls.MAX_RECURSION_DEPTH:
            issues.append(ValidationIssue(
                path=path,
                message=f"Maximum recursion depth ({cls.MAX_RECURSION_DEPTH}) exceeded.",
                severity="ERROR"
            ))
            return data, issues

        # 1. String signature
        if isinstance(schema, str):
            rule = cls.parse_type_signature(schema)
            # If ref
            if rule["type"] == "ref":
                ref_name = rule["ref_name"]
                if ref_name not in types_map:
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Undefined type reference '${ref_name}'.",
                        severity="ERROR"
                    ))
                    return data, issues
                target_schema = types_map[ref_name]
                return cls.validate_node(data, target_schema, path, types_map, depth + 1)

            expected_type = rule["type"]

            if expected_type == "any":
                return data, issues

            if expected_type == "str":
                if not isinstance(data, str):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected string, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                return data, issues

            elif expected_type == "int":
                if not isinstance(data, int) or isinstance(data, bool):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected integer, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                return data, issues

            elif expected_type == "bool":
                if not isinstance(data, bool):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected boolean, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                return data, issues

            elif expected_type == "float":
                if not isinstance(data, (float, int)) or isinstance(data, bool):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected float, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                return data, issues

            elif expected_type == "enum":
                allowed = rule["enum_values"]
                if not isinstance(data, str) or data not in allowed:
                    matches = difflib.get_close_matches(str(data), allowed, n=1)
                    hint = f"Did you mean '{matches[0]}'?" if matches else f"Expected one of {allowed}"
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Invalid value '{data}'.",
                        severity="ERROR",
                        suggestion=hint
                    ))
                return data, issues

            elif expected_type == "list":
                if not isinstance(data, list):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected list, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                    return data, issues
                out_list = []
                for idx, item in enumerate(data):
                    item_path = f"{path}[{idx}]"
                    out_item, sub_issues = cls.validate_node(item, rule["item_type"]["raw"], item_path, types_map, depth + 1)
                    issues.extend(sub_issues)
                    out_list.append(out_item)
                return out_list, issues

            elif expected_type == "dict":
                if not isinstance(data, dict):
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Expected dict, got {type(data).__name__}.",
                        severity="ERROR"
                    ))
                    return data, issues
                out_dict = {}
                for k, v in data.items():
                    k_path = f"{path}.{k}"
                    out_v, sub_issues = cls.validate_node(v, rule["value_type"]["raw"], k_path, types_map, depth + 1)
                    issues.extend(sub_issues)
                    out_dict[k] = out_v
                return out_dict, issues

            else:
                issues.append(ValidationIssue(
                    path=path,
                    message=f"Unknown primitive type '{expected_type}'.",
                    severity="ERROR"
                ))
                return data, issues

        # 2. List schema: [ item_schema ]
        elif isinstance(schema, list):
            if not isinstance(data, list):
                issues.append(ValidationIssue(
                    path=path,
                    message=f"Expected list, got {type(data).__name__}.",
                    severity="ERROR"
                ))
                return data, issues
            if not schema:
                return data, issues
            item_schema = schema[0]
            out_list = []
            for idx, item in enumerate(data):
                item_path = f"{path}[{idx}]"
                out_item, sub_issues = cls.validate_node(item, item_schema, item_path, types_map, depth + 1)
                issues.extend(sub_issues)
                out_list.append(out_item)
            return out_list, issues

        # 3. Dict schema
        elif isinstance(schema, dict):
            if not isinstance(data, dict):
                issues.append(ValidationIssue(
                    path=path,
                    message=f"Expected object/dict, got {type(data).__name__}.",
                    severity="ERROR"
                ))
                return data, issues

            # Check if this dict schema is a reference
            if "$ref" in schema:
                ref_name = schema["$ref"].lstrip("$")
                if ref_name not in types_map:
                    issues.append(ValidationIssue(
                        path=path,
                        message=f"Undefined type reference '${ref_name}'.",
                        severity="ERROR"
                    ))
                    return data, issues
                return cls.validate_node(data, types_map[ref_name], path, types_map, depth + 1)

            out_dict = copy.copy(data)
            has_wildcard = "*" in schema
            wildcard_schema = schema.get("*")
            defined_keys = set(k for k in schema.keys() if k != "*")

            # Validate existing keys in data
            for k, v in data.items():
                k_path = f"{path}.{k}" if path else k
                if k in defined_keys:
                    k_schema = schema[k]
                    out_val, sub_issues = cls.validate_node(v, k_schema, k_path, types_map, depth + 1)
                    issues.extend(sub_issues)
                    out_dict[k] = out_val
                elif has_wildcard:
                    out_val, sub_issues = cls.validate_node(v, wildcard_schema, k_path, types_map, depth + 1)
                    issues.extend(sub_issues)
                    out_dict[k] = out_val
                else:
                    # Unknown field
                    all_allowed = sorted(list(defined_keys))
                    matches = difflib.get_close_matches(k, all_allowed, n=1)
                    hint = f"Did you mean '{matches[0]}'?" if matches else f"Allowed fields: {all_allowed}"
                    issues.append(ValidationIssue(
                        path=k_path,
                        message=f"Unknown field '{k}'.",
                        severity="ERROR",
                        suggestion=hint
                    ))

            # Check required keys in defined_keys & fill defaults
            for k in defined_keys:
                k_schema = schema[k]
                k_path = f"{path}.{k}" if path else k
                if k not in data:
                    # Check if required or has default
                    if isinstance(k_schema, str):
                        rule = cls.parse_type_signature(k_schema)
                        if rule["required"]:
                            issues.append(ValidationIssue(
                                path=k_path,
                                message=f"Missing required field '{k}'.",
                                severity="ERROR"
                            ))
                        elif rule["has_default"]:
                            out_dict[k] = rule["default"]
                    elif isinstance(k_schema, dict) and k_schema.get("required") is True:
                        issues.append(ValidationIssue(
                            path=k_path,
                            message=f"Missing required field '{k}'.",
                            severity="ERROR"
                        ))

            return out_dict, issues

        return data, issues

    @classmethod
    def validate(
        cls,
        target_mod: str,
        payload: Dict[str, Any],
        donor_mod: str = "",
        format_schema: Optional[Dict[str, Any]] = None,
        strict_points: bool = True
    ) -> ValidationResult:
        """
        Validate donor's contributes payload against target_mod's format_schema.
        """
        issues: List[ValidationIssue] = []

        if not isinstance(payload, dict):
            return ValidationResult(
                is_valid=False,
                issues=[ValidationIssue(path="", message=f"Payload must be a dictionary, got {type(payload).__name__}.", severity="ERROR")]
            )

        if format_schema is None:
            # Tolerant mode if no schema exists
            return ValidationResult(is_valid=True, issues=[], payload=payload)

        types_map = format_schema.get("_types", {})
        known_points = [k for k in format_schema.keys() if not k.startswith("_")]

        validated_payload = {}

        # 1. Strict boundary check on top-level keys
        for key, val in payload.items():
            if key.startswith("_"):
                continue  # Ignore internal metadata like __provider__

            if key not in known_points:
                if strict_points:
                    matches = difflib.get_close_matches(key, known_points, n=1)
                    hint = f"Did you mean '{matches[0]}'?" if matches else f"Target '{target_mod}' only accepts: {known_points}"
                    issues.append(ValidationIssue(
                        path=key,
                        message=f"Key '{key}' is not an accepted contribute point for module '{target_mod}'.",
                        severity="ERROR",
                        suggestion=hint
                    ))
                validated_payload[key] = val
                continue

            point_def = format_schema[key]
            point_format = point_def.get("format") if isinstance(point_def, dict) else point_def
            if point_format is None:
                validated_payload[key] = val
                continue

            node_out, node_issues = cls.validate_node(val, point_format, key, types_map, depth=0)
            issues.extend(node_issues)
            validated_payload[key] = node_out

        is_valid = len([i for i in issues if i.severity == "ERROR"]) == 0
        return ValidationResult(is_valid=is_valid, issues=issues, payload=validated_payload)

    @classmethod
    def validate_format_schema(cls, format_schema: Dict[str, Any]) -> ValidationResult:
        """
        Meta-Check: Validate _format.json structure itself.
        """
        issues: List[ValidationIssue] = []
        if not isinstance(format_schema, dict):
            return ValidationResult(
                is_valid=False,
                issues=[ValidationIssue(path="", message="Format schema must be a dictionary.", severity="ERROR")]
            )

        types_map = format_schema.get("_types", {})
        if not isinstance(types_map, dict):
            issues.append(ValidationIssue(path="_types", message="_types must be a dictionary.", severity="ERROR"))

        points = [k for k in format_schema.keys() if not k.startswith("_")]
        if not points:
            issues.append(ValidationIssue(path="", message="No contribution points defined in format schema.", severity="WARNING"))

        for pt in points:
            p_def = format_schema[pt]
            if not isinstance(p_def, dict):
                issues.append(ValidationIssue(path=pt, message=f"Contribute point definition must be an object with 'description' and 'format'.", severity="ERROR"))
                continue
            if "description" not in p_def or not isinstance(p_def["description"], str):
                issues.append(ValidationIssue(path=f"{pt}.description", message="Missing or non-string 'description'.", severity="ERROR"))
            if "format" not in p_def:
                issues.append(ValidationIssue(path=f"{pt}.format", message="Missing 'format' specification.", severity="ERROR"))

        is_valid = len([i for i in issues if i.severity == "ERROR"]) == 0
        return ValidationResult(is_valid=is_valid, issues=issues)
