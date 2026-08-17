from __future__ import annotations

import logging
import os

from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

class TableRendererMixin(MaxBaseMixin):
    """Mixin for rendering Markdown tables."""

    @staticmethod
    def _convert_markdown_tables(text: str) -> str:
        """Convert markdown tables to MAX-compatible pipe format with monospace.

        MAX does not support markdown table rendering. This converts:
          | Col1 | Col2 |
          |------|------|
          | v1   | v2   |
        Into a monospace code block with aligned columns, which renders
        correctly on MAX.
        """
        import re

        # Match markdown tables: find blocks of pipe-delimited rows
        # that contain at least one separator row (|---|).
        # Strategy: find consecutive lines starting with |,
        # where at least one is a separator.
        lines = text.split('\n')
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if this line starts a table (starts with |)
            if re.match(r'^\|.+\|', line):
                # Collect consecutive pipe lines
                table_lines = []
                has_separator = False
                while i < len(lines) and re.match(r'^\|.+\|', lines[i]):
                    current = lines[i]
                    table_lines.append(current)
                    if re.match(r'^\|[\s\-:|]+\|$', current):
                        has_separator = True
                    i += 1

                if has_separator and len(table_lines) >= 2:
                    # This is a table — convert it
                    converted = TableRendererMixin._render_table(table_lines)
                    result_lines.append(converted)
                else:
                    # Not a valid table — keep as-is
                    result_lines.extend(table_lines)
            else:
                result_lines.append(line)
                i += 1

        return '\n'.join(result_lines)

    @staticmethod
    def _parse_table_rows(lines: list) -> tuple:
        """Parse pipe-delimited table lines into rows, handling embedded pipes.

        Strategy: use the first data row (typically the header) to determine
        the canonical column count, then rejoin any extra splits so all data
        rows match the header width.
        Returns (rows: list[list[str]], ncols: int).
        """

        raw_rows = []
        for line in lines:
            if not line.strip():
                continue
            if all(c in '|-: ' for c in line):
                continue
            # Split on | that are actual column separators
            cells_raw = [c.strip() for c in line.strip('|').split('|')]
            raw_rows.append(cells_raw)

        if not raw_rows:
            return [], 0

        # Canonical column count = first row's count (should be header)
        ncols = len(raw_rows[0])
        if ncols == 0:
            return [], 0

        # Normalize: if a row has MORE cells than ncols, merge extras into the last cell
        # If a row has FEWER, pad with empty strings
        rows = []
        for r in raw_rows:
            if len(r) == ncols:
                rows.append(r)
            elif len(r) > ncols:
                # Merge excess cells into the last column
                merged = r[:ncols - 1] + [' | '.join(r[ncols - 1:])]
                rows.append(merged)
            else:
                # Pad with empty strings if fewer
                rows.append(r + [''] * (ncols - len(r)))

        return rows, ncols

    @staticmethod
    def _sanitize_cell(text: str) -> str:
        """Sanitize cell content: escape HTML brackets, replace problematic chars."""
        t = text.replace('<', '\u2039').replace('>', '\u203a')
        t = t.replace('|', '\u23d0')  # broken bar as visible pipe alternative
        t = t.replace('\n', ' ')
        t = t.replace('\r', '')
        return t

    @staticmethod
    def _truncate_cell(text: str, max_len: int = 38) -> str:
        """Truncate text to max_len with … indicator."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 1] + '…'

    @staticmethod
    def _insert_soft_breaks(text: str, max_span: int = 15) -> str:
        """Insert ZWSP (zero-width space) in long strings without spaces.

        Browsers/MAX can break lines at ZWSP points, solving the overflow
        of URLs, JSON, long numbers without actual truncation.
        Strings that already contain whitespace are returned as-is.
        """
        if ' ' in text or '\t' in text:
            return text
        # Don't bother with short strings
        if len(text) <= max_span:
            return text
        # Insert ZWSP every max_span characters
        parts = []
        for i in range(0, len(text), max_span):
            parts.append(text[i:i + max_span])
        return '\u200b'.join(parts)

    @staticmethod
    def _render_table(lines: list) -> str:
        """Render a list of pipe-delimited lines as a monospace table."""
        rows, ncols = TableRendererMixin._parse_table_rows(lines)
        if not rows or ncols == 0:
            return '\n'.join(lines)

        # Calculate column widths (cap at 38 chars for mobile)
        widths = [3] * ncols  # minimum width
        for row in rows:
            for i, cell in enumerate(row):
                if i < ncols:
                    safe = TableRendererMixin._sanitize_cell(cell)
                    widths[i] = max(widths[i], min(len(safe), 38))

        # Build formatted table.
        # MAX supports inline `code` for monospace. Each line is its own
        # inline code span — no newlines inside, so they render correctly.
        sep = '-' * (sum(widths) + 3 * ncols + 1)

        result = ['`' + sep + '`']
        for row in rows:
            padded = []
            for i in range(ncols):
                cell = row[i] if i < len(row) else ''
                safe = TableRendererMixin._sanitize_cell(cell)
                # Insert soft breaks for long unbroken strings instead of truncating
                display = TableRendererMixin._insert_soft_breaks(safe, 15)
                padded.append(display.ljust(widths[i]))
            result.append('`| ' + ' | '.join(padded) + ' |`')
        result.append('`' + sep + '`')
        return '\n'.join(result)

    async def _render_table_as_image(self, table_lines: list) -> str | None:
        """Render pipe-delimited table lines as a clean PNG and upload to MAX.

        Returns upload token on success, None on failure.
        """
        # ── Parse rows ────────────────────────────────────────────────
        rows, ncols = TableRendererMixin._parse_table_rows(table_lines)
        if not rows or ncols == 0:
            return None

        def _prepare_cell(val: str) -> tuple:
            """Convert raw cell text to (display_text, color).

            Emoji → Unicode symbols that DejaVu Sans renders properly.
            Markdown styling (**bold**, *italic*, `code`) is preserved
            and rendered at draw time via segment parser.
            Status cells get semantic colors.

            NOTE: MAX may append U+FE0F (emoji VS-16) to emoji chars.
            Normalize by stripping variation selectors first.
            """
            color = None
            text = val.strip()
            # Strip variation selectors so "⚠️" matches as "⚠"
            text = text.replace("\ufe0f", "").replace("\ufe0e", "")

            # Map emoji → clear Unicode symbols with semantic colors
            if "✅" in text:
                text = text.replace("✅", "✓").strip()
                color = "#16a34a"  # green-600
            elif "❌" in text:
                text = text.replace("❌", "✗").strip()
                color = "#dc2626"  # red-600
            elif "⚠" in text:
                text = text.replace("⚠", "⚠").strip()
                color = "#ea580c"  # orange-600
            elif "⏳" in text or "⌛" in text:
                is_scheduled = "schedule" in text.lower()
                text = text.replace("⏳", "▶" if is_scheduled else "◷") \
                           .replace("⌛", "▶" if is_scheduled else "◷").strip()
                color = "#3b82f6" if is_scheduled else "#ca8a04"
            elif "🔴" in text:
                text = text.replace("🔴", "●").strip()
                color = "#dc2626"
            elif "🟢" in text:
                text = text.replace("🟢", "●").strip()
                color = "#16a34a"
            elif "🟡" in text:
                text = text.replace("🟡", "●").strip()
                color = "#ca8a04"

            # Cleanup stray text markers
            text = text.replace("ℹ", "").replace("📊", "")
            text = text.replace("[OK]", "✓").replace("[ERR]", "✗")
            text = text.replace("[WARN]", "⚠").replace("[WAIT]", "◷")
            text = text.replace("[SCHED]", "▶")
            text = text.replace("[CRIT]", "●").replace("[GOOD]", "●").replace("[MID]", "●")

            return text.strip(), color

        cells_info = [[_prepare_cell(c) for c in row] for row in rows]

        try:
            from PIL import Image, ImageDraw, ImageFont
            from wcwidth import wcswidth
        except ImportError:
            logger.warning("MAX: Pillow not installed, cannot render table as image")
            return None

        # ── Layout ────────────────────────────────────────────────────
        CELL_PAD_X = 22
        CELL_PAD_Y = 14
        LINE_WIDTH = 2
        FONT_SIZE = 18
        HEADER_FONT_SIZE = 20

        # ── Font resolution: try multiple locations ──
        # 1) Linux standard path (Debian/Ubuntu dejavu-fonts package)
        # 2) matplotlib-bundled DejaVu (lazy — avoids ImportError if absent)
        # 3) Windows system fonts (Segoe UI + Consolas, ship with Windows)
        # 4) Pillow built-in default (no Cyrillic support)
        _font_candidates = [
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
            None,  # placeholder for lazy matplotlib path
            ("C:\\Windows\\Fonts\\segoeui.ttf",
             "C:\\Windows\\Fonts\\segoeuib.ttf",
             "C:\\Windows\\Fonts\\segoeuii.ttf",
             "C:\\Windows\\Fonts\\consola.ttf"),
        ]
        font = font_bold = font_italic = font_code = None
        for candidate in _font_candidates:
            try:
                if candidate is None:
                    # Lazy: only try matplotlib import now
                    import matplotlib as _mpl
                    _mpl_dir = os.path.dirname(_mpl.__file__)
                    candidate = (
                        os.path.join(_mpl_dir, "mpl-data", "fonts", "ttf", "DejaVuSans.ttf"),
                        os.path.join(_mpl_dir, "mpl-data", "fonts", "ttf", "DejaVuSans-Bold.ttf"),
                        os.path.join(_mpl_dir, "mpl-data", "fonts", "ttf", "DejaVuSerif.ttf"),
                        os.path.join(_mpl_dir, "mpl-data", "fonts", "ttf", "DejaVuSansMono.ttf"),
                    )
                font = ImageFont.truetype(candidate[0], FONT_SIZE)
                font_bold = ImageFont.truetype(candidate[1], HEADER_FONT_SIZE)
                font_italic = ImageFont.truetype(candidate[2], FONT_SIZE)
                font_code = ImageFont.truetype(candidate[3], FONT_SIZE - 2)
                break  # all four loaded successfully
            except (OSError, ImportError):
                continue
        if font is None:
            font = ImageFont.load_default()
            font_bold = font
            font_italic = font
            font_code = font

        from PIL import ImageDraw as _ImageDraw
        _tmp_img = Image.new("RGB", (1, 1))
        _tmp_draw = _ImageDraw.Draw(_tmp_img)

        import re as _md_re

        def _strip_md_plain(text: str) -> str:
            """Strip markdown formatting, return plain text for measurement."""
            t = _md_re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            t = _md_re.sub(r'\*(.+?)\*', r'\1', t)
            t = _md_re.sub(r'`(.+?)`', r'\1', t)
            return t

        def _parse_md_segments(text: str) -> list:
            """Parse inline markdown into [(text, style_key), ...].
            style_key: 'bold', 'italic', 'code', or 'plain'.
            """
            pattern = r'(\*\*.+?\*\*|`.+?`|(?<!\*)\*.+?\*(?!\*))'
            parts = _md_re.split(pattern, text)
            result = []
            for p in parts:
                if not p:
                    continue
                if p.startswith('**') and p.endswith('**'):
                    result.append((p[2:-2], 'bold'))
                elif p.startswith('*') and p.endswith('*') and not p.startswith('**'):
                    result.append((p[1:-1], 'italic'))
                elif p.startswith('`') and p.endswith('`'):
                    result.append((p[1:-1], 'code'))
                else:
                    result.append((p, 'plain'))
            return result

        def _seg_font(style_key: str):
            """Return the font for a given style key."""
            if style_key == 'bold':
                return font_bold
            elif style_key == 'italic':
                return font_italic
            elif style_key == 'code':
                return font_code
            return font

        def _seg_width(text: str, style_key: str) -> int:
            """Measure pixel width of a styled segment."""
            return int(_tmp_draw.textlength(text, font=_seg_font(style_key)))

        def _tokenize_md(text: str) -> list:
            """Split markdown text into [(word, style_key), ...] tokens."""
            tokens = []
            for seg_text, style_key in _parse_md_segments(text):
                for i, w in enumerate(seg_text.split()):
                    tokens.append((w, style_key))
            return tokens

        def _break_word(word: str, sty: str, avail: int) -> list:
            """Break a single word into character-level token lines when it overflows avail."""
            lines = []
            cur = []
            cur_w = 0
            for ch in word:
                cw = _seg_width(ch, sty)
                if cur_w + cw > avail and cur:
                    lines.append(cur)
                    cur = []
                    cur_w = 0
                cur.append((ch, sty))
                cur_w += cw
            if cur:
                lines.append(cur)
            return lines

        def _wrap_md_text(cell_text: str, max_px_width: int) -> list:
            """Soft-wrap markdown text by tokens.
            Returns list of token lists: [[(word, style), ...], ...]
            """
            tokens = _tokenize_md(cell_text)
            if not tokens:
                return [[('', 'plain')]]
            avail = max(10, max_px_width - CELL_PAD_X * 2)
            lines = []
            cur = []
            cur_w = 0
            for word, sty in tokens:
                ww = _seg_width(word, sty)
                if not cur:
                    if ww > avail:
                        broken = _break_word(word, sty, avail)
                        lines.extend(broken[:-1])
                        cur = broken[-1]
                        cur_w = sum(_seg_width(ch, sty) for ch, _ in broken[-1])
                    else:
                        cur = [(word, sty)]
                        cur_w = ww
                elif cur_w + _seg_width(' ', 'plain') + ww <= avail:
                    cur.append((word, sty))
                    cur_w += _seg_width(' ', 'plain') + ww
                else:
                    lines.append(cur)
                    if ww > avail:
                        broken = _break_word(word, sty, avail)
                        lines.extend(broken[:-1])
                        cur = broken[-1]
                        cur_w = sum(_seg_width(ch, sty) for ch, _ in broken[-1])
                    else:
                        cur = [(word, sty)]
                        cur_w = ww
            if cur:
                lines.append(cur)
            return lines if lines else [[('', 'plain')]]

        def _text_px_width(text: str, font: ImageFont.FreeTypeFont) -> int:
            """Get pixel width of text using draw.textlength (Pillow 8+).
            Falls back to wcswidth*0.6 only as last resort."""
            try:
                # Create a temporary draw to measure accurately
                from PIL import ImageDraw
                tmp_img = Image.new("RGB", (1, 1))
                tmp_draw = ImageDraw.Draw(tmp_img)
                return int(tmp_draw.textlength(text, font=font))
            except Exception:
                try:
                    raw_width = wcswidth(text)
                    return int(raw_width * 0.6)
                except Exception:
                    bbox = font.getbbox(text)
                    return bbox[2] - bbox[0]

        def _get_line_height(this_font: ImageFont.FreeTypeFont) -> int:
            """Get single line height in pixels for a font."""
            try:
                bbox = this_font.getbbox("Ag")
                return bbox[3] - bbox[1]
            except Exception:
                return 18

        line_h = _get_line_height(font)
        line_h_bold = _get_line_height(font_bold)

        # Measure each column width by its widest text in pixels.
        # Header → font_bold, data → font (regular). Cap at 300px.
        data_rows = cells_info[1:]
        header = cells_info[0]

        px_widths = []
        for ci in range(ncols):
            max_px = 0
            for ri, row in enumerate(cells_info):
                if ci < len(row):
                    cell_text = row[ci][0]
                    plain_text = _strip_md_plain(cell_text)
                    this_font = font_bold if ri == 0 else font
                    txt_w = int(_tmp_draw.textlength(plain_text, font=this_font))
                    max_px = max(max_px, txt_w)
            col_w = min(max_px + CELL_PAD_X * 2 + 5, 400)
            px_widths.append(col_w)
        # Cap total width at 1200px for mobile retina
        total_w = sum(px_widths) + LINE_WIDTH * (ncols + 1)
        if total_w > 1200:
            scale = 1200 / total_w
            px_widths = [max(w, int(w * scale)) for i, w in enumerate(px_widths)]
            total_w = sum(px_widths) + LINE_WIDTH * (ncols + 1)

        # Calculate row heights with soft-wrap (multi-line support)
        # Also wrap header — it can have long text too

        # Pre-compute wrapped lines for header
        hdr_wrapped = []
        hdr_max_l = 1
        for ci in range(ncols):
            cell_text = header[ci][0] if ci < len(header) else ""
            col_w = px_widths[ci] if ci < len(px_widths) else 100
            wrapped = _wrap_md_text(cell_text, col_w)
            hdr_wrapped.append(wrapped)
            hdr_max_l = max(hdr_max_l, len(wrapped))

        header_h = int(CELL_PAD_Y * 2 + line_h_bold * hdr_max_l)

        # Pre-compute wrapped lines for each data row cell
        wrapped_data = []  # list of lists of lists: [row_index][col_index] = [line_str, ...]
        row_max_lines = []
        for row in data_rows:
            row_wrapped = []
            max_l = 1
            for ci in range(ncols):
                cell_text = row[ci][0] if ci < len(row) else ""
                # Use the column's pixel width for wrapping
                col_w = px_widths[ci] if ci < len(px_widths) else 100
                wrapped = _wrap_md_text(cell_text, col_w)
                row_wrapped.append(wrapped)
                max_l = max(max_l, len(wrapped))
            wrapped_data.append(row_wrapped)
            row_max_lines.append(max_l)

        # Row heights: line count + padding
        row_heights = [int(CELL_PAD_Y * 2 + line_h * ml) for ml in row_max_lines]

        img_h = int(header_h + LINE_WIDTH + sum(row_heights) + LINE_WIDTH + 6)

        # ── Draw ──────────────────────────────────────────────────────
        img = Image.new("RGB", (total_w, img_h), "#ffffff")
        draw = ImageDraw.Draw(img)

        # Color palette
        HDR_BG = "#1e293b"       # slate-800
        HDR_TEXT = "#ffffff"
        ROW_EVEN = "#ffffff"
        ROW_ODD = "#f1f5f9"      # slate-100
        BORDER = "#94a3b8"       # slate-400
        SEP = "#e2e8f0"          # slate-200
        TEXT_COLOR = "#0f172a"   # slate-900

        y = 0

        # --- Header row (multi-line markdown) ---
        draw.rectangle([(0, y), (total_w, y + header_h)], fill=HDR_BG)
        cx = LINE_WIDTH
        for ci in range(ncols):
            wrapped_token_lines = hdr_wrapped[ci]
            nlines = len(wrapped_token_lines)
            th = line_h_bold * nlines
            ty = y + int((header_h - th) / 2)
            for li, token_line in enumerate(wrapped_token_lines):
                sx = cx + CELL_PAD_X
                for idx, (word, sty) in enumerate(token_line):
                    f = _seg_font(sty)
                    draw.text((sx, ty + line_h_bold * li), word, font=f, fill=HDR_TEXT)
                    if idx < len(token_line) - 1:
                        sx += draw.textlength(word + ' ', font=f)
                    else:
                        sx += draw.textlength(word, font=f)
            # Vertical divider
            draw.line([(cx, y), (cx, y + header_h)], fill=BORDER, width=LINE_WIDTH)
            cx += px_widths[ci] + LINE_WIDTH
        # Right border
        draw.line([(cx, y), (cx, y + header_h)], fill=BORDER, width=LINE_WIDTH)
        y += header_h

        # Header-bottom separator
        draw.line([(0, y), (total_w, y)], fill=BORDER, width=LINE_WIDTH)

        # --- Data rows (multi-line markdown) ---
        for ri, row in enumerate(data_rows):
            row_h = row_heights[ri]
            bg = ROW_EVEN if ri % 2 == 0 else ROW_ODD
            draw.rectangle([(0, y), (total_w, y + row_h)], fill=bg)
            cx = LINE_WIDTH
            for ci in range(ncols):
                cell_text, cell_color = row[ci] if ci < len(row) else ("", None)
                fill_color = cell_color or TEXT_COLOR
                wrapped_token_lines = wrapped_data[ri][ci]
                n_lines = len(wrapped_token_lines)
                total_text_h = line_h * n_lines
                text_y_offset = y + int((row_h - total_text_h) / 2)
                for li, token_line in enumerate(wrapped_token_lines):
                    sx = cx + CELL_PAD_X
                    for idx, (word, sty) in enumerate(token_line):
                        f = _seg_font(sty)
                        draw.text((sx, text_y_offset + line_h * li), word, font=f, fill=fill_color)
                        if idx < len(token_line) - 1:
                            sx += draw.textlength(word + ' ', font=f)
                        else:
                            sx += draw.textlength(word, font=f)
                # Vertical divider
                draw.line(
                    [(cx, y), (cx, y + row_h)], fill=SEP, width=1,
                )
                cx += px_widths[ci] + LINE_WIDTH
            # Right border
            draw.line([(cx, y), (cx, y + row_h)], fill=BORDER, width=LINE_WIDTH)
            if ri != len(data_rows) - 1:
                draw.line(
                    [(0, y + row_h), (total_w, y + row_h)], fill=SEP, width=1,
                )
            y += row_h

        # Bottom border
        draw.line([(0, y), (total_w, y)], fill=BORDER, width=LINE_WIDTH)

        # ── Save & upload ─────────────────────────────────────────────
        import hashlib
        digest = hashlib.md5(str(table_lines).encode(), usedforsecurity=False).hexdigest()[:12]
        out_path = self._table_image_dir / f"table_{digest}.png"
        img.save(out_path, "PNG")

        token = await self._upload(str(out_path), "image")
        return token
