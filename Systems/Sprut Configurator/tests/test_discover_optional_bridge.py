"""Issue #202: three offline regression tests; no controller connection."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sprut_configurator_dev as app

ROOMS = [{"id": 1, "name": "Room"}]
ACCESSORIES = [{"id": 10, "serial": "test", "name": "Device", "roomId": 1,
                "services": [{"sId": 13, "type": "Switch", "name": "Switch"}]}]
MEMBERS = [{"bridgeIndex": "Yandex_1", "aId": 10, "sId": 13}]


def plan(alice=None):
    service = {"type": "Switch", "name": "Switch"}
    if alice is not None:
        service["bridge"] = {"alice": alice}
    return {"format_version": 2, "accessories": [
        {"serial": "test", "name": "Device", "room": "Room", "services": [service]}]}


class FakeSocket:
    def __init__(self, bridge_reply, failure_at="bridgeService"):
        self.bridge_reply = bridge_reply
        self.failure_at = failure_at
        self.requests = []

    def send(self, raw):
        self.request = json.loads(raw)
        self.requests.append(self.request["params"])

    def recv(self, **kwargs):
        params = self.request["params"]
        if self.failure_at in params:
            reply = self.bridge_reply
        elif "room" in params:
            reply = {"result": {"room": {"list": {"rooms": ROOMS}}}}
        elif "accessory" in params:
            reply = {"result": {"accessory": {"list": {"accessories": ACCESSORIES}}}}
        else:
            raise AssertionError(params)
        return json.dumps({"id": self.request["id"], **reply})


def client(reply, failure_at="bridgeService"):
    obj = app.base.SprutClient(SimpleNamespace(cid="test", token="test", serial="test"))
    obj._ws = FakeSocket(reply, failure_at)
    return obj


class OptionalBridgeTests(unittest.TestCase):
    def test_stable(self):
        obj = client({"result": {"bridgeService": {"list": {"services": MEMBERS}}}})
        data = obj.discover()
        self.assertEqual(data["bridges"]["Yandex_1"], MEMBERS)
        self.assertEqual(data["meta"]["yandex_bridge_services_count"], 1)
        getter = app._alice_state_getter_from_discover(data)
        self.assertIs(getter(ACCESSORIES[0], {"sId": 13}), True)
        self.assertIs(getter(ACCESSORIES[0], {"sId": 99}), False)
        self.assertTrue(app.make_dry_run_v2(plan(True), data).ok)
        self.assertEqual(obj._ws.requests[-1], app.yandex_bridge_list_params())

    def test_beta_unknown_blocks_alice(self):
        obj = client({"error": {"code": -32601, "message": "Module not found"}})
        data = obj.discover()
        self.assertEqual(data["rooms"], ROOMS)
        self.assertEqual(data["accessories"], ACCESSORIES)
        self.assertIsNone(data["bridges"]["Yandex_1"])
        self.assertEqual(data["meta"]["yandex_bridge_status"], "unavailable")
        self.assertIsNone(app._alice_state_getter_from_discover(data))
        self.assertTrue(app.make_dry_run_v2(plan(), data).ok)
        for desired in (True, False):
            target = plan(desired)
            dry = app.make_dry_run_v2(target, data)
            self.assertFalse(dry.ok)
            self.assertTrue(any(a.kind == "bridge_alice" and a.current == "UNKNOWN"
                                and a.status == "ERROR" for a in dry.actions))
            ui = SimpleNamespace(auth=object(), plan=target, last_dry_run=dry,
                                 last_dry_plan_hash=app.base._sha256_json(target),
                                 apply_btn=Mock(), _run_worker=Mock())
            app.update_apply_state_v2(ui)
            ui.apply_btn.configure.assert_called_once_with(state="disabled")
            app.base.SprutConfiguratorApp.do_apply(ui)
            ui._run_worker.assert_not_called()

    def test_other_errors_propagate(self):
        for reply, where, exception in [
            ({"error": {"code": -32601, "message": "Method not found"}}, "bridgeService", RuntimeError),
            ({"error": {"code": -32000, "message": "Module not found"}}, "bridgeService", RuntimeError),
            ({"error": {"code": -32601, "message": "Module not found"}}, "room", RuntimeError),
            ({"result": {"bridgeService": {"list": {}}}}, "bridgeService", ValueError),
        ]:
            with self.subTest(reply=reply, where=where):
                with self.assertRaises(exception):
                    client(reply, where).discover()


if __name__ == "__main__":
    unittest.main()
