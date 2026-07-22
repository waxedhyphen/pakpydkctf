import unittest

import ui_browser_edit_text_model as model


class EditTextModelTests(unittest.TestCase):
    def target(self, **values):
        defaults = dict(path="root/1:input", text="", multiline=False,
                        selectable=True, max_chars=0, restrict="", password=False)
        defaults.update(values)
        return model.EditableTarget(**defaults)

    def session(self, text="", anchor=None, caret=None):
        anchor = len(text) if anchor is None else anchor
        caret = anchor if caret is None else caret
        return model.EditSession("root/1:input", text, text, anchor, caret)

    def test_inserts_at_caret(self):
        session = self.session("ac", 1)
        self.assertTrue(model.insert_text(session, self.target(text="ac"), "b"))
        self.assertEqual(session.text, "abc")
        self.assertEqual(session.caret, 2)

    def test_replaces_selection(self):
        session = self.session("abcdef", 2, 5)
        model.insert_text(session, self.target(text="abcdef"), "X")
        self.assertEqual(session.text, "abXf")
        self.assertEqual(session.selection, (3, 3))

    def test_respects_max_chars_after_replacement(self):
        session = self.session("12345", 1, 4)
        model.insert_text(session, self.target(text="12345", max_chars=5), "ABCDEFG")
        self.assertEqual(session.text, "1ABC5")

    def test_single_line_removes_line_breaks(self):
        session = self.session()
        model.insert_text(session, self.target(), "A\r\nB\nC")
        self.assertEqual(session.text, "ABC")

    def test_multiline_normalizes_line_breaks(self):
        session = self.session()
        model.insert_text(session, self.target(multiline=True), "A\r\nB\rC")
        self.assertEqual(session.text, "A\nB\nC")

    def test_positive_restrict_supports_ranges(self):
        self.assertEqual(model.filter_restrict("aA9-!", "A-Za-z0-9"), "aA9")

    def test_negative_restrict_excludes_ranges(self):
        self.assertEqual(model.filter_restrict("ab12-CD", "^0-9"), "ab-CD")

    def test_escaped_restrict_literals(self):
        self.assertEqual(model.filter_restrict("a-b\\c", "\\-\\\\"), "-\\")

    def test_word_navigation(self):
        session = self.session("one two three", 13)
        model.move_caret(session, "left", by_word=True)
        self.assertEqual(session.caret, 8)
        model.move_caret(session, "left", by_word=True)
        self.assertEqual(session.caret, 4)
        model.move_caret(session, "right", by_word=True)
        self.assertEqual(session.caret, 8)

    def test_vertical_navigation_preserves_column(self):
        session = self.session("abcd\nxy\n123456", 3)
        model.move_caret(session, "down")
        self.assertEqual(session.caret, 7)
        model.move_caret(session, "down")
        self.assertEqual(session.caret, 11)

    def test_delete_and_undo_redo(self):
        session = self.session("hello", 5)
        target = self.target(text="hello")
        self.assertTrue(model.delete_backward(session, target))
        self.assertEqual(session.text, "hell")
        self.assertTrue(session.undo_once())
        self.assertEqual(session.text, "hello")
        self.assertTrue(session.redo_once())
        self.assertEqual(session.text, "hell")

    def test_password_display_preserves_length(self):
        self.assertEqual(model.display_text("secret", True), "••••••")
        self.assertEqual(model.display_text("secret", False), "secret")

    def test_clipboard_is_bounded_and_plain_text(self):
        raw = "A\x00B\r\nC" + "x" * model.MAX_CLIPBOARD_CHARS
        value = model.sanitize_clipboard(raw, True)
        self.assertNotIn("\x00", value)
        self.assertNotIn("\r", value)
        self.assertLessEqual(len(value), model.MAX_CLIPBOARD_CHARS)
        self.assertEqual(model.sanitize_clipboard("A\nB", False), "A B")

    def test_selection_collapse_uses_direction(self):
        session = self.session("abcdef", 5, 2)
        model.move_caret(session, "left")
        self.assertEqual(session.selection, (2, 2))
        session.anchor, session.caret = 2, 5
        model.move_caret(session, "right")
        self.assertEqual(session.selection, (5, 5))


if __name__ == "__main__":
    unittest.main()
