"""Multiline and explicitly confirmed UI for variable-length AVM2 patches."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import ui_browser_avm2_patch_tool as tool
import ui_browser_avm2_repack as repack
import ui_browser_avm2_variable_length_patch as variable


_INSTALLED = False
_BASE_DIALOG_INIT = None
_BASE_DIALOG_ADD = None
_BASE_DIALOG_REMOVE_BRANCH = None
_BASE_MANAGER_REFRESH = None
_BASE_STATUS = None


def _text_value(widget):
    return widget.get("1.0", "end-1c")


def _set_text(widget, value):
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.edit_modified(False)


def _format_count(value):
    try:
        return len(repack.parse_hex_bytes(value))
    except Exception:
        return None


def _update_counts(self, _event=None):
    expected_count = _format_count(_text_value(self.expected_text))
    replacement_count = _format_count(_text_value(self.replacement_text))
    if expected_count is None or replacement_count is None:
        self.count_var.set("Byteanzahl: ungültige Eingabe")
    else:
        delta = replacement_count - expected_count
        delta_text = f"+{delta}" if delta > 0 else str(delta)
        self.count_var.set(
            f"Erwartet: {expected_count} · Neu: {replacement_count} · "
            f"Änderung: {delta_text} Bytes"
        )
    try:
        self.expected_text.edit_modified(False)
        self.replacement_text.edit_modified(False)
    except Exception:
        pass


def _dialog_init(self, inspector, manager=None):
    self.inspector = inspector
    self.owner = inspector.owner
    self.manager = manager
    self.module, self.method_index = tool._selected_method(inspector)
    body = (
        self.module.abc.method_body(self.method_index)
        if self.module.abc is not None else None
    )
    if body is None:
        raise repack.AVM2PatchError(
            "Die ausgewählte Methode hat keinen Methodenbody"
        )

    tk.Toplevel.__init__(self, inspector)
    self.title("AVM2-Byteblock hinzufügen")
    self.geometry("860x650")
    self.minsize(700, 560)
    self.transient(inspector)
    self.grab_set()

    ttk.Label(
        self,
        text=tool._method_label(self.module, self.method_index),
        wraplength=820,
    ).pack(anchor="w", padx=12, pady=(12, 8))

    top = ttk.Frame(self, padding=(12, 0, 12, 8))
    top.pack(fill="x")
    self.offset_var = tk.StringVar(value="0x0")
    self.note_var = tk.StringVar()
    ttk.Label(top, text="Code-Offset:", width=18).grid(
        row=0, column=0, sticky="w", pady=4
    )
    ttk.Entry(top, textvariable=self.offset_var).grid(
        row=0, column=1, sticky="ew", pady=4
    )
    ttk.Label(top, text="Notiz:", width=18).grid(
        row=1, column=0, sticky="w", pady=4
    )
    ttk.Entry(top, textvariable=self.note_var).grid(
        row=1, column=1, sticky="ew", pady=4
    )
    top.columnconfigure(1, weight=1)

    blocks = ttk.Frame(self, padding=(12, 0, 12, 8))
    blocks.pack(fill="both", expand=True)
    blocks.columnconfigure(0, weight=1)
    blocks.columnconfigure(1, weight=1)
    blocks.rowconfigure(1, weight=1)

    ttk.Label(
        blocks,
        text="Erwartete Originalbytes (Sicherheitsanker)",
    ).grid(row=0, column=0, sticky="w", padx=(0, 6))
    ttk.Label(
        blocks,
        text="Neue Bytes (mehrzeilige Blöcke erlaubt)",
    ).grid(row=0, column=1, sticky="w", padx=(6, 0))

    self.expected_text = tk.Text(
        blocks, height=15, wrap="word", undo=True, font=("Consolas", 10)
    )
    self.replacement_text = tk.Text(
        blocks, height=15, wrap="word", undo=True, font=("Consolas", 10)
    )
    self.expected_text.grid(
        row=1, column=0, sticky="nsew", padx=(0, 6), pady=(4, 0)
    )
    self.replacement_text.grid(
        row=1, column=1, sticky="nsew", padx=(6, 0), pady=(4, 0)
    )
    self.expected_text.bind("<<Modified>>", self._update_counts)
    self.replacement_text.bind("<<Modified>>", self._update_counts)

    self.count_var = tk.StringVar(
        value="Erwartet: 0 · Neu: 0 · Änderung: 0 Bytes"
    )
    ttk.Label(
        self, textvariable=self.count_var, font=("TkDefaultFont", 9, "bold")
    ).pack(anchor="w", padx=12, pady=(0, 6))

    warning = ttk.LabelFrame(
        self, text="Wichtig bei Größenänderungen", padding=8
    )
    warning.pack(fill="x", padx=12, pady=(0, 8))
    ttk.Label(
        warning,
        text=(
            "Gleich lange Ersetzungen verschieben nichts. Längere oder kürzere "
            "Blöcke ändern die Methodengröße und verschieben alle späteren Bytes. "
            "Sprung-, lookupswitch- und Exception-Offsets werden nicht automatisch "
            "neu berechnet. Jede Größenänderung muss deshalb ausdrücklich bestätigt "
            "werden; bei mehr als einem Byte zusätzlich oder weniger ist eine zweite "
            "Bestätigung erforderlich."
        ),
        wraplength=810,
        justify="left",
    ).pack(anchor="w")

    helpers = ttk.Frame(self, padding=(12, 0, 12, 8))
    helpers.pack(fill="x")
    ttk.Button(
        helpers, text="pushtrue", command=lambda: _set_text(
            self.replacement_text, "26"
        )
    ).pack(side="left")
    ttk.Button(
        helpers, text="pushfalse", command=lambda: _set_text(
            self.replacement_text, "27"
        )
    ).pack(side="left", padx=(6, 0))
    ttk.Button(
        helpers,
        text="Bedingten Sprung gleichlang entfernen",
        command=self.remove_branch,
    ).pack(side="left", padx=(6, 0))

    buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
    buttons.pack(fill="x")
    ttk.Button(
        buttons, text="Patch prüfen und hinzufügen", command=self.add
    ).pack(side="left")
    ttk.Button(
        buttons, text="Abbrechen", command=self.destroy
    ).pack(side="left", padx=(6, 0))
    ttk.Label(
        buttons, text=f"Methodencode: {len(body.code)} Bytes"
    ).pack(side="right")


def _remove_branch(self):
    expected = repack.parse_hex_bytes(_text_value(self.expected_text))
    if expected and len(expected) != 4:
        messagebox.showerror(
            "AVM2-Patch",
            "Ein bedingter AVM2-Sprung ist normalerweise 4 Bytes lang.",
            parent=self,
        )
        return
    _set_text(self.replacement_text, "29 02 02 02")
    self._update_counts()


def _confirm_size_change(parent, patch):
    delta = variable.patch_delta(patch)
    if delta == 0:
        return True

    verb = "hinzugefügt" if delta > 0 else "entfernt"
    count = abs(delta)
    answer = messagebox.askyesno(
        "AVM2-Größenänderung bestätigen",
        (
            f"Erwartete Originalbytes: {len(patch.expected)}\n"
            f"Neue Bytes: {len(patch.replacement)}\n"
            f"Änderung: {delta:+d} Bytes\n\n"
            f"Es werden {count} Bytes {verb}. Das ist keine gleichlange "
            "Ersetzung.\n\n"
            "Falls du eigentlich nur gleich viele Bytes ersetzen wolltest, "
            "brich jetzt ab und prüfe beide Blöcke.\n\n"
            "Fortfahren?"
        ),
        parent=parent,
        icon="warning",
    )
    if not answer:
        return False

    if count <= 1:
        return True

    token = (
        f"EINFÜGEN {count}" if delta > 0 else f"LÖSCHEN {count}"
    )
    entered = simpledialog.askstring(
        "Mehrere Bytes bestätigen",
        (
            f"Zur Bestätigung exakt eingeben:\n\n{token}\n\n"
            "Damit wird bestätigt, dass die Größenänderung absichtlich "
            "mehr als ein Byte umfasst."
        ),
        parent=parent,
    )
    if (entered or "").strip().upper() != token:
        messagebox.showinfo(
            "AVM2-Patch",
            "Patch nicht hinzugefügt: Bestätigung stimmte nicht überein.",
            parent=parent,
        )
        return False
    return True


def _dialog_add(self):
    try:
        patch = repack.BytePatch(
            self.module.name,
            self.module.source,
            self.method_index,
            repack.parse_hex_bytes(
                self.offset_var.get(), allow_integer=True
            ),
            repack.parse_hex_bytes(_text_value(self.expected_text)),
            repack.parse_hex_bytes(_text_value(self.replacement_text)),
            self.note_var.get().strip(),
        )
        if not _confirm_size_change(self, patch):
            return

        values = tool.current_patches(self.owner)
        candidate = tuple(values) + (patch,)
        _key, _source, _index, _container, record = tool._selection_context(
            self.owner
        )
        tool.apply_movie_patches(record.data, candidate)
        values.append(patch)
        if self.manager is not None:
            self.manager.refresh()
        self.inspector._update_avm2_patch_status()
        self.destroy()
    except Exception as exc:
        messagebox.showerror("AVM2-Patch", str(exc), parent=self)


def _manager_refresh(self):
    self.tree.delete(*self.tree.get_children())
    try:
        patches = tool.current_patches(self.owner)
    except Exception as exc:
        self.status_var.set(str(exc))
        return

    net_delta = 0
    size_changing = 0
    for index, patch in enumerate(patches):
        delta = variable.patch_delta(patch)
        net_delta += delta
        if delta:
            size_changing += 1
        note_prefix = f"[{variable.patch_kind(patch)}]"
        note = f"{note_prefix} {patch.note}".strip()
        self.tree.insert("", "end", iid=str(index), values=(
            patch.module_name,
            patch.source,
            patch.method_index,
            f"0x{patch.code_offset:X}",
            patch.expected.hex(" ").upper(),
            patch.replacement.hex(" ").upper(),
            note,
        ))

    self.status_var.set(
        f"{len(patches)} Patch(es) · {size_changing} mit Größenänderung · "
        f"Netto {net_delta:+d} Bytes"
    )


def _status(self):
    try:
        patches = tool.current_patches(self.owner)
        changed = sum(1 for patch in patches if variable.patch_delta(patch))
        self.avm2_patch_status_var.set(
            f"AVM2-Patches: {len(patches)} · Größenänderungen: {changed}"
        )
    except Exception:
        self.avm2_patch_status_var.set("AVM2-Patches: kein Film")


def install():
    global _INSTALLED
    global _BASE_DIALOG_INIT, _BASE_DIALOG_ADD, _BASE_DIALOG_REMOVE_BRANCH
    global _BASE_MANAGER_REFRESH, _BASE_STATUS
    if _INSTALLED:
        return
    _INSTALLED = True

    # The core installer must run first, even when this module is imported alone.
    variable.install()
    tool.apply_movie_patches = variable.apply_movie_patches
    tool.ui_browser.apply_avm2_movie_patches = variable.apply_movie_patches

    _BASE_DIALOG_INIT = tool.AddPatchDialog.__init__
    _BASE_DIALOG_ADD = tool.AddPatchDialog.add
    _BASE_DIALOG_REMOVE_BRANCH = tool.AddPatchDialog.remove_branch
    _BASE_MANAGER_REFRESH = tool.AVM2PatchManager.refresh
    _BASE_STATUS = tool.avm2.AVM2InspectorWindow._update_avm2_patch_status

    tool.AddPatchDialog.__init__ = _dialog_init
    tool.AddPatchDialog.add = _dialog_add
    tool.AddPatchDialog.remove_branch = _remove_branch
    tool.AddPatchDialog._update_counts = _update_counts
    tool.AVM2PatchManager.refresh = _manager_refresh
    tool.avm2.AVM2InspectorWindow._update_avm2_patch_status = _status
