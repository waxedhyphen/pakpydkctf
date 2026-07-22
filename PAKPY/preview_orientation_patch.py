"""Install display-only orientation corrections for zlib previews.

The decoded zlib-backed image data uses the opposite vertical image origin from the
human-facing Tk/Pillow previews. The old workaround rotated previews by 180 degrees;
that fixed top/bottom but also mirrored left/right. The correct display transform is
therefore a vertical flip only.

Raw TXTR/SWF bytes, replacement data, PNG import and repacking remain unchanged.
"""
from __future__ import annotations

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

import txtrpreview
import ui_browser


_INSTALLED = False


def needs_txtr_preview_rotation(info):
    """Return whether a decoded TXTR needs the zlib preview orientation fix."""
    return str((info or {}).get("gpu_codec", "")).strip().lower() == "zlib"


def is_zlib_swf(raw):
    """CWS is the zlib-compressed SWF form used by the affected UI movies."""
    return isinstance(raw, (bytes, bytearray, memoryview)) and bytes(raw[:3]) == b"CWS"


def rotate_preview_image(image):
    """Apply the historical preview helper as a vertical flip, not a 180° turn.

    The function name is retained because the GFXL patch imports it. Returning a
    top/bottom flip also applies the missing horizontal correction relative to the
    previous 180-degree workaround.
    """
    if image is None or PILImage is None:
        return image
    transpose = getattr(getattr(PILImage, "Transpose", PILImage), "FLIP_TOP_BOTTOM")
    return image.transpose(transpose)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_txtr_render = txtrpreview.TxtrPreview._render_current

    def _render_current(self):
        original_txtr_render(self)
        if self.image is None or not needs_txtr_preview_rotation(self.info):
            return
        self.image = rotate_preview_image(self.image)
        self._draw_embedded_image()
        self._update_big_window()
        self._set_buttons()
        try:
            status = self.status_var.get()
            note = "Anzeige: vertikal gespiegelt"
            if note not in status:
                self.status_var.set(f"{status} | {note}" if status else note)
        except Exception:
            pass

    txtrpreview.TxtrPreview._render_current = _render_current

    original_parse_swf = ui_browser.parse_swf_movie

    def parse_swf_movie(raw):
        movie = original_parse_swf(raw)
        # Keep the old attribute for compatibility with the already-installed
        # GFXL patch; its meaning is now "apply preview orientation correction".
        movie.preview_rotate_180 = is_zlib_swf(raw)
        return movie

    ui_browser.parse_swf_movie = parse_swf_movie

    original_ui_render = ui_browser.UIRenderer.render

    def render(self, frame):
        image, stats = original_ui_render(self, frame)
        if getattr(self.movie, "preview_rotate_180", False):
            image = rotate_preview_image(image)
        return image, stats

    ui_browser.UIRenderer.render = render
