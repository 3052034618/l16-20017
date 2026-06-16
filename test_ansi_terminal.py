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


def test_feed_bytes_basic():
    print("\n=== Test 22: feed_bytes 基本 UTF-8 输入 ===")
    vt = VirtualTerminal(width=30, height=5)
    vt.feed_bytes("Hello 世界".encode("utf-8"))
    ok = assert_eq(vt.get_line_text(0), "Hello 世界", "UTF-8 Chinese rendered")
    ok &= assert_eq(vt.cursor_col, 8, "cursor after 8 chars")

    ba = bytearray(b"bytearray input")
    vt2 = VirtualTerminal(width=30, height=5)
    vt2.feed_bytes(ba)
    ok &= assert_eq(vt2.get_line_text(0), "bytearray input", "bytearray accepted")

    mv = memoryview(b"memoryview works")
    vt3 = VirtualTerminal(width=30, height=5)
    vt3.feed_bytes(mv)
    ok &= assert_eq(vt3.get_line_text(0), "memoryview works", "memoryview accepted")
    print("PASS" if ok else "FAIL")
    return ok


def test_feed_bytes_split_utf8():
    print("\n=== Test 23: UTF-8 半个字符跨 chunk 不乱码 ===")
    text = "Aä中🙂"
    encoded = text.encode("utf-8")
    vt_full = VirtualTerminal(width=30, height=5)
    vt_full.feed_bytes(encoded)
    expected = vt_full.get_screen_text()

    for split_point in range(1, len(encoded)):
        vt = VirtualTerminal(width=30, height=5)
        vt.feed_bytes(encoded[:split_point], final=False)
        vt.feed_bytes(encoded[split_point:], final=True)
        got = vt.get_screen_text()
        if got != expected:
            print(f"  Split at {split_point} failed")
            print(f"  expected: {repr(expected)}")
            print(f"  actual:   {repr(got)}")
            return False

    vt_multi = VirtualTerminal(width=30, height=5)
    for b in encoded:
        vt_multi.feed_bytes(bytes([b]), final=False)
    vt_multi.feed_bytes(b"", final=True)
    ok = assert_eq(vt_multi.get_screen_text(), expected, "byte-by-byte decode matches")

    ok &= assert_eq(vt_full.get_line_text(0), text, "full expected text")
    print("PASS" if ok else "FAIL")
    return ok


def test_feed_bytes_invalid_utf8():
    print("\n=== Test 24: 非法 UTF-8 字节不崩溃 (errors=replace) ===")
    vt = VirtualTerminal(width=30, height=5)
    bad = b"Hello \xff\xfe\x00 World"
    raised = False
    try:
        vt.feed_bytes(bad)
    except Exception as e:
        raised = True
        print(f"  EXCEPTION: {e}")
    ok = assert_eq(raised, False, "no exception on bad bytes")
    ok &= assert_eq("Hello" in vt.get_screen_text(), True, "text Hello present")
    ok &= assert_eq("World" in vt.get_screen_text(), True, "text World present")
    print("PASS" if ok else "FAIL")
    return ok


def test_decstbm_default_params():
    print("\n=== Test 25: DECSTBM 省略参数恢复整屏滚动 ===")
    vt = VirtualTerminal(width=30, height=10)
    vt.feed(f"{ESC}[3;8r")
    ok = assert_eq(vt.scroll_top, 2, "After ESC[3;8r: top=2")
    ok &= assert_eq(vt.scroll_bottom, 7, "After ESC[3;8r: bottom=7")

    vt.feed(f"{ESC}[r")
    ok &= assert_eq(vt.scroll_top, 0, "ESC[r → top=0 (full screen)")
    ok &= assert_eq(vt.scroll_bottom, 9, "ESC[r → bottom=9 (full screen)")

    vt.feed(f"{ESC}[4;7r")
    vt.feed(f"{ESC}[;r")
    ok &= assert_eq(vt.scroll_top, 0, "ESC[;r → top=0")
    ok &= assert_eq(vt.scroll_bottom, 9, "ESC[;r → bottom=9")

    vt.feed(f"{ESC}[5;6r")
    vt.feed(f"{ESC}[0;0r")
    ok &= assert_eq(vt.scroll_top, 0, "ESC[0;0r → top=0")
    ok &= assert_eq(vt.scroll_bottom, 9, "ESC[0;0r → bottom=9")
    print("PASS" if ok else "FAIL")
    return ok


def test_save_restore_cursor_esc78():
    print("\n=== Test 26: ESC 7/8 保存恢复光标 + 属性 ===")
    vt = VirtualTerminal(width=30, height=10)
    vt.feed(f"{ESC}[5;15H")
    vt.feed(f"{ESC}[1;31m")
    vt.feed("\x1b7")
    ok = assert_eq(vt.cursor_row, 4, "before save: row 4")
    ok &= assert_eq(vt.cursor_col, 14, "before save: col 14")
    ok &= assert_eq(vt.rendition.fg, 1, "before save: FG red")

    vt.feed(f"{ESC}[10;1H")
    vt.feed(f"{ESC}[32m")
    ok &= assert_eq(vt.cursor_row, 9, "moved to row 9")
    ok &= assert_eq(vt.rendition.fg, 2, "changed to FG green")

    vt.feed("\x1b8")
    ok &= assert_eq(vt.cursor_row, 4, "restore: row 4")
    ok &= assert_eq(vt.cursor_col, 14, "restore: col 14")
    ok &= assert_eq(vt.rendition.fg, 1, "restore: FG red back")
    ok &= assert_eq(bool(vt.rendition.style & STYLE_BOLD), True, "restore: bold back")

    vt2 = VirtualTerminal(width=30, height=10)
    vt2.feed("\x1b8")
    ok &= assert_eq(vt2.cursor_row, 0, "restore without save → row 0")
    ok &= assert_eq(vt2.cursor_col, 0, "restore without save → col 0")
    print("PASS" if ok else "FAIL")
    return ok


def test_insert_delete_chars_ich_dch():
    print("\n=== Test 27: 插入字符 ICH(@) / 删除字符 DCH(P) ===")
    vt = VirtualTerminal(width=20, height=5)
    vt.feed("ABCDEFGHIJ")
    vt.feed(f"{ESC}[1;5H")
    vt.feed(f"{ESC}[3@")
    line = vt.get_line_text(0)
    ok = assert_eq(line, "ABCD   EFGHIJ".rstrip(), "ICH 3 at col4 inserts 3 spaces")

    vt2 = VirtualTerminal(width=20, height=5)
    vt2.feed("ABCDEFGHIJKLMNOPQRST")
    vt2.feed(f"{ESC}[1;6H")
    vt2.feed(f"{ESC}[4P")
    ok &= assert_eq(vt2.get_line_text(0), "ABCDEJKLMNOPQRST".ljust(20).rstrip(),
                   "DCH 4 at col5 removes F G H I")

    vt3 = VirtualTerminal(width=10, height=3)
    vt3.feed("0123456789")
    vt3.feed(f"{ESC}[1;8H")
    vt3.feed(f"{ESC}[5@")
    ok &= assert_eq(vt3.get_line_text(0), "0123456     ".rstrip(),
                   "ICH 5 near end: inserts 5 spaces, chars shifted out dropped")

    vt4 = VirtualTerminal(width=10, height=3)
    vt4.feed("ABCDEFGHIJ")
    vt4.feed(f"{ESC}[1;6H")
    vt4.feed(f"{ESC}[10P")
    ok &= assert_eq(vt4.get_line_text(0), "ABCDE",
                   "DCH 10 deletes everything from cursor, pad with spaces")
    print("PASS" if ok else "FAIL")
    return ok


def test_insert_delete_lines_il_dl():
    print("\n=== Test 28: 插入行 IL(L) / 删除行 DL(M) ===")
    vt = VirtualTerminal(width=20, height=8)
    for i in range(6):
        vt.feed(f"Row{i}\n")

    vt.feed(f"{ESC}[3;1H")
    vt.feed(f"{ESC}[2L")
    ok = assert_eq(vt.get_line_text(0), "Row0", "IL 2: Row0 intact")
    ok &= assert_eq(vt.get_line_text(1), "Row1", "IL 2: Row1 intact")
    ok &= assert_eq(vt.get_line_text(2).strip(), "", "IL 2: Row2 empty (inserted)")
    ok &= assert_eq(vt.get_line_text(3).strip(), "", "IL 2: Row3 empty (inserted)")
    ok &= assert_eq(vt.get_line_text(4), "Row2", "IL 2: Row4 = old Row2")
    ok &= assert_eq(vt.get_line_text(6), "Row4", "IL 2: Row6 = old Row4")

    vt2 = VirtualTerminal(width=20, height=8)
    for i in range(6):
        vt2.feed(f"Row{i}\n")
    vt2.feed(f"{ESC}[2;1H")
    vt2.feed(f"{ESC}[2M")
    ok &= assert_eq(vt2.get_line_text(0), "Row0", "DL 2: Row0 intact")
    ok &= assert_eq(vt2.get_line_text(1), "Row3", "DL 2: Row1 = old Row3")
    ok &= assert_eq(vt2.get_line_text(2), "Row4", "DL 2: Row2 = old Row4")
    ok &= assert_eq(vt2.get_line_text(4).strip(), "", "DL 2: last lines empty")
    print("PASS" if ok else "FAIL")
    return ok


def test_ncurses_like_workflow():
    print("\n=== Test 29: ncurses 风格综合流程 ===")
    vt = VirtualTerminal(width=40, height=10)

    vt.feed(f"{ESC}[2J{ESC}[H")
    vt.feed(f"{ESC}[1;30;47mHeader: Title{ESC}[0m")
    vt.feed(f"{ESC}[2;1H")
    for i in range(1, 6):
        vt.feed(f"Item {i}: data{i:04d}\n")

    vt.feed(f"{ESC}[5;1H")
    vt.feed(f"{ESC}[1L")
    vt.feed(f"{ESC}[5;1H")
    vt.feed(f"  -> Inserted row here")

    vt.feed(f"{ESC}[3;5H")
    vt.feed(f"{ESC}[2@")
    vt.feed(f"{ESC}[1;33mXX{ESC}[0m")

    vt.feed(f"{ESC}[10;1H")
    vt.feed(f"Status bar at bottom")

    ok = "Header: Title" in vt.get_line_text(0)
    ok &= "Inserted row here" in vt.get_line_text(4)
    ok &= "Status bar at bottom" in vt.get_line_text(9)
    ok &= assert_eq(ok, True, "ncurses-style flow works")

    c = vt.get_cell(2, 4)
    ok &= assert_eq(c.char, "X", "inserted XX first char")
    ok &= assert_eq(c.fg, 3, "XX yellow FG")

    print("PASS" if ok else "FAIL")
    return ok


def test_json_export():
    print("\n=== Test 30: JSON 导出功能 ===")
    vt = VirtualTerminal(width=10, height=4)
    vt.feed(f"{ESC}[1;31mHi{ESC}[0m")
    vt.feed(f"{ESC}[2;1H")
    vt.feed(f"{ESC}[38;5;196mRed{ESC}[0m")

    json_str = vt.to_json(indent=2)
    ok = assert_eq(isinstance(json_str, str), True, "json returns str")
    data = json.loads(json_str)
    ok &= assert_eq(data["width"], 10, "width in JSON")
    ok &= assert_eq(data["height"], 4, "height in JSON")
    ok &= assert_eq(data["cursor"]["row"], 1, "cursor row in JSON")
    ok &= assert_eq(data["scroll_region"]["top"], 0, "scroll region top")

    rows = data["rows"]
    ok &= assert_eq(len(rows) >= 2, True, "at least 2 rows with content")

    r0_cells = [r for r in rows if r["row"] == 0][0]["cells"]
    hi_cell = [c for c in r0_cells if c["col"] == 0][0]
    ok &= assert_eq(hi_cell["ch"], "H", "cell H at row0 col0")
    ok &= assert_eq(hi_cell["fg"], 1, "cell H red FG")
    ok &= assert_eq("bold" in hi_cell.get("style_names", []), True, "bold in style_names")

    r1_cells = [r for r in rows if r["row"] == 1][0]["cells"]
    red_cell = [c for c in r1_cells if c["col"] == 0][0]
    ok &= assert_eq(red_cell["fg"], 196, "256-color index 196")

    full_json = vt.to_json(include_empty=True, indent=None,
                           rstrip_lines=False, rstrip_trailing=False)
    full_data = json.loads(full_json)
    total_cells = sum(len(r["cells"]) for r in full_data["rows"])
    ok &= assert_eq(total_cells, 4 * 10, "full export = 4x10 = 40 cells")

    print("PASS" if ok else "FAIL")
    return ok


def test_cli_args_and_helpers():
    print("\n=== Test 31: CLI 参数解析和便捷函数 ===")
    from ansi_terminal import _build_arg_parser, main, render_terminal_output
    parser = _build_arg_parser()
    args = parser.parse_args([])
    ok = assert_eq(args.width, 80, "default width=80")
    ok &= assert_eq(args.height, 24, "default height=24")
    ok &= assert_eq(args.json, False, "default no json")
    ok &= assert_eq(args.ansi, False, "default no ansi")

    args2 = parser.parse_args(["-W", "120", "-H", "50", "--json", "--full"])
    ok &= assert_eq(args2.width, 120, "custom width")
    ok &= assert_eq(args2.height, 50, "custom height")
    ok &= assert_eq(args2.json, True, "json flag")
    ok &= assert_eq(args2.full, True, "full flag")

    out = render_terminal_output("Hello\nWorld\n", width=40, height=5)
    ok &= assert_eq("Hello" in out and "World" in out, True, "render_terminal_output works")

    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".log", delete=False) as tmp:
        tmp.write(b"\x1b[1mBold\x1b[0m text\nNext line")
        tmp_path = tmp.name
    try:
        rc = main(["-f", tmp_path, "-W", "60", "-H", "10", "-o", os.devnull])
        ok &= assert_eq(rc, 0, f"CLI file mode exit code {rc}")
        rc2 = main(["-f", tmp_path, "--json", "-o", os.devnull])
        ok &= assert_eq(rc2, 0, f"CLI json mode exit code {rc2}")
        rc3 = main(["-f", tmp_path, "--ansi", "-o", os.devnull])
        ok &= assert_eq(rc3, 0, f"CLI ansi mode exit code {rc3}")
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

    rc_bad = main(["-f", "/nonexistent/zzz_12345.log", "-o", os.devnull])
    ok &= assert_eq(rc_bad, 2, "missing file returns 2")
    print("PASS" if ok else "FAIL")
    return ok


def test_chunked_bytes_matches_full_string():
    print("\n=== Test 32: 分块字节流 = 一次性完整字符串 ===")
    data = (
        f"{ESC}[2J{ESC}[H"
        f"{ESC}[1;36m+--------+{ESC}[0m\n"
        f"{ESC}[1;36m|{ESC}[0m AAAAAA {ESC}[1;36m|{ESC}[0m\n"
        f"{ESC}[1;36m|{ESC}[0m {ESC}[31mBBBB{ESC}[0m {ESC}[1;36m|{ESC}[0m\n"
        f"{ESC}[1;36m+--------+{ESC}[0m\n"
        f"UTF-8: \u4e2d\u6587 emoji: \U0001F600"
    ).encode("utf-8")

    vt_str = VirtualTerminal(30, 12)
    vt_str.feed(data.decode("utf-8"))

    import random
    random.seed(42)
    for _ in range(20):
        vt_chunk = VirtualTerminal(30, 12)
        i = 0
        while i < len(data):
            size = random.randint(1, 7)
            end = min(i + size, len(data))
            vt_chunk.feed_bytes(data[i:end], final=(end >= len(data)))
            i = end
        ok = (vt_str.get_screen_text() == vt_chunk.get_screen_text())
        if not ok:
            print("  random chunk mismatch")
            print(f"  expected: {repr(vt_str.get_screen_text())}")
            print(f"  actual:   {repr(vt_chunk.get_screen_text())}")
            return False

    vt_1b = VirtualTerminal(30, 12)
    for b in data:
        vt_1b.feed_bytes(bytes([b]), final=False)
    vt_1b.feed_bytes(b"", final=True)
    ok = assert_eq(vt_1b.get_screen_text(), vt_str.get_screen_text(),
                   "1-byte chunking matches full string")
    print("PASS" if ok else "FAIL")
    return ok


import json
import io
import os
import tempfile
import random


def test_unified_feed_accepts_all_types():
    print("\n=== Test 33: 统一 feed() 接受 str/bytes/bytearray/memoryview ===")
    text = "Hello 中文 \U0001F600"
    ok = True
    for payload in (
        text,
        text.encode("utf-8"),
        bytearray(text.encode("utf-8")),
        memoryview(text.encode("utf-8")),
    ):
        vt = VirtualTerminal(width=40, height=5)
        vt.feed(payload)
        got = vt.get_line_text(0)
        ok &= assert_eq(got, text, f"feed({type(payload).__name__}) correct")
    try:
        vt_bad = VirtualTerminal(10, 3)
        vt_bad.feed(12345)
        ok &= False
    except TypeError:
        pass
    except Exception as e:
        ok &= False
        print(f"  unexpected exception: {e}")
    print("PASS" if ok else "FAIL")
    return ok


def test_feed_bytes_byte_by_byte_consistency():
    print("\n=== Test 34: 单字节逐个喂 vs 完整字符串 完全一致 ===")
    data = (
        f"{ESC}[2J{ESC}[H"
        f"{ESC}[1;31mLine1 red{ESC}[0m\n"
        f"{ESC}[1;32mLine2 green{ESC}[0m with \u4e2d\u6587\n"
        f"emoji: \U0001F600 \U0001F603\n"
    ).encode("utf-8")

    vt_full = VirtualTerminal(60, 10)
    vt_full.feed(data.decode("utf-8"))
    expected_text = vt_full.get_screen_text()

    vt_1b = VirtualTerminal(60, 10)
    for b in data:
        vt_1b.feed(bytes([b]), final=False)
    vt_1b.feed(b"", final=True)
    ok = assert_eq(vt_1b.get_screen_text(), expected_text,
                   "byte-by-byte feed matches full string")

    for n in (1, 2, 3, 5, 7, 11, 16):
        random.seed(n)
        vt_rnd = VirtualTerminal(60, 10)
        i = 0
        while i < len(data):
            sz = random.randint(1, n)
            end = min(i + sz, len(data))
            vt_rnd.feed(data[i:end], final=(end >= len(data)))
            i = end
        ok &= assert_eq(vt_rnd.get_screen_text(), expected_text,
                        f"random chunk size={n} matches")
    print("PASS" if ok else "FAIL")
    return ok


def test_progress_bar_carriage_return_rewrite():
    print("\n=== Test 35: 彩色进度条反复 CR 覆盖 ===")
    vt = VirtualTerminal(width=60, height=5)
    vt.start_recording()
    for pct in (10, 25, 50, 75, 100):
        filled = pct // 2
        bar = "[" + "#" * filled + "-" * (50 - filled) + f"] {pct:3d}%"
        vt.feed(f"\r{ESC}[32m{bar}{ESC}[0m")
    hist = vt.get_history()
    ok = assert_eq(len(hist) >= 5, True, f"至少 5 帧 (实际 {len(hist)})")
    ok &= assert_eq(vt.cursor_row, 0, "进度条始终在第 0 行")
    final_line = vt.get_line_text(0)
    expected_final = "[" + "#" * 50 + "] 100%"
    ok &= assert_eq(expected_final in final_line, True, f"最终帧含 {expected_final!r}")
    first_changed = hist[1]["changed_cells"]
    ok &= assert_eq(len(first_changed) > 0, True, "帧间确实记录了变化")
    vt.stop_recording()
    print("PASS" if ok else "FAIL")
    return ok


def test_recording_seek_and_replay():
    print("\n=== Test 36: 录制 seek_snapshot / replay_frames ===")
    vt = VirtualTerminal(width=30, height=8)
    vt.start_recording()
    vt.feed("Line A\n")
    vt.feed("Line B\n")
    vt.feed("Line C\n")
    vt.feed(f"{ESC}[2;5HINJECTED\n")
    frames = vt.stop_recording()

    ok = assert_eq(len(frames) >= 4, True, f"录制 {len(frames)} 帧")
    snap_end = vt.seek_snapshot(-1)
    ok &= assert_eq(snap_end is not None, True, "seek_snapshot(-1) 有结果")
    ok &= assert_eq(snap_end.get("cursor", {}).get("row") is not None, True, "snapshot 含 cursor")

    snap_frame2 = vt.seek_snapshot(2)
    ok &= assert_eq(snap_frame2 is not None, True, "seek_snapshot(2) 有结果")

    vt2 = VirtualTerminal(width=30, height=8)
    vt2.replay_frames(frames)
    ok &= assert_eq(vt2.get_line_text(0), "Line A", "replay 后第 0 行一致")
    ok &= assert_eq(vt2.get_line_text(1).startswith("LineINJECTED"), True, "replay 后 INJECTED 覆盖生效")
    print("PASS" if ok else "FAIL")
    return ok


def test_scroll_region_insert_delete_lines_realistic():
    print("\n=== Test 37: 滚动区域内插入删除行 (ncurses 菜单风格) ===")
    vt = VirtualTerminal(width=40, height=10)
    vt.feed(f"{ESC}[2;9r")

    for i in range(1, 9):
        vt.feed(f"Item {i}\n")
    vt.feed(f"{ESC}[2;1H")

    vt.feed(f"{ESC}[1L")
    vt.feed(f"{ESC}[1;33m  -> NEW ITEM <-{ESC}[0m")

    ok = assert_eq(vt.scroll_top, 1, "scroll_top=1")
    ok &= assert_eq(vt.scroll_bottom, 8, "scroll_bottom=8")
    ok &= assert_eq("NEW ITEM" in vt.get_line_text(1), True, "NEW ITEM 写入 row1")

    vt.feed(f"{ESC}[4;1H")
    vt.feed(f"{ESC}[2M")

    ok &= assert_eq(("Item 5" in vt.get_line_text(3)) or ("Item 6" in vt.get_line_text(3)), True, "row3 存在Item 5/6")
    last_row_text = vt.get_line_text(8)
    ok &= assert_eq(last_row_text.strip() == "", True, "滚动区域底部是空行")
    print("PASS" if ok else "FAIL")
    return ok


def test_json_export_enhancements():
    print("\n=== Test 38: JSON 增强选项 (with_text/mark_styled/cursor_history/changed_only) ===")
    vt = VirtualTerminal(width=20, height=6)
    vt.start_recording()
    vt.feed(f"{ESC}[1;31mHello{ESC}[0m world")
    vt.feed(f"\nplain line here")

    d = vt.to_dict(with_text=True, mark_styled=True,
                   cursor_history=True, changed_only=True)

    ok = assert_eq("text" in d, True, "dict 含 text 字段")
    ok &= assert_eq(isinstance(d["text"], str), True, "text 字段是 str")
    ok &= assert_eq("Hello" in d["text"] and "plain" in d["text"], True, "text 字段含原文")

    r0 = [r for r in d["rows"] if r["row"] == 0][0]
    h_cell = [c for c in r0["cells"] if c.get("col") == 0][0]
    ok &= assert_eq(h_cell.get("styled"), True, "彩色字符带 styled=True 标记")

    ok &= assert_eq("cursor_history" in d, True, "含 cursor_history 字段")
    ok &= assert_eq(isinstance(d["cursor_history"], list), True, "cursor_history 是列表")
    ok &= assert_eq(len(d["cursor_history"]) >= 1, True, "cursor_history 非空")

    ok &= assert_eq("changed_cells" in d, True, "含 changed_cells 字段")
    ok &= assert_eq(isinstance(d["changed_cells"], list), True, "changed_cells 是列表")

    jstr = vt.to_json(with_text=True, mark_styled=True, ensure_ascii=False)
    jdata = json.loads(jstr)
    ok &= assert_eq(jdata.get("text"), d["text"], "JSON text 字段一致")
    vt.stop_recording()
    print("PASS" if ok else "FAIL")
    return ok


def test_history_to_json_export():
    print("\n=== Test 39: history_to_json 帧级差量导出 ===")
    vt = VirtualTerminal(width=30, height=6)
    vt.start_recording()
    vt.feed("Step 1")
    vt.feed("\nStep 2")
    vt.feed(f"\n{ESC}[1;34mStep 3 colored{ESC}[0m")
    hist_json = vt.history_to_json(indent=None, with_full_snapshot=True)
    d = json.loads(hist_json)
    ok = assert_eq(d["width"], 30, "width 正确")
    ok &= assert_eq(d["height"], 6, "height 正确")
    ok &= assert_eq(d["total_frames"] >= 3, True, f"至少 3 帧 (实际 {d['total_frames']})")
    first_frame = d["frames"][0]
    ok &= assert_eq("changed_cells" in first_frame, True, "帧含 changed_cells")
    ok &= assert_eq("cursor" in first_frame, True, "帧含 cursor")
    ok &= assert_eq("snapshot" in first_frame, True, "帧含 snapshot")
    last_frame = d["frames"][-1]
    snap_rows = last_frame.get("snapshot", {}).get("rows", [])
    row_chars = {}
    for r in snap_rows:
        for c in r.get("cells", []):
            row_chars.setdefault(r["row"], {})[c["col"]] = c["ch"]
    last_row = row_chars.get(2, {})
    last_line = "".join(last_row.get(c, " ") for c in range(max(last_row.keys(), default=-1) + 1))
    ok &= assert_eq("Step 3" in last_line, True, "末帧快照含 Step 3")
    vt.stop_recording()
    print("PASS" if ok else "FAIL")
    return ok


def test_cli_pipeline_stdin_vs_file_consistency():
    print("\n=== Test 40: CLI 管道大文件 stdin 读 vs 读文件 一致 ===")
    from ansi_terminal import main
    lines = []
    for i in range(200):
        color = 30 + (i % 8)
        lines.append(f"\x1b[{color}mLine {i:04d} content\x1b[0m")
    payload = "\n".join(lines).encode("utf-8")

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".log", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as out1:
        out1_path = out1.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as out2:
        out2_path = out2.name
    try:
        rc1 = main(["-f", tmp_path, "-W", "60", "-H", "220", "-o", out1_path])
        ok = assert_eq(rc1, 0, "文件模式 rc=0")

        old_stdin = sys.stdin
        try:
            bio = io.BytesIO(payload)
            sys.stdin = type(
                "FakeStdin", (),
                {"buffer": bio, "read": lambda self, *a, **kw: bio.read()},
            )()
            rc2 = main(["-W", "60", "-H", "220", "-o", out2_path])
        finally:
            sys.stdin = old_stdin
        ok &= assert_eq(rc2, 0, "stdin 模式 rc=0")

        with open(out1_path, "r", encoding="utf-8") as f:
            a = f.read()
        with open(out2_path, "r", encoding="utf-8") as f:
            b = f.read()
        ok &= assert_eq(a, b, "两种输入方式输出完全一致")
    finally:
        for p in (tmp_path, out1_path, out2_path):
            try:
                os.unlink(p)
            except Exception:
                pass
    print("PASS" if ok else "FAIL")
    return ok


def test_timestamped_log_parsing_and_cli_at():
    print("\n=== Test 41: 带时间戳日志解析 + --at 回放 ===")
    from ansi_terminal import main, _parse_ts, _split_timestamped_log

    ok = assert_eq(_parse_ts("00:00:01.500"), 1.5, "HH:MM:SS.mmm")
    ok &= assert_eq(_parse_ts("01:23"), 60 + 23, "MM:SS")
    ok &= assert_eq(_parse_ts("123.45"), 123.45, "纯秒数")
    ok &= assert_eq(_parse_ts("[3.5]"), 3.5, "方括号秒数")
    ok &= assert_eq(_parse_ts("+2.1"), 2.1, "+ 秒数")

    log_bytes = (
        b"0.000 Starting up\n"
        b"0.500 Progress 50%\r0.750 Progress 75%\r1.000 Progress 100%\n"
        b"1.500 [INFO] done\n"
    )
    chunks = _split_timestamped_log(log_bytes)
    ok &= assert_eq(len(chunks) >= 3, True, f"切出 {len(chunks)} 段 (>=3)")

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".log", delete=False) as tmp:
        tmp.write(log_bytes)
        tmp_path = tmp.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as outf:
        out_path = outf.name
    try:
        rc = main(["-f", tmp_path, "--timestamps", "--at", "0.8",
                   "-W", "40", "-H", "5", "-o", out_path])
        ok &= assert_eq(rc, 0, "--at 回放 rc=0")
        with open(out_path, "r", encoding="utf-8") as f:
            out_text = f.read()
        ok &= assert_eq(("Progress 75%" in out_text) or ("75" in out_text), True, "--at 0.8 快照含 75%")
    finally:
        for p in (tmp_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass
    print("PASS" if ok else "FAIL")
    return ok


def test_cli_record_and_frame_seek():
    print("\n=== Test 42: CLI --record --frame 帧级回放 ===")
    from ansi_terminal import main
    log_bytes = b"AAAA\nBBBB\nCCCC\nDDDD\n"
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".log", delete=False) as tmp:
        tmp.write(log_bytes)
        tmp_path = tmp.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as out1:
        out1_path = out1.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as out2:
        out2_path = out2.name
    try:
        rc = main(["-f", tmp_path, "--record", "--frame", "2",
                   "-W", "30", "-H", "10", "-o", out1_path])
        ok = assert_eq(rc, 0, "--frame 2 rc=0")
        with open(out1_path, "r", encoding="utf-8") as f:
            t = f.read()
        ok &= assert_eq("AAAA" in t, True, "frame2 含 AAAA")
        ok &= assert_eq("BBBB" in t, True, "frame2 含 BBBB")

        rc2 = main(["-f", tmp_path, "--record", "--history",
                    "-W", "30", "-H", "10", "-o", out2_path])
        ok &= assert_eq(rc2, 0, "--history rc=0")
        with open(out2_path, "r", encoding="utf-8") as f:
            hd = json.load(f)
        ok &= assert_eq("total_frames" in hd, True, "history 含 total_frames")
        ok &= assert_eq(hd["total_frames"] >= 2, True, f"至少 2 帧 (初始 + feed = {hd['total_frames']})")
    finally:
        for p in (tmp_path, out1_path, out2_path):
            try:
                os.unlink(p)
            except Exception:
                pass
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
        test_feed_bytes_basic,
        test_feed_bytes_split_utf8,
        test_feed_bytes_invalid_utf8,
        test_decstbm_default_params,
        test_save_restore_cursor_esc78,
        test_insert_delete_chars_ich_dch,
        test_insert_delete_lines_il_dl,
        test_ncurses_like_workflow,
        test_json_export,
        test_cli_args_and_helpers,
        test_chunked_bytes_matches_full_string,
        test_unified_feed_accepts_all_types,
        test_feed_bytes_byte_by_byte_consistency,
        test_progress_bar_carriage_return_rewrite,
        test_recording_seek_and_replay,
        test_scroll_region_insert_delete_lines_realistic,
        test_json_export_enhancements,
        test_history_to_json_export,
        test_cli_pipeline_stdin_vs_file_consistency,
        test_timestamped_log_parsing_and_cli_at,
        test_cli_record_and_frame_seek,
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
