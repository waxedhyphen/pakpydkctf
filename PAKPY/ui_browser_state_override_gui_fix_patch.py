"""Small GUI follow-up for the UI state override editor.

Tk Text widgets ignore edits while disabled.  The override editor therefore has to
re-enable its text box before replacing the displayed value when selection changes
from a non-text placement back to an EditText node.
"""
from __future__ import annotations

import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as override_patch


_INSTALLED = False


def sync_override_controls(window):
    if not hasattr(window, "override_visibility_var"):
        return
    node = override_patch._selected_inspector_node(window)
    overrides = getattr(window.owner, "_ui_state_overrides", {})
    override = override_patch.normalize_override(overrides.get(node.path, {})) if node else {}

    if "visible" not in override:
        window.override_visibility_var.set("Original")
    else:
        window.override_visibility_var.set(
            "Sichtbar" if override["visible"] else "Versteckt"
        )
    window.override_frame_var.set(str(override.get("sprite_frame", 0)))
    window.override_text_enabled_var.set("text" in override)
    window.override_html_var.set(bool(override.get("html", False)))
    window.override_disable_filters_var.set(bool(override.get("disable_filters", False)))
    window.override_disable_blend_var.set(bool(override.get("disable_blend", False)))

    window.override_text.configure(state="normal")
    window.override_text.delete("1.0", "end")
    if node is not None:
        value = override.get("text", node.metadata.get("display_text", ""))
        window.override_text.insert("1.0", str(value))

    frame_state = "normal" if node is not None and node.kind == "MovieClip" else "disabled"
    text_state = "normal" if node is not None and node.kind == "EditText" else "disabled"
    window.override_frame_spin.configure(state=frame_state)
    window.override_text.configure(state=text_state)
    window.override_text_toggle.configure(state=text_state)
    window.override_html_toggle.configure(state=text_state)

    if node is None:
        window.override_status_var.set("Keine Instanz ausgewählt")
    elif override:
        window.override_status_var.set(f"Aktiver Override: {node.path}")
    else:
        window.override_status_var.set(f"Originalzustand: {node.path}")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    override_patch._sync_override_controls = sync_override_controls
    inspector.StateInspectorWindow._sync_override_controls = sync_override_controls
