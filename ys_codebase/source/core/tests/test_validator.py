"""
Unit tests for ContributesValidator and Schema DSL Engine.
Covers FT-01 ~ FT-05.
"""
from dev.testing import YSCBTestCase, require, Requirement
from core.validator import ContributesValidator, ValidationResult, ValidationIssue


class TestContributesValidator(YSCBTestCase):
    @require(Requirement.ENV)
    def test_validator_types(self):
        """FT-01: 型別表達式解析與基礎型別校驗"""
        p_str = ContributesValidator.parse_type_signature("str!")
        self.assertEqual(p_str["type"], "str")
        self.assertTrue(p_str["required"])

        p_enum = ContributesValidator.parse_type_signature("enum(safe, conditional, gated)? = conditional")
        self.assertEqual(p_enum["type"], "enum")
        self.assertFalse(p_enum["required"])
        self.assertEqual(p_enum["default"], "conditional")
        self.assertEqual(p_enum["enum_values"], ["safe", "conditional", "gated"])

        p_bool = ContributesValidator.parse_type_signature("bool? = false")
        self.assertEqual(p_bool["type"], "bool")
        self.assertFalse(p_bool["required"])
        self.assertFalse(p_bool["default"])

        p_alias = ContributesValidator.parse_type_signature("boolean!")
        self.assertEqual(p_alias["type"], "bool")
        self.assertTrue(p_alias["required"])
        self.mark_passed()

    @require(Requirement.ENV)
    def test_validator_containers(self):
        """FT-02: 物件陣列清單與通配符 * 字典映射"""
        schema = {
            "uri_schemes": {
                "description": "URI schemes",
                "format": [
                    {
                        "token": "str!",
                        "type": "enum(config, const, module)!",
                        "value": "str!",
                        "description": "str?"
                    }
                ]
            }
        }
        # Valid data
        data = {
            "uri_schemes": [
                {"token": "test.uri", "type": "const", "value": "cache://test/"}
            ]
        }
        res = ContributesValidator.validate("core", data, format_schema=schema)
        self.assertTrue(res.is_valid, f"Validation failed: {res.errors}")

        # Invalid type enum
        bad_data = {
            "uri_schemes": [
                {"token": "test.uri", "type": "invalid_type", "value": "cache://test/"}
            ]
        }
        bad_res = ContributesValidator.validate("core", bad_data, format_schema=schema)
        self.assertFalse(bad_res.is_valid)
        self.assertTrue(any("Invalid value 'invalid_type'" in e.message for e in bad_res.errors))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_validator_recursive(self):
        """FT-03: 遞迴結構 ($CommandNode) 與 _types 別名參照"""
        schema = {
            "_types": {
                "CommandNode": {
                    "description": "str!",
                    "tier": "enum(safe, conditional)? = safe",
                    "cmd": {
                        "*": "$CommandNode"
                    }
                }
            },
            "commands": {
                "description": "commands tree",
                "format": {
                    "cmd": {
                        "*": "$CommandNode"
                    }
                }
            }
        }
        # Multi-level recursive commands: uri -> resolve
        tree_data = {
            "commands": {
                "cmd": {
                    "uri": {
                        "description": "URI management",
                        "tier": "safe",
                        "cmd": {
                            "resolve": {
                                "description": "Resolve URI to path",
                                "tier": "safe"
                            }
                        }
                    }
                }
            }
        }
        res = ContributesValidator.validate("core", tree_data, format_schema=schema)
        self.assertTrue(res.is_valid, f"Validation errors: {res.errors}")
        self.mark_passed()

    @require(Requirement.ENV)
    def test_validator_did_you_mean(self):
        """FT-04: 未知欄位 Levenshtein 近似拼寫診斷 (Did you mean)"""
        schema = {
            "commands": {
                "description": "commands",
                "format": {
                    "cmd": {
                        "*": {
                            "description": "str!",
                            "case_pros": "list[str]?",
                            "case_cons": "list[str]?"
                        }
                    }
                }
            }
        }
        # typo: 'cas_pros' instead of 'case_pros'
        typo_data = {
            "commands": {
                "cmd": {
                    "test": {
                        "description": "run test",
                        "cas_pros": ["fast run"]
                    }
                }
            }
        }
        res = ContributesValidator.validate("core", typo_data, format_schema=schema)
        self.assertFalse(res.is_valid)
        error = [e for e in res.errors if "cas_pros" in e.path or "cas_pros" in e.message][0]
        self.assertIsNotNone(error.suggestion)
        self.assertIn("case_pros", error.suggestion)
        self.mark_passed()

    @require(Requirement.ENV)
    def test_validator_cross_target(self):
        """FT-05: 跨目標越權注入阻斷"""
        schema = {
            "commands": {
                "description": "commands",
                "format": {}
            }
        }
        # inject 'export' to 'core' (which is only accepted by agents-workflow)
        bad_target_data = {
            "commands": {},
            "export": [{"type": "standard", "source": "..."}]
        }
        res = ContributesValidator.validate("core", bad_target_data, format_schema=schema, strict_points=True)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("not an accepted contribute point" in e.message for e in res.errors))
        self.mark_passed()

    @require(Requirement.ENV)
    def test_validator_format_meta_check(self):
        """Meta-Check: 校驗 _format.json 本身結構"""
        valid_meta = {
            "_types": {
                "Foo": {"name": "str!"}
            },
            "my_point": {
                "description": "test point",
                "format": "$Foo"
            }
        }
        res = ContributesValidator.validate_format_schema(valid_meta)
        self.assertTrue(res.is_valid)

        # Missing description
        invalid_meta = {
            "my_point": {
                "format": "str!"
            }
        }
        res_inv = ContributesValidator.validate_format_schema(invalid_meta)
        self.assertFalse(res_inv.is_valid)
        self.mark_passed()
