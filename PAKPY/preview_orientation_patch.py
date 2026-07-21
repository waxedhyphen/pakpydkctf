"""Install display-only 180-degree orientation corrections for zlib previews.

The underlying TXTR and SWF decoders keep their native byte/layout orientation so
exports, replacement and repacking remain unchanged. Only viewer-owned PIL images
are rotated.
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
    """Return whether a decoded TXTR should be rotated for human-facing preview."""
    return str((info or {}).get("gpu_codec", "")).strip().lower() == "zlib"


def is_zlib_swf(raw):
    """CWS is the zlib-compressed SWF form used by the affected UI movies."""
    return isinstance(raw, (bytes, bytearray, memoryview)) and bytes(raw[:3]) == b"CWS"


def rotate_preview_image(image):
    """Rotate a PIL image without changing its dimensions or resampling pixels."""
    if image is None or PILImage is None:
        return image
    transpose = getattr(getattr(PILImage, "Transpose", PILImage), "ROTATE_180")
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
            note = "Anzeige: 180° gedreht"
            if note not in status:
                self.status_var.set(f"{status} | {note}" if status else note)
        except Exception:
            pass

    txtrpreview.TxtrPreview._render_current = _render_current

    original_parse_swf = ui_browser.parse_swf_movie

    def parse_swf_movie(raw):
        movie = original_parse_swf(raw)
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
