"""
ANSI 终端转义序列处理引擎 —— 测试用例 (修正版)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ansi_terminal import (
    VirtualTerminal, Cell, Rendition, ParseState,
    STYLE_BOLD, STYLE_DIM, STYLE_UNDERLINE, STYLE_REVERSE, STYLE_ITALIC,
    COLOR_DEFAULT, render_terminal_output, parse_and_snapshot,
)


ESC = "\x1b"


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        print(f"FAIL: {msg}")
        print(f"  expected: {repr(expected)}")
        print(f"  actual:   {repr(actual)}")
        return False
    return True


def test_basic_text():
    print("=== Test 1: 基本文本输出 ===")
    vt = VirtualTerminal(width=40, height=10)
    vt.feed("Hello, World!")
    ok = assert_eq(vt.get_line_text(0), "Hello, World!", "Line 0 text")
    ok &= assert_eq(vt.cursor_row, 0, "Cursor row")
    ok &= assert_eq(vt.cursor_col, 13, "Cursor col")
    print("PASS" if ok else "FAIL")
    return ok


def test_newline_and_cr():
    print("\n=== Test 2: 换行和回车 ===")
    vt = VirtualTerminal(width=40, height=10)
    vt.feed("Line1\nLine2\rOverwrite\n")
    ok = assert_eq(vt.get_line_text(0), "Line1", "Line 0")
    ok &= assert_eq(vt.get_line_text(1), "Overwrite", "Line 1 (\\r overwrite)")
    ok &= assert_eq(vt.cursor_row, 2, "Cursor after \\n")
    ok &= assert_eq(vt.cursor_col, 0, "Cursor col after \\n")
    print("PASS" if ok else "FAIL")
    return ok


def test_cursor_movement():
    print("\n=== Test 3: 光标移动 ===")
    vt = VirtualTerminal(width=20, height=10)
    vt.feed("ABCDE")
    vt.feed(f"{ESC}[3D")
    vt.feed("X")
    ok = assert_eq(vt.get_line_text(0), "ABXDE", "CUF 3 back then insert")

    vt2 = VirtualTerminal(width=20, height=10)
    vt2.feed("Line1\nLine2\nLine3\n")
    vt2.feed(f"{ESC}[2A")
    vt2.feed("X")
    ok &= assert_eq(vt2.get_line_text(1), "Xine2", "CUU 2 up")

    vt3 = VirtualTerminal(width=20, height=10)
    vt3.feed("Row1\n")
    vt3.feed(f"{ESC}[5;10H")
    vt3.feed("*")
    ok &= assert_eq(vt3.get_cell(4, 9).char, "*", "CUP row5 col10 (0-based r=4, c=9)")

    print("PASS" if ok else "FAIL")
    return ok


def test_cursor_boundary():
    print("\n=== Test 4: 光标越界处理 ===")
    vt = VirtualTerminal(width=10, height=5)
    vt.feed(f"{ESC}[100A")
    ok = assert_eq(vt.cursor_row, 0, "CUU 100 stopped at top")
    vt.feed(f"{ESC}[100B")
    ok &= assert_eq(vt.cursor_row, 4, "CUD 100 stopped at bottom")
    vt.feed(f"{ESC}[100C")
    ok &= assert_eq(vt.cursor_col, 9, "CUF 100 stopped at right")
    vt.feed(f"{ESC}[100D")
    ok &= assert_eq(vt.cursor_col, 0, "CUB 100 stopped at left")
    print("PASS" if ok else "FAIL")
    return ok


def test_sgr_colors_and_styles():
    print("\n=== Test 5: SGR 颜色和样式 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed(f"{ESC}[1;31;42mBoldRedOnGreen{ESC}[0m Normal")

    c = vt.get_cell(0, 0)
    ok = assert_eq(c.char, "B", "First char")
    ok &= assert_eq(c.fg, 1, "FG red (index 1)")
    ok &= assert_eq(c.bg, 2, "BG green (index 2)")
    ok &= assert_eq(c.style & STYLE_BOLD, STYLE_BOLD, "Bold style")

    c_normal = vt.get_cell(0, 14)
    ok &= assert_eq(c_normal.style, 0, "Reset style")
    ok &= assert_eq(c_normal.fg, COLOR_DEFAULT, "Reset FG")
    ok &= assert_eq(c_normal.bg, COLOR_DEFAULT, "Reset BG")

    vt2 = VirtualTerminal(width=40, height=5)
    vt2.feed(f"{ESC}[4mUnderline{ESC}[24mNoUnder")
    c_under = vt2.get_cell(0, 0)
    ok &= assert_eq(c_under.style & STYLE_UNDERLINE, STYLE_UNDERLINE, "Underline")
    c_nounder = vt2.get_cell(0, 9)
    ok &= assert_eq(c_nounder.style & STYLE_UNDERLINE, 0, "Underline removed")

    print("PASS" if ok else "FAIL")
    return ok


def test_sgr_256_colors():
    print("\n=== Test 6: SGR 256 色模式 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed(f"{ESC}[38;5;196mBrightRed{ESC}[0m")
    c = vt.get_cell(0, 0)
    ok = assert_eq(c.fg, 196, "256-color FG 196")
    ok &= assert_eq(c.fg_rgb is not None, True, "RGB non-None")
    if c.fg_rgb:
        ok &= assert_eq(c.fg_rgb[0] > 200, True, "Red channel high")

    vt.feed(f"{ESC}[48;5;46mBgGreen{ESC}[0m")
    c2 = vt.get_cell(0, 9)
    ok &= assert_eq(c2.bg, 46, "256-color BG 46")

    print("PASS" if ok else "FAIL")
    return ok


def test_sgr_rgb_truecolor():
    print("\n=== Test 7: SGR RGB 真彩色 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed(f"{ESC}[38;2;255;128;0mOrangeText{ESC}[0m")
    c = vt.get_cell(0, 0)
    ok = assert_eq(c.fg_rgb, (255, 128, 0), "RGB FG (255,128,0)")

    vt.feed(f"{ESC}[48;2;0;0;255mBlueBG{ESC}[0m")
    c2 = vt.get_cell(0, 10)
    ok &= assert_eq(c2.bg_rgb, (0, 0, 255), "RGB BG (0,0,255)")

    print("PASS" if ok else "FAIL")
    return ok


def test_sgr_style_accumulation():
    print("\n=== Test 8: SGR 样式累积 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed(f"{ESC}[1mBold{ESC}[4mBoldUnder{ESC}[22mUnderOnly{ESC}[0m")

    c1 = vt.get_cell(0, 0)
    ok = assert_eq(bool(c1.style & STYLE_BOLD), True, "Bold only")

    c2 = vt.get_cell(0, 4)
    ok &= assert_eq(bool(c2.style & STYLE_BOLD), True, "Bold+Under: bold")
    ok &= assert_eq(bool(c2.style & STYLE_UNDERLINE), True, "Bold+Under: under")

    c3 = vt.get_cell(0, 13)
    ok &= assert_eq(bool(c3.style & STYLE_BOLD), False, "UnderOnly: no bold")
    ok &= assert_eq(bool(c3.style & STYLE_UNDERLINE), True, "UnderOnly: under")

    print("PASS" if ok else "FAIL")
    return ok


def test_clear_operations():
    print("\n=== Test 9: 清屏清行操作 ===")
    vt = VirtualTerminal(width=20, height=5)
    vt.feed("ABCDEFGHIJKLMNOPQRST\n")
    vt.feed("ABCDEFGHIJKLMNOPQRST\n")
    vt.feed("ABCDEFGHIJKLMNOPQRST\n")
    vt.feed(f"{ESC}[2;5H")
    vt.feed(f"{ESC}[K")
    ok = assert_eq(vt.get_line_text(1), "ABCD", "EL from col 4 to end")

    vt2 = VirtualTerminal(width=20, height=5)
    vt2.feed("ABCDEFGHIJKLMNOPQRST\n")
    vt2.feed("ABCDEFGHIJKLMNOPQRST")
    vt2.feed(f"{ESC}[2;11H")
    vt2.feed(f"{ESC}[1K")
    ok &= assert_eq(vt2.get_line_text(1), "           LMNOPQRST", "EL 1: from start through cursor col 10 (cols 0-10 cleared)")

    vt3 = VirtualTerminal(width=20, height=8)
    vt3.feed("Row0\nRow1\nRow2\nRow3\nRow4")
    vt3.feed(f"{ESC}[3;1H")
    vt3.feed(f"{ESC}[0J")
    ok &= assert_eq(vt3.get_line_text(0), "Row0", "ED 0: row0 intact")
    ok &= assert_eq(vt3.get_line_text(1), "Row1", "ED 0: row1 intact")
    ok &= assert_eq(vt3.get_line_text(2).strip(), "", "ED 0: row2 cleared")

    print("PASS" if ok else "FAIL")
    return ok


def test_auto_wrap_and_scroll():
    print("\n=== Test 10: 自动换行与滚动 ===")
    vt = VirtualTerminal(width=10, height=5)
    vt.feed("0123456789ABCDEF")
    ok = assert_eq(vt.get_line_text(0), "0123456789", "Wrap line 0")
    ok &= assert_eq(vt.get_line_text(1), "ABCDEF", "Wrapped to line 1")

    vt2 = VirtualTerminal(width=10, height=4)
    for i in range(20):
        vt2.feed(f"Line{i:02d}\n")
    ok &= assert_eq(vt2.get_line_text(0), "Line17", "Auto-scroll: line 0 = #17")
    ok &= assert_eq(vt2.get_line_text(2), "Line19", "Auto-scroll: line 2 = #19")
    ok &= assert_eq(vt2.get_line_text(3).strip(), "", "Auto-scroll: last line empty after scroll")

    print("PASS" if ok else "FAIL")
    return ok


def test_scroll_region():
    print("\n=== Test 11: 滚动区域 DECSTBM ===")
    vt = VirtualTerminal(width=20, height=10)
    for i in range(8):
        vt.feed(f"Row{i:02d}\n")
    vt.feed(f"{ESC}[3;8r")
    vt.feed(f"{ESC}[5;1H")
    vt.feed("\n\n\n")
    ok = assert_eq(vt.get_line_text(0), "Row00", "Region: outside top (row0) intact")
    ok &= assert_eq(vt.get_line_text(1), "Row01", "Region: outside top (row1) intact")
    ok &= assert_eq(vt.get_line_text(7), "Row07", "Region: outside bottom (row7) intact")
    ok &= assert_eq(vt.get_line_text(8).strip(), "", "Region: outside bottom (row8) empty/unused")

    print("PASS" if ok else "FAIL")
    return ok


def test_scroll_up_down():
    print("\n=== Test 12: SU/SD 滚动 ===")
    vt = VirtualTerminal(width=20, height=6)
    for i in range(5):
        vt.feed(f"R{i:02d}ABCDEFGHIJKLMN\n")
    vt.feed(f"{ESC}[2S")
    ok = assert_eq(vt.get_line_text(0), "R02ABCDEFGHIJKLMN", "SU 2: new row 0 = old row 2")
    ok &= assert_eq(vt.get_line_text(4).strip(), "", "SU 2: row 4 empty")
    ok &= assert_eq(vt.get_line_text(5).strip(), "", "SU 2: row 5 empty")

    vt2 = VirtualTerminal(width=20, height=6)
    for i in range(5):
        vt2.feed(f"R{i:02d}XXXXXXXXXXXXXXXX\n")
    vt2.feed(f"{ESC}[3T")
    ok &= assert_eq(vt2.get_line_text(0).strip(), "", "SD 3: row 0 empty")
    ok &= assert_eq(vt2.get_line_text(3), "R00XXXXXXXXXXXXXXXX", "SD 3: row 3 = old row 0")
    ok &= assert_eq(vt2.get_line_text(4), "R01XXXXXXXXXXXXXXXX", "SD 3: row 4 = old row 1")

    print("PASS" if ok else "FAIL")
    return ok


def test_unknown_sequences_safe_skip():
    print("\n=== Test 13: 未识别序列安全跳过 ===")
    vt = VirtualTerminal(width=60, height=5)
    vt.feed("Before")
    vt.feed(f"{ESC}[999z")
    vt.feed(f"{ESC}[?42h")
    vt.feed(f"{ESC}]9999;long ignored text\x07")
    vt.feed(f"{ESC}#8")
    vt.feed("After")
    text = vt.get_screen_text()
    ok = assert_eq("BeforeAfter" in text, True, f"Unknown seq skipped: got {repr(text)}")
    ok &= assert_eq(vt._parse_state, ParseState.GROUND, "Parser back to GROUND state")
    print("PASS" if ok else "FAIL")
    return ok


def test_tab_handling():
    print("\n=== Test 14: Tab 处理 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed("A\tB\tC")
    ok = assert_eq(vt.get_line_text(0), "A       B       C", "Tab stops every 8")
    ok &= assert_eq(vt.get_cell(0, 8).char, "B", "Tab B at col 8")
    ok &= assert_eq(vt.get_cell(0, 16).char, "C", "Tab C at col 16")
    print("PASS" if ok else "FAIL")
    return ok


def test_bs_backspace():
    print("\n=== Test 15: Backspace 退格 ===")
    vt = VirtualTerminal(width=40, height=5)
    vt.feed("ABCDE\b\bX")
    ok = assert_eq(vt.get_line_text(0), "ABCXE", "Backspace: remove D, insert X")
    vt2 = VirtualTerminal(width=40, height=5)
    vt2.feed("\b\b\bA")
    ok &= assert_eq(vt2.get_line_text(0), "A", "Backspace at col 0 stays")
    print("PASS" if ok else "FAIL")
    return ok


def test_render_screen_text():
    print("\n=== Test 16: 屏幕快照纯文本渲染 ===")
    vt = VirtualTerminal(width=30, height=6)
    vt.feed("Title: Example\n")
    vt.feed("Line 2 content\n")
    vt.feed("\n")
    vt.feed("Line 4\n")
    result = vt.get_screen_text()
    lines = result.split("\n")
    ok = assert_eq(len(lines), 4, "Render 4 non-empty lines (trailing stripped)")
    ok &= assert_eq(lines[0], "Title: Example", "Line 0 correct")
    ok &= assert_eq(lines[1], "Line 2 content", "Line 1 correct")
    print("PASS" if ok else "FAIL")
    return ok


def test_private_modes():
    print("\n=== Test 17: 私有模式 (DECTCEM 等) ===")
    vt = VirtualTerminal(width=30, height=5)
    vt.feed(f"{ESC}[?25l")
    ok = assert_eq(vt.cursor_visible, False, "DECTCEM hide cursor")
    vt.feed(f"{ESC}[?25h")
    ok &= assert_eq(vt.cursor_visible, True, "DECTCEM show cursor")
    print("PASS" if ok else "FAIL")
    return ok


def test_convenience_functions():
    print("\n=== Test 18: 便捷函数 ===")
    output = f"{ESC}[1;33mHello{ESC}[0m\nWorld"
    result = render_terminal_output(output, width=20, height=5)
    ok = assert_eq("Hello" in result, True, "render_terminal_output: Hello")
    ok &= assert_eq("World" in result, True, "render_terminal_output: World")

    vt = parse_and_snapshot(output, width=20, height=5)
    ok &= assert_eq(vt.get_cell(0, 0).fg, 3, "parse_and_snapshot: yellow FG")
    ok &= assert_eq(bool(vt.get_cell(0, 0).style & STYLE_BOLD), True, "parse_and_snapshot: bold")
    print("PASS" if ok else "FAIL")
    return ok


def test_integration_complex_output():
    print("\n=== Test 19: 综合复杂终端输出 ===")
    vt = VirtualTerminal(width=48, height=14)

    vt.feed(f"{ESC}[2J{ESC}[H")

    inner = 46
    vt.feed(f"{ESC}[1;36m+{'-'*inner}+{ESC}[0m\n")

    title = "Welcome to VT"
    title_prefix = "   " + title
    title_pad = inner - len(title_prefix) - 1
    vt.feed(f"{ESC}[1;36m|{ESC}[0m {ESC}[1;37m{title_prefix}{ESC}[0m{' '*title_pad}{ESC}[1;36m|{ESC}[0m\n")

    vt.feed(f"{ESC}[1;36m+{'-'*inner}+{ESC}[0m\n")

    menu_items = ["File", "Edit", "View", "Help"]
    for i, item in enumerate(menu_items):
        prefix = f"[{i+1}] {item}"
        spaces = inner - len(prefix) - 1
        vt.feed(f"{ESC}[1;36m|{ESC}[0m {ESC}[32m{prefix}{ESC}[0m{' '*spaces}{ESC}[1;36m|{ESC}[0m\n")

    vt.feed(f"{ESC}[1;36m+{'-'*inner}+{ESC}[0m")

    lines = vt.get_screen_text().split("\n")
    ok = len(lines) >= 7
    ok &= assert_eq("Welcome to VT" in lines[1], True, "Integration: Welcome found in line 1")
    ok &= assert_eq("[1] File" in lines[3], True, "Integration: Menu item 1 File in line 3")
    ok &= assert_eq("[3] View" in lines[5], True, "Integration: Menu item 3 View in line 5")

    border_cell = vt.get_cell(0, 0)
    ok &= assert_eq(border_cell.char, "+", "Integration: top-left border char '+'")
    ok &= assert_eq(border_cell.fg, 6, "Integration: cyan FG for border (color 6)")
    ok &= assert_eq(border_cell.style & STYLE_BOLD, STYLE_BOLD, "Integration: bold border style")

    item_cell = vt.get_cell(3, 2)
    ok &= assert_eq(item_cell.char, "[", "Integration: menu '[' bracket at row3 col2")
    ok &= assert_eq(item_cell.fg, 2, "Integration: green color (2) for menu number")

    print("PASS" if ok else "FAIL")
    return ok


def test_origin_mode():
    print("\n=== Test 20: Origin Mode (DECOM) ===")
    vt = VirtualTerminal(width=30, height=10)
    vt.feed(f"{ESC}[3;8r")
    vt.feed(f"{ESC}[?6h")
    vt.feed(f"{ESC}[1;1H")
    ok = assert_eq(vt.cursor_row, 2, "Origin: row 1 → scroll_top+0 = 2")
    ok &= assert_eq(vt.cursor_col, 0, "Origin: col 1 = 0")
    vt.feed(f"{ESC}[100;100H")
    ok &= assert_eq(vt.cursor_row, 7, "Origin: clamped to scroll_bottom (7)")
    ok &= assert_eq(vt.cursor_col, 29, "Origin: clamped to width-1")
    vt.feed(f"{ESC}[?6l")
    vt.feed(f"{ESC}[1;1H")
    ok &= assert_eq(vt.cursor_row, 0, "Normal: row 1 → 0")
    print("PASS" if ok else "FAIL")
    return ok


def test_bright_colors():
    print("\n=== Test 21: Bright 16 colors (90-97 / 100-107) ===")
    vt = VirtualTerminal(width=30, height=3)
    vt.feed(f"{ESC}[91;104mBrightRedOnBrightBlue{ESC}[0m")
    c = vt.get_cell(0, 0)
    ok = assert_eq(c.fg, 9, "91 → bright red index 9")
    ok &= assert_eq(c.bg, 12, "104 → bright blue index 12")
    print("PASS" if ok else "FAIL")
    return ok


def run_all_tests():
    print("=" * 60)
    print("ANSI 终端转义序列处理引擎 测试套件")
    print("=" * 60)

    tests = [
        test_basic_text,
        test_newline_and_cr,
        test_cursor_movement,
        test_cursor_boundary,
        test_sgr_colors_and_styles,
        test_sgr_256_colors,
        test_sgr_rgb_truecolor,
        test_sgr_style_accumulation,
        test_clear_operations,
        test_auto_wrap_and_scroll,
        test_scroll_region,
        test_scroll_up_down,
        test_unknown_sequences_safe_skip,
        test_tab_handling,
        test_bs_backspace,
        test_render_screen_text,
        test_private_modes,
        test_convenience_functions,
        test_integration_complex_output,
        test_origin_mode,
        test_bright_colors,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            if t():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"EXCEPTION in {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 个测试")
    print("=" * 60)
    return failed == 0


def demo_render():
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

    print("\n" + "=" * 60)
    print("Demo: Rendering complex terminal UI")
    print("=" * 60)

    output = []
    output.append(f"{ESC}[2J{ESC}[H")
    output.append(f"{ESC}[1;34m+{'='*62}+{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[1;37mANSI Virtual Terminal Demo Engine{ESC}[0m  {ESC}[1;30m(C) 2024{ESC}[0m             {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m+{'='*62}+{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[32m>* {ESC}[1mCursor Movement{ESC}[0m  - CUU/CUD/CUF/CUB/CUP supported    {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[32m>* {ESC}[1mColors & Styles{ESC}[0m - 16/256/RGB, bold/underline        {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[32m>* {ESC}[1mScrolling{ESC}[0m       - DECSTBM, SU, SD auto-scroll        {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[32m>* {ESC}[1mErase{ESC}[0m           - ED (0/1/2), EL (0/1/2)              {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[31m>x {ESC}[9mUnimplemented{ESC}[0m   - Just kidding, everything works!     {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m+{'='*62}+{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[38;5;196mR{ESC}[38;5;202mA{ESC}[38;5;226mI{ESC}[38;5;46mN{ESC}[38;5;21mB{ESC}[38;5;93mO{ESC}[38;5;201mW{ESC}[0m 256-color gradient...                  {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m|{ESC}[0m  {ESC}[7mReverse video with {ESC}[1mbold{ESC}[22m normal{ESC}[27m                           {ESC}[1;34m|{ESC}[0m")
    output.append(f"{ESC}[1;34m+{'='*62}+{ESC}[0m")
    output.append(f"\n{ESC}[3mCursor will be positioned after this line...{ESC}[0m")

    full_output = "\n".join(output)

    vt = VirtualTerminal(width=64, height=15)
    vt.feed(full_output)

    print("\n--- Plain text snapshot ---")
    print(vt.get_screen_text(rstrip_lines=False, rstrip_trailing=False))

    print("\n--- Rendered with ANSI colors (shows colors in a real terminal) ---")
    rendered = vt.render_ansi(rstrip_lines=False, rstrip_trailing=False)
    print(rendered)


if __name__ == "__main__":
    success = run_all_tests()
    demo_render()
    sys.exit(0 if success else 1)
