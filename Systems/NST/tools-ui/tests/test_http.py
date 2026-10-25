"""HTTP surface denies cross-origin POST and arbitrary commands."""
import importlib.util
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nst_tools_server_http", ROOT/"service/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.WEB = ROOT/"web"
        server.Handler.jobs = server.Jobs(executor=lambda action: {"final_status": "ok", "action": action})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.httpd.daemon_threads = True
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.httpd.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def urlopen(self, path, data=None, origin=None, intent=None):
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        if intent is not None:
            headers["X-NST-Intent"] = intent
        return urllib.request.urlopen(
            urllib.request.Request(self.url+path, data=data, headers=headers),
            timeout=3)

    def test_static_page_readable_and_no_write_endpoint(self):
        with self.urlopen("/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"NEIROLINKS", resp.read())
            self.assertIn("nosniff", resp.headers.get("X-Content-Type-Options"))
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.urlopen("/api/jobs/sync", data=b"{}", origin=self.url, intent="ui")
        self.assertEqual(e.exception.code,404)

    def test_cross_origin_post_denied_even_with_intent(self):
        for origin, intent in [(None,"ui"), ("https://example.net", "ui"), (self.url, None)]:
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.urlopen("/api/jobs/channels",data=b"{}",origin=origin,intent=intent)
            self.assertEqual(e.exception.code,403)

    def test_valid_same_origin_post_and_poll(self):
        with self.urlopen("/api/jobs/inventory", data=b"{}", origin=self.url, intent="ui") as response:
            self.assertEqual(response.status,202)
            job = json.load(response)["job"]
        self.assertEqual(len(job),32)
        with self.urlopen("/api/jobs/"+job) as response:
            self.assertIn(json.load(response)["state"], ("running", "complete"))
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.urlopen("/api/download/"+job+"?token=wrong")
        self.assertEqual(error.exception.code,404)

if __name__ == "__main__":
    unittest.main()
