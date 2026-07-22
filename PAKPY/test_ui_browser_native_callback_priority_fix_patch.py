import unittest
from types import SimpleNamespace

import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_patch as native
import ui_browser_native_callback_priority_fix_patch as patch


class NativeCallbackPriorityFixTests(unittest.TestCase):
    def test_override_suppresses_lower_registry_and_write_side_effects(self):
        movie = SimpleNamespace(
            avm2_modules=(),
            ui_avm2_runtime_generation=0,
            ui_avm2_runtime_revision=0,
            ui_avm2_runtime_log=[],
            ui_avm2_runtime_errors=[],
            ui_native_callback_overrides={"SetDataValue": False},
        )
        context = SimpleNamespace(movie=movie, path="root/1:test", callbacks=0)
        lower_calls = []
        old = patch._BASE_NATIVE
        patch._BASE_NATIVE = lambda *_args: lower_calls.append(True) or True
        try:
            result = patch.native_call(
                context, "SetDataValue", ("debug", "mRuntimeData", "allowInput", True),
            )
        finally:
            patch._BASE_NATIVE = old
        self.assertFalse(result)
        self.assertEqual(lower_calls, [])
        self.assertEqual(context.callbacks, 1)
        self.assertEqual(native._callback_state(movie)["calls"][-1]["source"], "Native-Override")


if __name__ == "__main__":
    unittest.main()
