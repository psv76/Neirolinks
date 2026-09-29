"""Shared runtime attribution and durable recovery; exclusively fake WB."""
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

from test_pressure_makeup import PressureFixture
from nli.core import Engine
from nli.cli import main
from nli.journal import classify, devices
from nli.layout import LOG_DIR
from nli.util import digest

EXTERNAL = '/etc/wb-rules/vendor.js'
SOURCE = "var virtual = 'vendor-widget', git = 'https://example.invalid'; defineVirtualDevice(virtual, {});"
ERROR = 'ERROR: Error in creating control check on device vendor-widget: Control already exists'


class AttributionTests(PressureFixture):
    def setUp(self):
        super().setUp()
        self.put(EXTERNAL, SOURCE.encode())
        self.config['components']['hhm']['unmanaged_rules'][EXTERNAL] = digest(SOURCE.encode())

    def test_foreign_update_and_rollback_audited_both_components(self):
        self.system.logs = ERROR
        for component in ('pressure_makeup', 'hhm'):
            for command in ('update', 'rollback'):
                r = self.engine.mutate(command, component)
                self.assertEqual(r['final_status'], 'ok', r)
                event = r['verification_attempts'][0]['journal'][0]
                self.assertEqual(event, dict(message=ERROR, category='shared_runtime', sources=[EXTERNAL], fatal=False, technical=False))
                saved = json.loads(self.engine.target(LOG_DIR + '/' + r['id'] + '.json').read_bytes())
                self.assertEqual(saved['verification_attempts'], r['verification_attempts'])
                self.assertIsNone(self.engine.pending())

    def test_own_error_rolls_back_and_preserves_both_attempts(self):
        for component, own in [('pressure_makeup', 'pressure_makeup'), ('hhm', 'NL_simple_thermostat_zone1')]:
            with patch.object(self.system, 'journal', side_effect=[ERROR + '\nTypeError on device ' + own, ERROR]):
                r = self.engine.mutate('update', component)
            self.assertEqual(r['final_status'], 'rolled_back', r)
            attempts = r['verification_attempts']
            self.assertEqual([a['status'] for a in attempts], ['failed', 'ok'])
            self.assertEqual(attempts[0]['journal'][1]['category'], 'component_fatal')
            self.assertFalse(attempts[1]['journal'][0]['fatal'])
            self.assertIsNone(self.engine.pending())

    def test_legacy_pending_recovered_without_deleting_evidence(self):
        # Equivalent old global gate: both verification attempts fail.
        self.system.logs = 'SyntaxError 507_Pressure_makeup.js'
        failed = self.engine.mutate('update', self.component)
        self.assertEqual(failed['final_status'], 'partial_failure', failed)
        pending = self.engine.pending()
        pending.pop('verification_attempts', None)  # pre-0.1.4 record schema
        self.engine.pending_path.write_text(json.dumps(pending))
        old_audit = self.engine.target(LOG_DIR + '/' + failed['id'] + '.json').read_bytes()
        self.system.logs = ERROR
        recovered = Engine(self.config, self.root, self.system).mutate('rollback', self.component)
        self.assertEqual(recovered['final_status'], 'ok', recovered)
        self.assertEqual(recovered['backup'], failed['backup'])
        self.assertIsNone(self.engine.pending())
        self.assertEqual(self.engine.target(LOG_DIR + '/' + failed['id'] + '.json').read_bytes(), old_audit)
        self.assertEqual(self.engine.current(self.component)['version'], '1.0')

    def test_own_and_unknown_errors_keep_pending_when_restore_fails(self):
        for error in ('SyntaxError [507_Pressure_makeup]', 'TypeError [507_Pressure_makeup]'):
            self.system.logs = error
            r = self.engine.mutate('update' if not self.engine.pending() else 'rollback', self.component)
            self.assertEqual(r['final_status'], 'partial_failure', r)
            self.assertIsNotNone(self.engine.pending())

    def test_standalone_reports_foreign_errors_without_install_failure(self):
        self.system.logs = ERROR
        r = self.engine.read_operation('verify', self.component)
        self.assertEqual(r['final_status'], 'ok', r)
        self.assertFalse(r['verification_attempts'][0]['journal'][0]['fatal'])

    def test_foreign_drift_is_not_warning(self):
        self.put(EXTERNAL, b'changed')
        self.system.logs = ERROR
        r = self.engine.mutate('update', self.component)
        self.assertEqual(r['final_status'], 'failed', r)
        self.assertEqual(self.system.actions, [])

    def test_plain_cli_shows_foreign_warning(self):
        self.system.logs = ERROR
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(['update', self.component], engine=self.engine)
        self.assertEqual(code, 0)
        self.assertIn('shared_runtime', out.getvalue())
        self.assertIn(ERROR, out.getvalue())



class ParserTests(unittest.TestCase):
    def test_field_declaration_is_understood_without_named_exception(self):
        path = Path(__file__).resolve().parents[2] / 'objects/05_31_Ivolga_13/Wirenboard/wb-rules/upd-wbe2-i-opentherm.js'
        source = path.read_text(encoding='utf-8')
        self.assertIn('nevoton-updater', devices(source))
        renamed = source.replace('nevoton-updater', 'any-other-vendor')
        self.assertIn('any-other-vendor', devices(renamed))

    def test_literal_variable_and_comments(self):
        self.assertEqual(devices(SOURCE), {'vendor-widget'})
        self.assertEqual(devices("// defineVirtualDevice('fake', {});\ndefineVirtualDevice('real', {});"), {'real'})

    def test_no_dynamic_or_reassigned_or_property_inference(self):
        for source in ("var x='one'; x='two'; defineVirtualDevice(x, {});",
                       "var x='one'; x *= 2; defineVirtualDevice(x, {});",
                       "var x='one'; function f(x) { defineVirtualDevice(x, {}); }",
                       "var text = `defineVirtualDevice('fake', {});`;",
                       "defineVirtualDevice('a' + x, {});", "obj.defineVirtualDevice('fake', {});",
                       'defineVirtualDevice("a\\x62", {});'):
            self.assertEqual(devices(source), set())

    def test_ambiguity_module_and_own_stack_fail_closed(self):
        own = '/etc/wb-rules/507_Pressure_makeup.js'
        for sources, log in (({EXTERNAL: SOURCE, '/etc/wb-rules/second.js': SOURCE}, ERROR),
                             ({'/etc/wb-rules-modules/helper.js': ''}, 'ERROR helper.js'),
                             ({EXTERNAL: SOURCE, own: ''}, ERROR + '\n    at ' + own + ':12')):
            self.assertFalse(classify(log, sources, {own}, ('pressure_makeup',), True)[0]['fatal'])

    def test_adjacent_info_does_not_reassign_error(self):
        events = classify(ERROR + '\nINFO [507_Pressure_makeup] started', {EXTERNAL: SOURCE}, set(), ('pressure_makeup',), True)
        self.assertFalse(events[0]['fatal'])


if __name__ == '__main__':
    unittest.main()
