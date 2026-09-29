"""Synthetic preview contract tests; never use a database or broker."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('preview_demo', pathlib.Path(__file__).with_name('preview_demo.py'))
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'index.html').write_text('<html><body>Preview app</body></html>')
        self.server = module.make_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def test_injects_demo_label_in_deep_link(self):
        with urllib.request.urlopen(self.url + '/portfolio?tab=holdings') as response:
            self.assertIn(b'DEMO / SYNTHETIC DATA', response.read())
    def test_only_explicit_fixture_reads_are_served(self):
        with urllib.request.urlopen(self.url + '/api/auth/session') as response:
            self.assertEqual(json.load(response)['mode'], 'local')
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self.url + '/api/unknown')
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()
    def test_v2_fixture_matches_real_public_serializer(self):
        import subprocess
        output = subprocess.check_output([sys.executable, str(pathlib.Path(__file__).with_name('serialize_sync_fixture.py'))], text=True)
        serialized = json.loads(output)
        self.assertEqual(module.FIXTURES['/api/sync/status']['last_run'], serialized)
        committed = pathlib.Path(__file__).parents[1] / 'src/components/__tests__/fixtures/public-sync-v2.json'
        self.assertEqual(json.loads(committed.read_text()), serialized)

    def test_additional_routes_have_explicit_populated_synthetic_fixtures(self):
        for path in ['/api/cgt/summary', '/api/orders/positions', '/api/orders/analytics', '/api/orders/page', '/api/imports/diff']:
            with urllib.request.urlopen(self.url + path) as response:
                body = json.load(response)
                self.assertTrue(body, path)
        self.assertTrue(module.FIXTURES['/api/cgt/summary']['instruments'][0]['sales'])
        self.assertTrue(module.FIXTURES['/api/orders/positions'][0]['security_name'].startswith('DEMO'))

    def test_rejects_all_mutations(self):
        for method in ['POST','PATCH','PUT','DELETE']:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(urllib.request.Request(self.url + '/api/groups', data=b'{}', method=method))
            self.assertEqual(raised.exception.code, 405)
            raised.exception.close()

if __name__ == '__main__': unittest.main()
