"""
Unit and Edge Case Tests for knowledge-db SpiceParser.
"""

import os
from pathlib import Path
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.parsers import ParserRegistry, SpiceParser
from knowledge_db.schema import LanguageType, SymbolKind, UnifiedSymbol


class TestSpiceParser(YSCBTestCase):
    """SPICE 網表解析器 (SpiceParser) 完整功能與邊界測試套件。"""

    def setUp(self):
        super().setUp()
        self.parser = SpiceParser()

    # =========================================================================
    # FT: 功能需求測試 (Functional Tests)
    # =========================================================================

    @require(Requirement.LOGIC)
    def test_ft_01_can_parse_extensions(self):
        """FT-01: 驗證 can_parse 支援 .cir, .sp, .spice, .net, .cdl 及其大小寫變形 (FR-01)"""
        valid_files = [
            "circuit.cir",
            "netlist.sp",
            "models.SPICE",
            "top.Net",
            "layout.CDL",
            "path/to/subckt.cir",
        ]
        for f in valid_files:
            self.assertTrue(self.parser.can_parse(f), f"Expected True for {f}")

        invalid_files = [
            "code.py",
            "doc.md",
            "header.h",
            "data.json",
            "circuit.v",
            "",
        ]
        for f in invalid_files:
            self.assertFalse(self.parser.can_parse(f), f"Expected False for {f}")

    @require(Requirement.LOGIC)
    def test_ft_02_line_continuation_and_docstring(self):
        """FT-02: 驗證 Stage 1 行聚合器正確合併 '+' 接續行並提取 Docstring (FR-02)"""
        content = """* Standard CMOS Inverter
* High speed version with parameterized widths
.SUBCKT INV_X1 IN OUT VDD VSS
+ PARAMS: WP=2u
+ WN=1u L=0.18u
M1 OUT IN VDD VDD PMOS W={WP} L={L}
M2 OUT IN VSS VSS NMOS W={WN} L={L}
.ENDS INV_X1
"""
        symbols = self.parser.parse("inverter.cir", content, "spice_space")
        self.assertEqual(len(symbols), 1)
        inv = symbols[0]

        self.assertEqual(inv.name, "INV_X1")
        self.assertEqual(inv.kind, SymbolKind.CLASS.value)
        self.assertEqual(inv.language, LanguageType.SPICE.value)
        self.assertEqual(inv.line_number, 3)
        self.assertEqual(inv.end_line, 8)
        self.assertIn("Standard CMOS Inverter", inv.docstring)
        self.assertIn("High speed version", inv.docstring)
        self.assertIn("PARAMS: WP=2u WN=1u L=0.18u", inv.signature)

    @require(Requirement.LOGIC)
    def test_ft_03_dot_commands_extraction(self):
        """FT-03: 驗證 .subckt, .model, .param, .include, .lib, .global 點指令符號提取 (FR-03)"""
        content = """* Global Models and Directives
.INCLUDE "tsmc18.lib"
.LIB "corners.lib" TT
.GLOBAL VDD VSS CLK
.PARAM VDD_VAL=1.8V VSS_VAL=0V TEMP_NOM=27

* NMOS Standard Model
.MODEL NMOS_18 NMOS (LEVEL=1 VTO=0.7 KP=1e-4)

* PMOS Standard Model
.MODEL PMOS_18 PMOS (LEVEL=1 VTO=-0.7 KP=4e-5)
"""
        symbols = self.parser.parse("top.sp", content, "top_space")

        # 符號名稱集合
        names = {s.name for s in symbols}
        self.assertIn("tsmc18.lib", names)
        self.assertIn("corners.lib", names)
        self.assertIn("VDD", names)
        self.assertIn("VSS", names)
        self.assertIn("CLK", names)
        self.assertIn("VDD_VAL", names)
        self.assertIn("VSS_VAL", names)
        self.assertIn("TEMP_NOM", names)
        self.assertIn("NMOS_18", names)
        self.assertIn("PMOS_18", names)

        # 檢核 Model kind
        nmos = next(s for s in symbols if s.name == "NMOS_18")
        self.assertEqual(nmos.kind, SymbolKind.STRUCT.value)
        self.assertEqual(nmos.language, LanguageType.SPICE.value)
        self.assertIn("NMOS Standard Model", nmos.docstring)

        # 檢核 Param kind
        param_vdd = next(s for s in symbols if s.name == "VDD_VAL")
        self.assertEqual(param_vdd.kind, SymbolKind.VARIABLE.value)

    @require(Requirement.LOGIC)
    def test_ft_04_subckt_members_and_instances(self):
        """FT-04: 驗證子電路內部 members 與頂層 X 實例提取 (FR-04)"""
        content = """* NAND2 Gate Definition
.SUBCKT NAND2_X1 A B Y VDD VSS
.PARAM WP=2u WN=1u
.MODEL LOCAL_DIO D (IS=1e-14)
MP1 Y A VDD VDD PMOS W=WP L=0.18u
MP2 Y B VDD VDD PMOS W=WP L=0.18u
MN1 Y A MID VSS NMOS W=WN L=0.18u
MN2 MID B VSS VSS NMOS W=WN L=0.18u
X_DECAP VDD VSS CAP_DECAP
.ENDS NAND2_X1

* Top level circuit instantiations
X_GATE_1 IN1 IN2 OUT VDD VSS NAND2_X1
X_GATE_2 OUT IN3 FINAL VDD VSS NAND2_X1
V_VDD VDD 0 DC 1.8V
"""
        symbols = self.parser.parse("nand_tree.cir", content, "nand_space")

        # 頂層應包含: NAND2_X1 (subckt), X_GATE_1 (instance), X_GATE_2 (instance), V_VDD (voltage source)
        top_names = {s.name for s in symbols}
        self.assertIn("NAND2_X1", top_names)
        self.assertIn("X_GATE_1", top_names)
        self.assertIn("X_GATE_2", top_names)
        self.assertIn("V_VDD", top_names)

        # 檢驗 NAND2_X1 的內部 members
        nand_sym = next(s for s in symbols if s.name == "NAND2_X1")
        member_names = {m.name for m in nand_sym.members}
        self.assertIn("WP", member_names)
        self.assertIn("LOCAL_DIO", member_names)
        self.assertIn("MP1", member_names)
        self.assertIn("MP2", member_names)
        self.assertIn("MN1", member_names)
        self.assertIn("MN2", member_names)
        self.assertIn("X_DECAP", member_names)

    @require(Requirement.LOGIC)
    def test_ft_05_registry_integration(self):
        """FT-05: 驗證 ParserRegistry 動態分發與 SPICE 符號解析整合 (FR-05)"""
        registry = ParserRegistry(register_defaults=True)
        p = registry.get_parser("circuit.cdl")
        self.assertIsInstance(p, SpiceParser)

        content = ".SUBCKT BUFFER_X2 IN OUT VDD VSS\n.ENDS BUFFER_X2\n"
        symbols = registry.parse_file("circuit.cdl", content, "proj_space")
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0].name, "BUFFER_X2")
        self.assertEqual(symbols[0].language, LanguageType.SPICE.value)

    # =========================================================================
    # ET: 邊界與異常防禦測試 (Edge Case Tests)
    # =========================================================================

    @require(Requirement.LOGIC)
    def test_et_01_continuation_with_comments_and_blank_lines(self):
        """ET-01: 驗證跨多行 '+' 接續夾雜空行與行尾註解之穩定合併 (EC-01)"""
        content = """* Multi-line parameterized amplifier
.SUBCKT OPAMP_DIFF INP INN OUT
+ VDD ; Power positive
+ VSS $ Power negative
+ PARAMS: GAIN='100k'
+ GBW='10MEG' ; 10MHz GBW
M1 OUT INP VDD VDD PMOS
.ENDS OPAMP_DIFF
"""
        symbols = self.parser.parse("opamp.cir", content, "diff_space")
        self.assertEqual(len(symbols), 1)
        opamp = symbols[0]
        self.assertEqual(opamp.name, "OPAMP_DIFF")
        self.assertEqual(opamp.line_number, 2)
        self.assertEqual(opamp.end_line, 8)
        self.assertIn("PARAMS: GAIN='100k' GBW='10MEG'", opamp.signature)
        self.assertNotIn("Power positive", opamp.signature)
        self.assertNotIn("Power negative", opamp.signature)

    @require(Requirement.LOGIC)
    def test_et_02_unclosed_subcircuit_fallback(self):
        """ET-02: 驗證未閉合 .subckt 網表自動防禦封裝至檔案末端 (EC-02)"""
        content = """* Incomplete Subcircuit (Truncated)
.SUBCKT BROKEN_SUBCKT A B Y
M1 Y A VDD VDD PMOS
M2 Y B VSS VSS NMOS
"""
        symbols = self.parser.parse("broken.cir", content, "broken_space")
        self.assertEqual(len(symbols), 1)
        broken = symbols[0]
        self.assertEqual(broken.name, "BROKEN_SUBCKT")
        self.assertEqual(broken.line_number, 2)
        self.assertEqual(broken.end_line, 4)
        self.assertTrue(broken.metadata.get("unclosed"))
        self.assertEqual(len(broken.members), 2)

    @require(Requirement.LOGIC)
    def test_et_03_mixed_dialect_comments_and_case(self):
        """ET-03: 驗證混合方言註解 (*, ;, $) 與大小寫混雜關鍵字之正規化 (EC-03)"""
        content = """* Mixed Dialect Netlist
.subckt MixedGate_X1 in out vdd vss ; ngspice style
.Param R_VAL = 10k $ HSPICE comment
.model Diode_Mod D (Is=1e-15)
R1 in mid {R_VAL} ; inline comment
X_inner mid out Inverter_Core $ HSPICE comment
.Ends MixedGate_X1
"""
        symbols = self.parser.parse("mixed.sp", content, "mixed_space")
        self.assertEqual(len(symbols), 1)
        mg = symbols[0]
        self.assertEqual(mg.name, "MixedGate_X1")
        self.assertEqual(mg.kind, SymbolKind.CLASS.value)

        member_names = {m.name for m in mg.members}
        self.assertIn("R_VAL", member_names)
        self.assertIn("Diode_Mod", member_names)
        self.assertIn("R1", member_names)
        self.assertIn("X_inner", member_names)

    @require(Requirement.LOGIC)
    def test_et_04_empty_and_comment_only_files(self):
        """ET-04: 驗證空檔案、首行標題或純註解網表回傳空清單 [] (EC-04)"""
        self.assertEqual(self.parser.parse("empty.cir", "", "empty_space"), [])
        self.assertEqual(self.parser.parse("blank.cir", "   \n\t\n  ", "blank_space"), [])

        comment_only = """* Title: Inverter Testbench
* Author: Circuit Designer
* Date: 2026-08-29
* Description: Only comment lines in this file.
"""
        self.assertEqual(self.parser.parse("comments.cir", comment_only, "comment_space"), [])
