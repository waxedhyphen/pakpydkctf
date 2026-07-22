import unittest
from types import SimpleNamespace

import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_lifecycle_patch as patch


class DummyABC:
    def __init__(self):
        self.instances = (SimpleNamespace(name_index=1, super_name_index=0, initializer=30, traits=()),)
        self.classes = (SimpleNamespace(initializer=20, traits=()),)
        self.scripts = (SimpleNamespace(initializer=10, traits=()),)
        self._bodies = {index: SimpleNamespace(local_count=1) for index in (5, 6, 10, 20, 30)}

    def class_name(self, index):
        return "pkg.Doc"

    def multiname_name(self, index):
        return "pkg.Doc" if index == 1 else ""

    def method_body(self, index):
        return self._bodies.get(index)

    def string(self, index):
        return ""


class Owner:
    def __init__(self, movie):
        self._current_movie = movie
        self._ui_playback_running = False
        self.frame_var = SimpleNamespace(get=lambda: 1)
        self.render_requests = 0

    def request_render(self):
        self.render_requests += 1


class AVM2LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.abc = DummyABC()
        self.module = SimpleNamespace(name="main", source="root", abc=self.abc)
        self.movie = SimpleNamespace(
            avm2_modules=(self.module,), symbol_classes={0: "pkg.Doc"},
            definitions={}, root_tags=[], frame_count=10, frame_rate=10.0, labels={},
            ui_state_overrides={}, ui_timeline_states={},
            ui_avm2_runtime_enabled=True, ui_avm2_runtime_generation=0,
            ui_avm2_runtime_revision=0, ui_avm2_runtime_properties={},
            ui_avm2_runtime_log=[], ui_avm2_runtime_errors=[],
        )
        self.owner = Owner(self.movie)
        self.movie._ui_avm2_runtime_owner = self.owner
        self.context = runtime.RuntimeContext(
            movie=self.movie, abc=self.abc, class_name="pkg.Doc", path="root",
            definition=None, frame=1, playing=False, frame_count=10, labels={},
            owner=self.owner, trait_methods={}, slot_names={},
        )
        patch._BASE.clear()
        patch._BASE.update(
            call=lambda context, receiver, name, args: runtime._UNDEFINED,
            get=lambda context, receiver, name: runtime._UNDEFINED,
            set=lambda context, receiver, name, value: False,
        )

    def test_script_class_and_instance_initializers_run_once(self):
        calls = []
        old = runtime.execute_method
        runtime.execute_method = lambda context, method, arguments=(), receiver=None: calls.append(method)
        try:
            self.assertTrue(patch.initialize_instance(self.owner, self.movie, "root", None, "pkg.Doc"))
            self.assertFalse(patch.initialize_instance(self.owner, self.movie, "root", None, "pkg.Doc"))
        finally:
            runtime.execute_method = old
        self.assertEqual(calls, [10, 20, 30])
        state = patch._state(self.movie)
        self.assertEqual(state["constructors"], 1)
        self.assertEqual(len(state["modules"]), 1)
        self.assertEqual(len(state["classes"]), 1)

    def test_event_dispatcher_add_dispatch_remove_and_constants(self):
        calls = []
        old = runtime.execute_method
        runtime.execute_method = lambda context, method, arguments=(), receiver=None: calls.append((method, arguments[0].type))
        try:
            dispatcher = patch.call_value(self.context, self.context.this_ref(), "EventDispatcher", ())
            self.assertIsInstance(dispatcher, patch.RuntimeDispatcher)
            method = runtime.RuntimeMethod(5, self.context.this_ref())
            self.assertTrue(patch.add_listener(self.context, dispatcher, "change", method))
            self.assertTrue(patch.dispatch_event(self.context, dispatcher, patch.RuntimeEvent("change")))
            self.assertEqual(calls, [(5, "change")])
            self.assertTrue(patch.remove_listener(self.context, dispatcher, "change", method))
            patch.dispatch_event(self.context, dispatcher, patch.RuntimeEvent("change"))
            self.assertEqual(calls, [(5, "change")])
        finally:
            runtime.execute_method = old
        self.assertEqual(
            patch.get_property(self.context, runtime.RuntimeGlobal("flash.events.Event"), "ENTER_FRAME"),
            "enterFrame",
        )

    def test_lifecycle_objects_survive_script_property_roundtrip(self):
        dispatcher = patch.RuntimeDispatcher(7)
        root = self.context.this_ref()
        self.assertTrue(patch.set_property(self.context, root, "mEventDispatcher", dispatcher))
        self.assertIs(patch.get_property(self.context, root, "mEventDispatcher"), dispatcher)
        global_ref = runtime.RuntimeGlobal("mEventDispatcher")
        self.assertIs(patch._resolve_global(self.context, global_ref), dispatcher)

    def test_timer_events_are_deterministic_and_complete(self):
        calls = []
        old = runtime.execute_method
        runtime.execute_method = lambda context, method, arguments=(), receiver=None: calls.append((method, arguments[0].type))
        try:
            timer = patch.call_value(self.context, self.context.this_ref(), "Timer", (100, 2))
            self.assertIsInstance(timer, patch.RuntimeTimer)
            patch.add_listener(self.context, timer, "timer", runtime.RuntimeMethod(5, self.context.this_ref()))
            patch.add_listener(self.context, timer, "timerComplete", runtime.RuntimeMethod(6, self.context.this_ref()))
            patch.call_value(self.context, timer, "start", ())
            patch.advance_runtime_clock(self.owner, 250)
        finally:
            runtime.execute_method = old
        self.assertEqual(calls, [(5, "timer"), (5, "timer"), (6, "timerComplete")])
        self.assertFalse(timer.running)
        self.assertEqual(timer.current_count, 2)

    def test_enter_frame_listener_runs_on_runtime_clock(self):
        calls = []
        old = runtime.execute_method
        runtime.execute_method = lambda context, method, arguments=(), receiver=None: calls.append(method)
        try:
            patch.add_listener(self.context, self.context.this_ref(), "enterFrame", runtime.RuntimeMethod(5, self.context.this_ref()))
            patch.advance_runtime_clock(self.owner, 100)
        finally:
            runtime.execute_method = old
        self.assertEqual(calls, [5])

    def test_set_timeout_calls_method_once(self):
        calls = []
        old = runtime.execute_method
        runtime.execute_method = lambda context, method, arguments=(), receiver=None: calls.append((method, arguments))
        try:
            token = patch.call_value(
                self.context, runtime.RuntimeGlobal("global"), "setTimeout",
                (runtime.RuntimeMethod(5, self.context.this_ref()), 50, "payload"),
            )
            self.assertIsInstance(token, int)
            patch.advance_runtime_clock(self.owner, 49)
            self.assertEqual(calls, [])
            patch.advance_runtime_clock(self.owner, 1)
        finally:
            runtime.execute_method = old
        self.assertEqual(calls, [(5, ("payload",))])
        self.assertNotIn(token, patch._state(self.movie)["timers"])


if __name__ == "__main__":
    unittest.main()
