"""
ANSI 终端转义序列处理引擎

支持的功能:
- 光标移动: CUU, CUD, CUF, CUB, CHA, CUP
- 颜色和样式: SGR (Select Graphic Rendition)
- 清屏清行: ED, EL
- 滚动: SU, SD, DECSTBM
- 自动换行与滚动
- 字符网格: 每个单元格包含字符、前景色、背景色、样式位
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple, Union, TextIO, BinaryIO
import io
import codecs
import json
import argparse
import sys


# ==================== 样式位掩码 ====================
STYLE_BOLD = 1 << 0
STYLE_DIM = 1 << 1
STYLE_ITALIC = 1 << 2
STYLE_UNDERLINE = 1 << 3
STYLE_BLINK = 1 << 4
STYLE_REVERSE = 1 << 5
STYLE_HIDDEN = 1 << 6
STYLE_STRIKETHROUGH = 1 << 7


# ==================== 颜色常量 ====================
COLOR_DEFAULT = -1

# 16 色标准颜色
COLOR_NAMES = {
    0: "black", 1: "red", 2: "green", 3: "yellow",
    4: "blue", 5: "magenta", 6: "cyan", 7: "white",
    8: "bright_black", 9: "bright_red", 10: "bright_green", 11: "bright_yellow",
    12: "bright_blue", 13: "bright_magenta", 14: "bright_cyan", 15: "bright_white",
}

# ANSI 256 色近似 RGB (用于渲染)
def color_256_to_rgb(n: int) -> Optional[Tuple[int, int, int]]:
    if 0 <= n <= 15:
        base = [
            (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
            (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
            (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
            (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
        ]
        return base[n]
    elif 16 <= n <= 231:
        idx = n - 16
        r = idx // 36
        g = (idx % 36) // 6
        b = idx % 6
        levels = [0, 95, 135, 175, 215, 255]
        return (levels[r], levels[g], levels[b])
    elif 232 <= n <= 255:
        gray = 8 + (n - 232) * 10
        return (gray, gray, gray)
    return None


# ==================== 字符单元格 ====================
@dataclass
class Cell:
    char: str = " "
    fg: int = COLOR_DEFAULT
    bg: int = COLOR_DEFAULT
    fg_rgb: Optional[Tuple[int, int, int]] = None
    bg_rgb: Optional[Tuple[int, int, int]] = None
    style: int = 0

    def reset(self):
        self.char = " "
        self.fg = COLOR_DEFAULT
        self.bg = COLOR_DEFAULT
        self.fg_rgb = None
        self.bg_rgb = None
        self.style = 0

    def copy_from(self, other: "Cell"):
        self.char = other.char
        self.fg = other.fg
        self.bg = other.bg
        self.fg_rgb = other.fg_rgb
        self.bg_rgb = other.bg_rgb
        self.style = other.style

    def apply_rendition(self, fg: int, bg: int, fg_rgb: Optional[Tuple[int, int, int]],
                        bg_rgb: Optional[Tuple[int, int, int]], style: int):
        self.fg = fg
        self.bg = bg
        self.fg_rgb = fg_rgb
        self.bg_rgb = bg_rgb
        self.style = style


# ==================== 当前文本渲染属性 ====================
@dataclass
class Rendition:
    fg: int = COLOR_DEFAULT
    bg: int = COLOR_DEFAULT
    fg_rgb: Optional[Tuple[int, int, int]] = None
    bg_rgb: Optional[Tuple[int, int, int]] = None
    style: int = 0

    def reset(self):
        self.fg = COLOR_DEFAULT
        self.bg = COLOR_DEFAULT
        self.fg_rgb = None
        self.bg_rgb = None
        self.style = 0


# ==================== 解析状态 ====================
class ParseState:
    GROUND = "ground"
    ESCAPE = "escape"
    CSI_ENTRY = "csi_entry"
    CSI_PARAM = "csi_param"
    CSI_INTERMEDIATE = "csi_intermediate"
    OSC_STRING = "osc_string"


# ==================== 终端屏幕 ====================
class VirtualTerminal:
    """
    ANSI 兼容的虚拟终端。

    内部坐标系:
      - 行 (row): 0-based, 从上到下
      - 列 (col): 0-based, 从左到右
    用户接口使用 1-based (符合终端惯例)
    """

    def __init__(self, width: int = 80, height: int = 24):
        self.width = width
        self.height = height
        self.grid: List[List[Cell]] = [
            [Cell() for _ in range(width)] for _ in range(height)
        ]
        self.cursor_row = 0
        self.cursor_col = 0
        self.cursor_visible = True
        self.rendition = Rendition()
        self.scroll_top = 0
        self.scroll_bottom = height - 1
        self.auto_wrap = True
        self.origin_mode = False

        self._parse_state = ParseState.GROUND
        self._csi_params: List[int] = []
        self._csi_param_buf = ""
        self._csi_intermediates: List[str] = []
        self._osc_buf = ""
        self._pending_esc = False

        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._saved_cursor: Optional[dict] = None

    # =================================================================
    # 屏幕基础操作
    # =================================================================

    def clear_screen(self):
        for row in self.grid:
            for cell in row:
                cell.reset()

    def clear_row(self, row: int):
        if 0 <= row < self.height:
            for cell in self.grid[row]:
                cell.reset()

    def clear_from_cursor_to_end_screen(self):
        self.clear_from_cursor_to_end_line()
        for r in range(self.cursor_row + 1, self.height):
            self.clear_row(r)

    def clear_from_start_to_cursor_screen(self):
        for r in range(0, self.cursor_row):
            self.clear_row(r)
        self.clear_from_start_to_cursor_line()

    def clear_from_cursor_to_end_line(self):
        if 0 <= self.cursor_row < self.height:
            for c in range(self.cursor_col, self.width):
                self.grid[self.cursor_row][c].reset()

    def clear_from_start_to_cursor_line(self):
        if 0 <= self.cursor_row < self.height:
            for c in range(0, self.cursor_col + 1):
                self.grid[self.cursor_row][c].reset()

    # =================================================================
    # 滚动操作
    # =================================================================

    def set_scroll_region(self, top: int, bottom: int):
        top = max(0, min(self.height - 1, top))
        bottom = max(top, min(self.height - 1, bottom))
        self.scroll_top = top
        self.scroll_bottom = bottom

    def scroll_up(self, n: int = 1):
        if n <= 0:
            return
        n = min(n, self.scroll_bottom - self.scroll_top + 1)
        for _ in range(n):
            for r in range(self.scroll_top, self.scroll_bottom):
                for c in range(self.width):
                    self.grid[r][c].copy_from(self.grid[r + 1][c])
            for c in range(self.width):
                self.grid[self.scroll_bottom][c].reset()

    def scroll_down(self, n: int = 1):
        if n <= 0:
            return
        n = min(n, self.scroll_bottom - self.scroll_top + 1)
        for _ in range(n):
            for r in range(self.scroll_bottom, self.scroll_top, -1):
                for c in range(self.width):
                    self.grid[r][c].copy_from(self.grid[r - 1][c])
            for c in range(self.width):
                self.grid[self.scroll_top][c].reset()

    # =================================================================
    # 光标操作
    # =================================================================

    def _clamp_cursor(self):
        self.cursor_row = max(0, min(self.height - 1, self.cursor_row))
        self.cursor_col = max(0, min(self.width - 1, self.cursor_col))

    def cursor_up(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_row -= n
        if self.origin_mode:
            self.cursor_row = max(self.scroll_top, self.cursor_row)
        else:
            self.cursor_row = max(0, self.cursor_row)

    def cursor_down(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_row += n
        if self.origin_mode:
            self.cursor_row = min(self.scroll_bottom, self.cursor_row)
        else:
            self.cursor_row = min(self.height - 1, self.cursor_row)

    def cursor_forward(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_col += n
        self.cursor_col = min(self.width - 1, self.cursor_col)

    def cursor_backward(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_col -= n
        self.cursor_col = max(0, self.cursor_col)

    def cursor_next_line(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_down(n)
        self.cursor_col = 0

    def cursor_prev_line(self, n: int = 1):
        if n <= 0:
            n = 1
        self.cursor_up(n)
        self.cursor_col = 0

    def cursor_to_column(self, col: int):
        if col <= 0:
            col = 1
        self.cursor_col = col - 1
        self.cursor_col = max(0, min(self.width - 1, self.cursor_col))

    def cursor_position(self, row: int, col: int):
        if row <= 0:
            row = 1
        if col <= 0:
            col = 1
        if self.origin_mode:
            self.cursor_row = row - 1 + self.scroll_top
            self.cursor_row = min(self.scroll_bottom, self.cursor_row)
        else:
            self.cursor_row = row - 1
        self.cursor_col = col - 1
        self._clamp_cursor()

    # =================================================================
    # SGR (Select Graphic Rendition) 处理
    # =================================================================

    def apply_sgr(self, params: List[int]):
        if not params:
            params = [0]

        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self.rendition.reset()
            elif p == 1:
                self.rendition.style |= STYLE_BOLD
            elif p == 2:
                self.rendition.style |= STYLE_DIM
            elif p == 3:
                self.rendition.style |= STYLE_ITALIC
            elif p == 4:
                self.rendition.style |= STYLE_UNDERLINE
            elif p == 5:
                self.rendition.style |= STYLE_BLINK
            elif p == 7:
                self.rendition.style |= STYLE_REVERSE
            elif p == 8:
                self.rendition.style |= STYLE_HIDDEN
            elif p == 9:
                self.rendition.style |= STYLE_STRIKETHROUGH
            elif p == 22:
                self.rendition.style &= ~(STYLE_BOLD | STYLE_DIM)
            elif p == 23:
                self.rendition.style &= ~STYLE_ITALIC
            elif p == 24:
                self.rendition.style &= ~STYLE_UNDERLINE
            elif p == 25:
                self.rendition.style &= ~STYLE_BLINK
            elif p == 27:
                self.rendition.style &= ~STYLE_REVERSE
            elif p == 28:
                self.rendition.style &= ~STYLE_HIDDEN
            elif p == 29:
                self.rendition.style &= ~STYLE_STRIKETHROUGH
            elif 30 <= p <= 37:
                self.rendition.fg = p - 30
                self.rendition.fg_rgb = None
            elif p == 38:
                if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
                    self.rendition.fg = params[i + 2]
                    self.rendition.fg_rgb = color_256_to_rgb(params[i + 2])
                    i += 2
                elif i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
                    self.rendition.fg_rgb = (params[i + 2], params[i + 3], params[i + 4])
                    self.rendition.fg = COLOR_DEFAULT
                    i += 4
            elif p == 39:
                self.rendition.fg = COLOR_DEFAULT
                self.rendition.fg_rgb = None
            elif 40 <= p <= 47:
                self.rendition.bg = p - 40
                self.rendition.bg_rgb = None
            elif p == 48:
                if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
                    self.rendition.bg = params[i + 2]
                    self.rendition.bg_rgb = color_256_to_rgb(params[i + 2])
                    i += 2
                elif i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
                    self.rendition.bg_rgb = (params[i + 2], params[i + 3], params[i + 4])
                    self.rendition.bg = COLOR_DEFAULT
                    i += 4
            elif p == 49:
                self.rendition.bg = COLOR_DEFAULT
                self.rendition.bg_rgb = None
            elif 90 <= p <= 97:
                self.rendition.fg = p - 90 + 8
                self.rendition.fg_rgb = None
            elif 100 <= p <= 107:
                self.rendition.bg = p - 100 + 8
                self.rendition.bg_rgb = None
            i += 1

    # =================================================================
    # 文本输出
    # =================================================================

    def put_char(self, ch: str):
        if ch == "\r":
            self.cursor_col = 0
            return
        if ch == "\n":
            self._handle_newline()
            return
        if ch == "\t":
            tab_width = 8
            next_tab = ((self.cursor_col // tab_width) + 1) * tab_width
            if next_tab >= self.width:
                next_tab = self.width - 1
            self.cursor_col = next_tab
            return
        if ch == "\b":
            if self.cursor_col > 0:
                self.cursor_col -= 1
            return
        if ord(ch) < 0x20:
            return

        if self.cursor_col >= self.width:
            if self.auto_wrap:
                self._handle_newline()
            else:
                self.cursor_col = self.width - 1

        cell = self.grid[self.cursor_row][self.cursor_col]
        cell.char = ch
        cell.apply_rendition(
            self.rendition.fg, self.rendition.bg,
            self.rendition.fg_rgb, self.rendition.bg_rgb,
            self.rendition.style
        )
        self.cursor_col += 1

    def _handle_newline(self):
        if self.cursor_row >= self.scroll_bottom:
            self.scroll_up(1)
            self.cursor_row = self.scroll_bottom
        else:
            self.cursor_row += 1
        self.cursor_col = 0

    # =================================================================
    # CSI 序列分发
    # =================================================================

    def _parse_csi_params(self) -> List[int]:
        if not self._csi_param_buf:
            return []
        parts = self._csi_param_buf.split(";")
        result = []
        for p in parts:
            if p == "":
                result.append(0)
            else:
                try:
                    result.append(int(p))
                except ValueError:
                    result.append(0)
        return result

    def _dispatch_csi(self, final: str):
        params = self._parse_csi_params()
        private = len(self._csi_intermediates) > 0 and self._csi_intermediates[0] == "?"

        if not private:
            if final == "@":
                self.insert_chars(params[0] if params else 1)
            elif final == "A":
                self.cursor_up(params[0] if params else 1)
            elif final == "B":
                self.cursor_down(params[0] if params else 1)
            elif final == "C":
                self.cursor_forward(params[0] if params else 1)
            elif final == "D":
                self.cursor_backward(params[0] if params else 1)
            elif final == "E":
                self.cursor_next_line(params[0] if params else 1)
            elif final == "F":
                self.cursor_prev_line(params[0] if params else 1)
            elif final == "G":
                self.cursor_to_column(params[0] if params else 1)
            elif final == "H" or final == "f":
                row = params[0] if len(params) >= 1 else 1
                col = params[1] if len(params) >= 2 else 1
                self.cursor_position(row, col)
            elif final == "J":
                mode = params[0] if params else 0
                if mode == 0:
                    self.clear_from_cursor_to_end_screen()
                elif mode == 1:
                    self.clear_from_start_to_cursor_screen()
                elif mode == 2:
                    self.clear_screen()
            elif final == "K":
                mode = params[0] if params else 0
                if mode == 0:
                    self.clear_from_cursor_to_end_line()
                elif mode == 1:
                    self.clear_from_start_to_cursor_line()
                elif mode == 2:
                    self.clear_row(self.cursor_row)
            elif final == "L":
                self.insert_lines(params[0] if params else 1)
            elif final == "M":
                self.delete_lines(params[0] if params else 1)
            elif final == "P":
                self.delete_chars(params[0] if params else 1)
            elif final == "S":
                self.scroll_up(params[0] if params else 1)
            elif final == "T":
                self.scroll_down(params[0] if params else 1)
            elif final == "m":
                self.apply_sgr(params)
            elif final == "r":
                top_param = params[0] if (len(params) >= 1 and params[0] > 0) else 1
                bottom_param = params[1] if (len(params) >= 2 and params[1] > 0) else self.height
                top = top_param - 1
                bottom = bottom_param - 1
                if (len(params) == 0 or
                    (len(params) == 1 and params[0] == 0) or
                    (len(params) >= 1 and params[0] <= 0 and (len(params) == 1 or params[1] <= 0))):
                    top = 0
                    bottom = self.height - 1
                self.set_scroll_region(top, bottom)
                self.cursor_position(1, 1)
            elif final == "l":
                if params and params[0] == 7:
                    self.auto_wrap = False
            elif final == "h":
                if params and params[0] == 7:
                    self.auto_wrap = True
            elif final == "d":
                row = params[0] if params else 1
                if row <= 0:
                    row = 1
                if self.origin_mode:
                    self.cursor_row = row - 1 + self.scroll_top
                    self.cursor_row = min(self.scroll_bottom, self.cursor_row)
                else:
                    self.cursor_row = row - 1
                self._clamp_cursor()
        else:
            if final == "h":
                if params and params[0] == 6:
                    self.origin_mode = True
                elif params and params[0] == 25:
                    self.cursor_visible = True
            elif final == "l":
                if params and params[0] == 6:
                    self.origin_mode = False
                elif params and params[0] == 25:
                    self.cursor_visible = False

    # =================================================================
    # ESC 序列处理 (非 CSI)
    # =================================================================

    def _dispatch_escape(self, ch: str):
        if ch == "c":
            self.clear_screen()
            self.cursor_row = 0
            self.cursor_col = 0
            self.rendition.reset()
            self.scroll_top = 0
            self.scroll_bottom = self.height - 1
            self._saved_cursor = None
        elif ch == "D":
            if self.cursor_row >= self.scroll_bottom:
                self.scroll_up(1)
            else:
                self.cursor_row += 1
        elif ch == "M":
            if self.cursor_row <= self.scroll_top:
                self.scroll_down(1)
            else:
                self.cursor_row -= 1
        elif ch == "E":
            self.cursor_col = 0
            self._handle_newline()
        elif ch == "7":
            self.save_cursor()
        elif ch == "8":
            self.restore_cursor()

    # =================================================================
    # 字节流/数据流输入接口 (支持 bytes, bytearray, 分块读取)
    # =================================================================

    def feed_bytes(self, data: Union[bytes, bytearray, memoryview], final: bool = True):
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = bytes(data)
        else:
            raise TypeError(f"feed_bytes expects bytes/bytearray/memoryview, got {type(data).__name__}")
        text = self._utf8_decoder.decode(data, final=final)
        if text:
            self.feed(text)

    def feed_stream(self, stream: BinaryIO, chunk_size: int = 8192):
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                self.feed_bytes(b"", final=True)
                break
            self.feed_bytes(chunk, final=False)

    def reset_decoder(self):
        self._utf8_decoder.reset()

    # =================================================================
    # 保存/恢复光标 (DECSC / DECRC)
    # =================================================================

    def save_cursor(self):
        self._saved_cursor = {
            "row": self.cursor_row,
            "col": self.cursor_col,
            "fg": self.rendition.fg,
            "bg": self.rendition.bg,
            "fg_rgb": self.rendition.fg_rgb,
            "bg_rgb": self.rendition.bg_rgb,
            "style": self.rendition.style,
            "origin_mode": self.origin_mode,
            "auto_wrap": self.auto_wrap,
        }

    def restore_cursor(self):
        if self._saved_cursor is None:
            self.cursor_row = 0
            self.cursor_col = 0
            return
        s = self._saved_cursor
        self.cursor_row = s["row"]
        self.cursor_col = s["col"]
        self.rendition.fg = s["fg"]
        self.rendition.bg = s["bg"]
        self.rendition.fg_rgb = s["fg_rgb"]
        self.rendition.bg_rgb = s["bg_rgb"]
        self.rendition.style = s["style"]
        self.origin_mode = s.get("origin_mode", False)
        self.auto_wrap = s.get("auto_wrap", True)
        self._clamp_cursor()

    # =================================================================
    # 插入/删除 字符 (ICH / DCH)
    # =================================================================

    def insert_chars(self, n: int = 1):
        if n <= 0:
            n = 1
        if not (0 <= self.cursor_row < self.height):
            return
        row = self.grid[self.cursor_row]
        start = self.cursor_col
        end = min(start + n, self.width)
        shift = end - start
        if shift <= 0:
            return
        for c in range(self.width - 1, end - 1, -1):
            row[c].copy_from(row[c - shift])
        for c in range(start, end):
            row[c].reset()

    def delete_chars(self, n: int = 1):
        if n <= 0:
            n = 1
        if not (0 <= self.cursor_row < self.height):
            return
        row = self.grid[self.cursor_row]
        start = self.cursor_col
        move_end = min(start + n, self.width)
        shift = move_end - start
        if shift <= 0:
            return
        for c in range(start, self.width - shift):
            row[c].copy_from(row[c + shift])
        for c in range(self.width - shift, self.width):
            row[c].reset()

    # =================================================================
    # 插入/删除 行 (IL / DL) —— 仅在滚动区域内生效
    # =================================================================

    def insert_lines(self, n: int = 1):
        if n <= 0:
            n = 1
        if not (self.scroll_top <= self.cursor_row <= self.scroll_bottom):
            return
        n = min(n, self.scroll_bottom - self.cursor_row + 1)
        for _ in range(n):
            for r in range(self.scroll_bottom, self.cursor_row, -1):
                for c in range(self.width):
                    self.grid[r][c].copy_from(self.grid[r - 1][c])
            for c in range(self.width):
                self.grid[self.cursor_row][c].reset()

    def delete_lines(self, n: int = 1):
        if n <= 0:
            n = 1
        if not (self.scroll_top <= self.cursor_row <= self.scroll_bottom):
            return
        n = min(n, self.scroll_bottom - self.cursor_row + 1)
        for _ in range(n):
            for r in range(self.cursor_row, self.scroll_bottom):
                for c in range(self.width):
                    self.grid[r][c].copy_from(self.grid[r + 1][c])
            for c in range(self.width):
                self.grid[self.scroll_bottom][c].reset()

    # =================================================================
    # 主解析循环 —— 状态机
    # =================================================================

    def feed(self, data: str):
        for ch in data:
            self._feed_char(ch)

    def _feed_char(self, ch: str):
        state = self._parse_state

        if state == ParseState.GROUND:
            if ch == "\x1b":
                self._parse_state = ParseState.ESCAPE
                self._csi_params = []
                self._csi_param_buf = ""
                self._csi_intermediates = []
                self._osc_buf = ""
            else:
                self.put_char(ch)

        elif state == ParseState.ESCAPE:
            if ch == "[":
                self._parse_state = ParseState.CSI_ENTRY
            elif ch == "]":
                self._parse_state = ParseState.OSC_STRING
            elif " " <= ch <= "/":
                self._csi_intermediates.append(ch)
                self._parse_state = ParseState.CSI_INTERMEDIATE
            elif 0x30 <= ord(ch) <= 0x7E:
                self._dispatch_escape(ch)
                self._parse_state = ParseState.GROUND
            else:
                self._dispatch_escape(ch)
                self._parse_state = ParseState.GROUND

        elif state == ParseState.CSI_ENTRY:
            if "0" <= ch <= "9" or ch == ";":
                self._csi_param_buf += ch
                self._parse_state = ParseState.CSI_PARAM
            elif " " <= ch <= "/":
                self._csi_intermediates.append(ch)
                self._parse_state = ParseState.CSI_INTERMEDIATE
            elif "<" <= ch <= "?":
                self._csi_intermediates.append(ch)
                self._parse_state = ParseState.CSI_PARAM
            elif 0x40 <= ord(ch) <= 0x7E:
                self._dispatch_csi(ch)
                self._parse_state = ParseState.GROUND
            elif ch == "\x1b":
                self._parse_state = ParseState.ESCAPE
                self._csi_params = []
                self._csi_param_buf = ""
                self._csi_intermediates = []
                self._osc_buf = ""
            else:
                self._parse_state = ParseState.GROUND

        elif state == ParseState.CSI_PARAM:
            if "0" <= ch <= "9" or ch == ";":
                self._csi_param_buf += ch
            elif " " <= ch <= "/":
                self._csi_intermediates.append(ch)
                self._parse_state = ParseState.CSI_INTERMEDIATE
            elif 0x40 <= ord(ch) <= 0x7E:
                self._dispatch_csi(ch)
                self._parse_state = ParseState.GROUND
            elif ch == "\x1b":
                self._parse_state = ParseState.ESCAPE
                self._csi_params = []
                self._csi_param_buf = ""
                self._csi_intermediates = []
                self._osc_buf = ""
            else:
                self._parse_state = ParseState.GROUND

        elif state == ParseState.CSI_INTERMEDIATE:
            if " " <= ch <= "/":
                self._csi_intermediates.append(ch)
            elif 0x40 <= ord(ch) <= 0x7E:
                self._dispatch_csi(ch)
                self._parse_state = ParseState.GROUND
            elif ch == "\x1b":
                self._parse_state = ParseState.ESCAPE
                self._csi_params = []
                self._csi_param_buf = ""
                self._csi_intermediates = []
                self._osc_buf = ""
            else:
                self._parse_state = ParseState.GROUND

        elif state == ParseState.OSC_STRING:
            if ch == "\x07" or (ch == "\\" and self._osc_buf.endswith("\x1b")):
                self._parse_state = ParseState.GROUND
                self._osc_buf = ""
            elif ch == "\x1b":
                self._osc_buf += ch
            else:
                self._osc_buf += ch

    # =================================================================
    # 渲染输出
    # =================================================================

    def get_line_text(self, row: int, rstrip: bool = True) -> str:
        if not (0 <= row < self.height):
            return ""
        chars = [cell.char for cell in self.grid[row]]
        line = "".join(chars)
        if rstrip:
            line = line.rstrip()
        return line

    def get_screen_text(self, rstrip_lines: bool = True, rstrip_trailing: bool = True) -> str:
        lines = [self.get_line_text(r, rstrip_lines) for r in range(self.height)]
        if rstrip_trailing:
            while lines and lines[-1] == "":
                lines.pop()
        return "\n".join(lines)

    def _sgr_start(self, cell: Cell) -> str:
        parts = []
        if cell.style & STYLE_BOLD:
            parts.append("1")
        if cell.style & STYLE_DIM:
            parts.append("2")
        if cell.style & STYLE_ITALIC:
            parts.append("3")
        if cell.style & STYLE_UNDERLINE:
            parts.append("4")
        if cell.style & STYLE_BLINK:
            parts.append("5")
        if cell.style & STYLE_REVERSE:
            parts.append("7")
        if cell.style & STYLE_STRIKETHROUGH:
            parts.append("9")

        if cell.fg_rgb is not None:
            r, g, b = cell.fg_rgb
            parts.append(f"38;2;{r};{g};{b}")
        elif cell.fg != COLOR_DEFAULT:
            if cell.fg < 8:
                parts.append(str(30 + cell.fg))
            else:
                parts.append(str(90 + cell.fg - 8))

        if cell.bg_rgb is not None:
            r, g, b = cell.bg_rgb
            parts.append(f"48;2;{r};{g};{b}")
        elif cell.bg != COLOR_DEFAULT:
            if cell.bg < 8:
                parts.append(str(40 + cell.bg))
            else:
                parts.append(str(100 + cell.bg - 8))

        if not parts:
            return ""
        return "\x1b[" + ";".join(parts) + "m"

    def render_ansi(self, rstrip_lines: bool = True, rstrip_trailing: bool = True) -> str:
        result = io.StringIO()
        lines = []
        for r in range(self.height):
            line_buf = io.StringIO()
            last_sgr = None
            for c in range(self.width):
                cell = self.grid[r][c]
                cur_sgr = (cell.fg, cell.bg, cell.fg_rgb, cell.bg_rgb, cell.style)
                if cur_sgr != last_sgr:
                    line_buf.write("\x1b[0m")
                    sgr_code = self._sgr_start(cell)
                    line_buf.write(sgr_code)
                    last_sgr = cur_sgr
                line_buf.write(cell.char)
            line_buf.write("\x1b[0m")
            lines.append(line_buf.getvalue())

        if rstrip_lines:
            stripped = []
            for line in lines:
                cleaned = line
                while cleaned.endswith(" ") or cleaned.endswith("\x1b[0m"):
                    if cleaned.endswith("\x1b[0m"):
                        cleaned = cleaned[:-4]
                    elif cleaned.endswith(" "):
                        cleaned = cleaned[:-1]
                    else:
                        break
                stripped.append(cleaned)
            lines = stripped

        if rstrip_trailing:
            while lines and lines[-1] == "":
                lines.pop()

        result.write("\n".join(lines))
        return result.getvalue()

    def render_debug(self) -> str:
        lines = []
        for r in range(self.height):
            row_repr = []
            for c in range(self.width):
                cell = self.grid[r][c]
                if cell.char != " " or cell.style != 0 or cell.fg != COLOR_DEFAULT or cell.bg != COLOR_DEFAULT:
                    row_repr.append(f"[{c}]{repr(cell.char)}")
            if row_repr:
                lines.append(f"R{r}: " + " ".join(row_repr))
        lines.append(f"Cursor: ({self.cursor_row}, {self.cursor_col})")
        lines.append(f"Scroll: [{self.scroll_top}, {self.scroll_bottom}]")
        return "\n".join(lines)

    def get_cell(self, row: int, col: int) -> Optional[Cell]:
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.grid[row][col]
        return None

    def snapshot(self) -> List[List[Cell]]:
        return [[Cell(
            char=c.char, fg=c.fg, bg=c.bg,
            fg_rgb=c.fg_rgb, bg_rgb=c.bg_rgb, style=c.style
        ) for c in row] for row in self.grid]

    # =================================================================
    # JSON 序列化导出
    # =================================================================

    def _cell_to_dict(self, cell: Cell) -> dict:
        d = {"ch": cell.char}
        if cell.fg != COLOR_DEFAULT:
            d["fg"] = cell.fg
        if cell.bg != COLOR_DEFAULT:
            d["bg"] = cell.bg
        if cell.fg_rgb is not None:
            d["fg_rgb"] = list(cell.fg_rgb)
        if cell.bg_rgb is not None:
            d["bg_rgb"] = list(cell.bg_rgb)
        if cell.style != 0:
            d["style"] = cell.style
            style_names = []
            if cell.style & STYLE_BOLD: style_names.append("bold")
            if cell.style & STYLE_DIM: style_names.append("dim")
            if cell.style & STYLE_ITALIC: style_names.append("italic")
            if cell.style & STYLE_UNDERLINE: style_names.append("underline")
            if cell.style & STYLE_BLINK: style_names.append("blink")
            if cell.style & STYLE_REVERSE: style_names.append("reverse")
            if cell.style & STYLE_HIDDEN: style_names.append("hidden")
            if cell.style & STYLE_STRIKETHROUGH: style_names.append("strikethrough")
            if style_names:
                d["style_names"] = style_names
        return d

    def to_dict(self, include_empty: bool = False, rstrip_lines: bool = True,
                rstrip_trailing: bool = True) -> dict:
        rows = []
        last_non_empty = -1
        for r in range(self.height):
            cells = []
            has_content = False
            for c in range(self.width):
                cell = self.grid[r][c]
                is_empty = (
                    cell.char == " " and cell.style == 0 and
                    cell.fg == COLOR_DEFAULT and cell.bg == COLOR_DEFAULT and
                    cell.fg_rgb is None and cell.bg_rgb is None
                )
                if include_empty or not is_empty:
                    cd = self._cell_to_dict(cell)
                    cd["col"] = c
                    cells.append(cd)
                    if not is_empty:
                        has_content = True
            if rstrip_lines:
                while cells and (cells[-1]["ch"] == " " and len(cells[-1]) <= 2):
                    cells.pop()
            row_data = {"row": r, "cells": cells}
            if has_content or not rstrip_trailing:
                rows.append(row_data)
                last_non_empty = r
            elif not rstrip_trailing:
                rows.append(row_data)
        if rstrip_trailing and last_non_empty >= 0:
            rows = [row for row in rows if row["row"] <= last_non_empty]
        return {
            "width": self.width,
            "height": self.height,
            "cursor": {"row": self.cursor_row, "col": self.cursor_col,
                       "visible": self.cursor_visible},
            "scroll_region": {"top": self.scroll_top, "bottom": self.scroll_bottom},
            "mode": {"auto_wrap": self.auto_wrap, "origin_mode": self.origin_mode},
            "rows": rows,
        }

    def to_json(self, indent: Optional[int] = 2, include_empty: bool = False,
                rstrip_lines: bool = True, rstrip_trailing: bool = True,
                ensure_ascii: bool = False) -> str:
        data = self.to_dict(include_empty=include_empty,
                            rstrip_lines=rstrip_lines,
                            rstrip_trailing=rstrip_trailing)
        return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)


# =================================================================
# 便捷函数
# =================================================================

def render_terminal_output(output: str, width: int = 80, height: int = 24,
                           use_ansi: bool = False) -> str:
    vt = VirtualTerminal(width=width, height=height)
    vt.feed(output)
    if use_ansi:
        return vt.render_ansi()
    else:
        return vt.get_screen_text()


def parse_and_snapshot(output: str, width: int = 80, height: int = 24) -> VirtualTerminal:
    vt = VirtualTerminal(width=width, height=height)
    vt.feed(output)
    return vt


# =================================================================
# CLI 命令行入口
# =================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ansi_terminal",
        description="ANSI 终端转义序列渲染引擎：把带 ANSI 码的字节流渲染成纯文本快照或 JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 从文件读取,默认 80x24,输出纯文本
  python ansi_terminal.py -f output.log

  # 从 stdin 管道输入,自定义尺寸,导出 JSON
  curl -s https://example.com | some_cmd | python ansi_terminal.py -W 120 -H 50 --json

  # 导出属性完整的 JSON(含空格单元格)并重定向到文件
  python ansi_terminal.py -f build.log --json --full --output snapshot.json

  # 输出带 ANSI 颜色的文本(保留颜色/加粗等属性)
  python ansi_terminal.py -f colored.txt --ansi
""",
    )
    p.add_argument("-f", "--file", type=str, default=None,
                   help="输入文件路径 (默认或 '-' 时从 stdin 读取)")
    p.add_argument("-W", "--width", type=int, default=80,
                   help="虚拟终端宽度 (列数),默认 80")
    p.add_argument("-H", "--height", type=int, default=24,
                   help="虚拟终端高度 (行数),默认 24")
    p.add_argument("--json", action="store_true",
                   help="输出 JSON 格式 (含每个单元格的属性)")
    p.add_argument("--ansi", action="store_true",
                   help="输出带 ANSI 颜色/加粗属性的文本 (默认纯文本)")
    p.add_argument("--full", action="store_true",
                   help="JSON 输出时包含空格/空单元格 (默认省略)")
    p.add_argument("--no-rstrip", action="store_true",
                   help="不删除行尾空格和空行 (默认会 rstrip)")
    p.add_argument("-o", "--output", type=str, default=None,
                   help="输出文件 (默认 stdout)")
    p.add_argument("--encoding", type=str, default="utf-8",
                   help="输入文件编码,默认 utf-8 (非法字节会用 U+FFFD 替换)")
    return p


def _read_input(args) -> bytes:
    if args.file and args.file != "-":
        with open(args.file, "rb") as f:
            return f.read()
    else:
        return getattr(sys.stdin, "buffer", sys.stdin).read()


def main(argv=None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.width <= 0 or args.height <= 0:
        parser.error("width 和 height 必须是正整数")

    vt = VirtualTerminal(width=args.width, height=args.height)

    try:
        raw = _read_input(args)
    except FileNotFoundError as e:
        print(f"错误: 无法打开文件: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"错误: 读取输入失败: {e}", file=sys.stderr)
        return 2

    try:
        vt.feed_bytes(raw, final=True)
    except Exception as e:
        print(f"错误: 解析输入时异常: {e}", file=sys.stderr)
        return 3

    rstrip = not args.no_rstrip
    if args.json:
        out_text = vt.to_json(
            include_empty=args.full,
            rstrip_lines=rstrip,
            rstrip_trailing=rstrip,
            ensure_ascii=False,
        )
    elif args.ansi:
        out_text = vt.render_ansi(rstrip_lines=rstrip, rstrip_trailing=rstrip)
    else:
        out_text = vt.get_screen_text(rstrip_lines=rstrip, rstrip_trailing=rstrip)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out_text)
                if not out_text.endswith("\n"):
                    f.write("\n")
        except OSError as e:
            print(f"错误: 写入输出失败: {e}", file=sys.stderr)
            return 4
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        sys.stdout.write(out_text)
        if not out_text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main())
