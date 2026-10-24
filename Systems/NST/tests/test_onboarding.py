"""Unregistered WB onboarding evidence: no registry, no mutation, bounded exports."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nst.cli import main
from nst.onboarding import Onboarding, build_map, serial_devices, widget_channels
from nst.layout import unconfigured_state_compatible
from nst.util import Error, digest


class ReadOnlySystem:
    def __init__(self):
        self.actions = []
        self.metadata = (
            '/devices/A01/meta\t{"title":"WB-MR6C","driver":"wb-mqtt-serial"}\n'
            '/devices/A01/controls/K1/meta\t{"title":"K1","type":"switch"}\n'
            '/devices/A01/controls/K2/meta\t{"title":"K2","type":"switch"}\n'
            '/devices/wb-w1/controls/28_0001/meta\t{"title":"Температура","type":"value"}\n'
        )

    def hostname(self):
        return "new-wb-unknown"

    def run(self, argv, timeout=30):
        assert argv[:2] == ["/usr/bin/dpkg-query", "-W"], argv
        return "nst\t2.5\nwb-mqtt-serial\t2.140\nspruthub\t3.0\nother-package\t1.0"

    def mqtt_metadata(self):
        return self.metadata


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.system = ReadOnlySystem()
        self.engine = SimpleNamespace(root=self.root, system=self.system)
        self.put("/var/lib/wirenboard/short_sn.conf", b"NEWABC123\n")
        self.serial = {
            "ports": [{"path": "/dev/ttyRS485-1", "enabled": True,
                       "devices": [{"id": "A01", "device_type": "WB-MR6C", "slave_id": "42",
                                    "name": "WB-MR6C 42"},
                                   {"id": "A02", "device_type": "WB-MSW v4", "slave_id": 51}]}]
        }
        self.webui = {"dashboards":[{"id":"d1","name":"Дом","widgets":[["w1"]]}],
                      "widgets":[{"id":"w1","name":"Освещение",
                                  "cells":[{"id":"A01/K1","name":"Свет кухни"},
                                           {"id":"A01/K3","name":""},
                                           {"id":"separator1","type":"separator"},
                                           {"id":"wb-w1/28_0001","name":"Датчик пола"}]}]}
        self.put("/etc/wb-mqtt-serial.conf", json.dumps(self.serial,ensure_ascii=False).encode())
        self.put("/etc/wb-webui.conf", json.dumps(self.webui,ensure_ascii=False).encode())

    def put(self, logical, data):
        path = self.root/logical.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    @staticmethod
    def entries(result):
        archive = Path(result["bundle"])
        assert digest(archive.read_bytes()) == result["sha256"]
        with tarfile.open(archive,"r:gz") as tar:
            return {m.name:tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}

    def test_collect_unknown_controller_without_registry_or_services(self):
        result = Onboarding(self.engine).collect("inventory")
        self.assertEqual(result["final_status"],"ok")
        self.assertEqual(result["serial"],"NEWABC123")
        entries = self.entries(result)
        self.assertIn("config/etc/wb-mqtt-serial.conf",entries)
        self.assertNotIn("config/etc/wb-webui.conf",entries)
        hardware=json.loads(entries["hardware.json"])
        self.assertEqual(len(hardware["configured_modbus_devices"]),2)
        self.assertEqual([p["package"] for p in hardware["installed_packages"]],
                         ["nst","spruthub","wb-mqtt-serial"])
        self.assertEqual(self.system.actions, [])
        state=self.root/"mnt/data/var/lib/neirolinks/nst"
        self.assertTrue(unconfigured_state_compatible(state),
                        "first-visit archive must not block first approved sync")

    def test_channels_inventory_distinguishes_signed_and_unlabelled(self):
        result=Onboarding(self.engine).collect("channels")
        entries=self.entries(result)
        self.assertIn("config/etc/wb-webui.conf",entries)
        self.assertIn("widget-channels.csv",entries)
        mapping=json.loads(entries["channel-map.json"])
        rows=mapping["webui_channels"]
        kitchen=next(x for x in rows if x["path"]=="A01/K1")
        self.assertEqual(kitchen["ui_label"],"Свет кухни")
        self.assertEqual(kitchen["dashboards"],["Дом"])
        self.assertFalse(next(x for x in rows if x["path"]=="A01/K3")["label_present"])
        self.assertTrue(any(x["device_id"]=="A02" for x in mapping["devices_without_explicit_widget_labels"]))
        self.assertTrue(any(x["path"]=="A01/K2" for x in mapping["mqtt_channels_without_explicit_widget_label"]))
        self.assertTrue(any(x["device_id"]=="wb-w1" for x in mapping["mqtt_devices"]))
        self.assertEqual(self.system.actions,[])
        self.assertEqual(json.loads(entries["meta.json"])["registered"],"not_checked")

    def test_credentials_redacted_and_original_hash_recorded(self):
        raw=json.dumps({"ports":[],"password":"do-not-export","token":"secret-value"}).encode()
        self.put("/etc/wb-mqtt-serial.conf",raw)
        self.put("/etc/wb-webui.conf", b'{"widgets":[],"wifi_password":"private","dashboards":[]}')
        entries=self.entries(Onboarding(self.engine).collect("channels"))
        self.assertNotIn(b"do-not-export",entries["config/etc/wb-mqtt-serial.conf"])
        self.assertNotIn(b"secret-value",entries["config/etc/wb-mqtt-serial.conf"])
        self.assertNotIn(b"private",entries["config/etc/wb-webui.conf"])
        origins=json.loads(entries["config-inventory.json"])
        self.assertEqual(origins[0]["sha256"],digest(raw))
        self.assertTrue(origins[0]["redacted"])

    def test_malformed_config_is_omitted_not_exported(self):
        self.put("/etc/wb-webui.conf", b"not-json passphrase=should-not-leak")
        result=Onboarding(self.engine).collect("channels")
        entries=self.entries(result)
        self.assertNotIn("config/etc/wb-webui.conf",entries)
        self.assertNotIn(b"should-not-leak",b"".join(entries.values()))
        self.assertIn("invalid JSON"," ".join(result["warnings"]))
        self.assertEqual(json.loads(entries["channel-map.json"])["webui_channels"],[])

    def test_missing_webui_does_not_fabricate_labels(self):
        (self.root/"etc/wb-webui.conf").unlink()
        result=Onboarding(self.engine).collect("channels")
        entries=self.entries(result)
        self.assertEqual(json.loads(entries["channel-map.json"])["webui_channels"],[])
        self.assertTrue(result["warnings"])
        self.assertTrue(any(x["device_id"]=="A01" for x in json.loads(entries["channel-map.json"])["devices_without_explicit_widget_labels"]))

    def test_symlink_escape_rejected(self):
        from unittest.mock import patch
        link=self.root/"etc/wb-webui.conf"
        real_is_symlink=Path.is_symlink

        def pretend_symlink(path):
            return path==link or real_is_symlink(path)

        with patch.object(Path, "is_symlink", pretend_symlink):
            with patch("nst.diagnostics.os.readlink", return_value="/tmp/unsafe.conf"):
                with self.assertRaises(Error):
                    Onboarding(self.engine).collect("channels")

    def test_no_serial_blocks_collection(self):
        (self.root/"var/lib/wirenboard/short_sn.conf").unlink()
        with self.assertRaisesRegex(Error,"serial unavailable"):
            Onboarding(self.engine).collect("inventory")

    def test_cli_json_and_human(self):
        for mode in ("collect","channels"):
            output=io.StringIO()
            with redirect_stdout(output):
                exit_code=main(["--json","onboarding",mode],engine=self.engine)
            self.assertEqual(exit_code,0,output.getvalue())
            data=json.loads(output.getvalue())
            self.assertEqual(data["serial"],"NEWABC123")
        output=io.StringIO()
        with redirect_stdout(output):
            exit_code=main(["onboarding","collect"],engine=self.engine)
        self.assertEqual(exit_code,0)
        self.assertIn("NEWABC123",output.getvalue())

    def test_parser_on_realistic_widget_structure(self):
        devices=serial_devices(self.serial)
        rows=widget_channels(self.webui)
        mapping=build_map(devices,rows,{}, {})
        self.assertEqual(len(rows),3)
        self.assertEqual(len(mapping["configured_modbus_devices"]),2)
        self.assertEqual(mapping["webui_channels"][0]["device_id"],"A01")


if __name__=="__main__":
    unittest.main()
