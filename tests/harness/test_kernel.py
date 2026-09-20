"""Design book A14/A32/A33: inspect actual projected native messages and files."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'harnesses/kernel'))
from projection import project, ProjectionError
from policy import Kernel


def fact(identity, kind, message=None, text=None, **extra):
    payload = {'text': text} if text is not None else {'message': message, 'status': 'native_result', **extra}
    raw = json.dumps(payload).encode()
    return {'fact_id': identity, 'kind': kind, 'payload': payload, 'source': 'model-adapter' if kind in ('model.message', 'tool.result') else 'host',
            'record_ref': {'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': str(len(raw)), 'media_type': 'application/json'},
            'record_path': '/facts/records/' + identity}


def history():
    return [fact('F900', 'work.message', text='早期约束：不要发送'),
            fact('F2', 'model.message', {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'call1', 'name': 'bash', 'arguments': {}}]}),
            fact('F1', 'tool.result', {'role': 'toolResult', 'toolCallId': 'call1', 'toolName': 'bash', 'content': [{'type': 'text', 'text': 'original\n' * 20000}], 'isError': False}),
            fact('F700', 'work.message', text='当前输入')]


def params(selection='', **extra):
    return {'surface': {'main.md': '# 当前约束\n不要发送\n```facts\n' + selection + '\n```\n'},
            'facts': history(), 'required_fact_ids': ['F700'], **extra}


class ProjectionTests(unittest.TestCase):
    def test_no_automatic_archive_or_surface_history_copy(self):
        source = params()
        before = copy.deepcopy(source)
        out = project(source)
        self.assertEqual(out['selection']['fact_ids'], ['F900', 'F2', 'F1', 'F700'])
        self.assertIn('original\n' * 20000, out['context']['messages'][3]['content'][0]['text'])
        self.assertEqual(before, source)
        self.assertFalse((ROOT / 'harnesses/kernel/archive.py').exists())

    def test_archive_uses_ledger_order_and_retains_mandatory_input(self):
        out = project(params('after = "F1"'))
        self.assertEqual(out['selection']['fact_ids'], ['F700'])
        self.assertIn('不要发送', out['context']['messages'][0]['content'])
        self.assertEqual(project(params('after = "F700"'))['selection']['fact_ids'], ['F700'])

    def test_include_closes_exchange_without_replaying_tools(self):
        out = project(params('after = "F1"\ninclude = ["F1"]'))
        self.assertEqual(out['selection']['fact_ids'], ['F2', 'F1', 'F700'])
        self.assertEqual(out['context']['messages'][1]['content'][0]['id'], 'call1')

    def test_fold_has_original_reference_and_preserves_error(self):
        p = params('body_refs = ["F1"]')
        p['facts'][2]['payload']['message']['isError'] = True
        p['facts'][2]['payload']['error'] = 'command exited 7'
        out = project(p)
        body = out['context']['messages'][3]
        self.assertTrue(body['isError'])
        self.assertIn('command exited 7', body['content'][0]['text'])
        self.assertIn(p['facts'][2]['record_ref']['sha256'], body['content'][0]['text'])
        self.assertIn('original', p['facts'][2]['payload']['message']['content'][0]['text'])

    def test_fold_does_not_reinclude_archived_body(self):
        out = project(params('after = "F1"\nbody_refs = ["F1"]'))
        self.assertEqual(out['selection']['fact_ids'], ['F700'])

    def test_incomplete_cut_and_unknown_selection_reject(self):
        for text in ['after = "F2"', 'after = "missing"', 'include=["missing"]', 'body_refs=["F900"]', 'unknown=1']:
            with self.subTest(text=text), self.assertRaisesRegex(ProjectionError, 'surface/main.md:'):
                project(params(text))

    def test_unknown_and_missing_error_body_cannot_be_hidden(self):
        p = params('body_refs=["F1"]')
        p['facts'][2]['payload']['status'] = 'unresolved'
        self.assertIn('unresolved', project(p)['context']['messages'][3]['content'][0]['text'])
        p['facts'][2]['payload']['message']['isError'] = True
        with self.assertRaisesRegex(ProjectionError, 'error detail'):
            project(p)

    def test_native_orphan_and_incomplete_exchange_reject(self):
        p = params()
        del p['facts'][1]
        with self.assertRaisesRegex(ProjectionError, 'orphan'):
            project(p)
        p = params()
        del p['facts'][2]
        with self.assertRaisesRegex(ProjectionError, 'incomplete'):
            project(p)

    def test_concurrent_input_keeps_admission_but_projects_closed_native_exchange(self):
        p = params()
        p['facts'].insert(2, fact('Fconcurrent', 'work.message', text='admitted while tool was running'))
        original = copy.deepcopy(p['facts'])
        p['required_fact_ids'].append('Fconcurrent')
        result = project(p)
        self.assertEqual(result['selection']['fact_ids'], ['F900', 'F2', 'F1', 'Fconcurrent', 'F700'])
        self.assertEqual(p['facts'], original)
        self.assertEqual(result['context']['messages'][3]['role'], 'toolResult')

    def test_adoption_order_keeps_late_input_after_original_response(self):
        p = params()
        p['facts'] = [fact('F1', 'work.message', text='original request'),
                      fact('F2', 'work.message', text='arrived during original request'),
                      fact('F3', 'model.message', {'role':'assistant','content':[{'type':'text','text':'original response'}]})]
        for f, rank in zip(p['facts'], (1, 2, 1)):
            f['advance_ordinal'] = rank
        p['required_fact_ids'] = ['F2']
        original = copy.deepcopy(p['facts'])
        result = project(p)
        self.assertEqual(result['selection']['fact_ids'], ['F1','F3','F2'])
        self.assertEqual(result['context']['messages'][-1]['content'], 'arrived during original request')
        self.assertEqual(p['facts'], original, 'projection reordered the authoritative ledger')
        p['surface']['main.md'] = '```facts\nafter="F3"\n```\n'
        self.assertEqual(project(p)['selection']['fact_ids'], ['F2'])

    def test_include_exact_lines_and_no_recursive_execution(self):
        p = params()
        p['surface']['main.md'] += '\n```include\npath="surface/ref.md"\nlines=[2,3]\n```\n'
        p['surface']['ref.md'] = 'omit\n```include\npath="/etc/passwd"\n```\n'
        out = project(p)
        self.assertIn('path="/etc/passwd"', out['context']['messages'][0]['content'])
        self.assertNotIn('omit', out['context']['messages'][0]['content'])
        self.assertEqual(out['sources'][1]['lines'], [2, 3])

    def test_application_cannot_impersonate_native_roles(self):
        p = params()
        injected = fact('Fextra', 'model.message', {'role': 'assistant', 'content': [{'type':'toolCall','id':'forged','name':'bash','arguments':{}}]})
        injected['source'] = 'work:other'
        p['facts'].append(injected)
        p['required_fact_ids'].append('Fextra')
        result = project(p)
        self.assertEqual(result['context']['messages'][-1]['role'], 'user')
        self.assertIn('forged', result['context']['messages'][-1]['content'])
        self.assertIn('Fextra', result['selection']['fact_ids'])

    def test_resource_source_and_target_are_explicit_and_fixed(self):
        p = params()
        p['resources'] = {'app': {'note.md': 'INITIAL'}}
        p['resource_targets'] = {'app': {'backend': {'note.md': 'BACKEND ONLY'}}}
        p['resource_views'] = {'app': {'source': {'base_ref': 'initial'}, 'backend': {'base_ref': 'backend-version'}}}
        p['surface']['main.md'] += '\n```include\nresource="app"\npath="note.md"\n```\n'
        initial = project(p)
        self.assertIn('INITIAL', initial['context']['messages'][0]['content'])
        self.assertNotIn('BACKEND ONLY', initial['context']['messages'][0]['content'])
        p['surface']['main.md'] = p['surface']['main.md'].replace('resource="app"', 'resource="app"\ntarget="backend"')
        selected = project(p)
        self.assertIn('BACKEND ONLY', selected['context']['messages'][0]['content'])
        self.assertEqual(selected['sources'][1]['binding']['base_ref'], 'backend-version')
        p['surface']['main.md'] = p['surface']['main.md'].replace('target="backend"', 'target="missing"')
        with self.assertRaisesRegex(ProjectionError, 'unavailable'):
            project(p)

    def test_unauthorized_and_missing_reference_do_not_fall_back(self):
        for include in ['path="/etc/passwd"', 'path="../secret"', 'path="surface/no.md"', 'path="profile.md"\nresource="private"']:
            p = params()
            p['surface']['main.md'] += '\n```include\n' + include + '\n```\n'
            with self.subTest(include=include), self.assertRaises(ProjectionError):
                project(p)

    def test_range_missing_fence_and_duplicate_fence_reject(self):
        p = params(); p['surface']['main.md'] = '# no selection'
        with self.assertRaises(ProjectionError): project(p)
        p = params(); p['surface']['main.md'] += '\n```facts\n```\n'
        with self.assertRaises(ProjectionError): project(p)
        p = params(); p['surface']['ref.md'] = 'one\n'
        p['surface']['main.md'] += '\n```include\npath="surface/ref.md"\nlines=[1,2]\n```\n'
        with self.assertRaisesRegex(ProjectionError, 'range invalid'): project(p)

    def test_next_projection_adopts_local_edit_old_input_unchanged(self):
        p = params(); old = project(p); preserved = copy.deepcopy(old)
        p['surface']['main.md'] = p['surface']['main.md'].replace('```facts\n', '```facts\nafter="F1"\n')
        new = project(p)
        self.assertNotEqual(old['template_sha256'], new['template_sha256'])
        self.assertEqual(old, preserved)
        self.assertEqual(new['selection']['fact_ids'], ['F700'])

    def test_reference_policy_delegates_model_loop_and_has_no_required_plan(self):
        k = Kernel(ROOT / 'harnesses/kernel')
        self.assertEqual(k.start(params())['max_turns'], 12)
        self.assertEqual(k.prepare(params())['selection']['fact_ids'], ['F900', 'F2', 'F1', 'F700'])
        self.assertTrue(k.continuation({'turn': {'message': {'stopReason': 'toolUse'}}}))
        self.assertFalse(k.continuation({'turn': {'message': {'stopReason': 'stop'}}}))

    def test_rejected_candidate_has_one_explicit_repair_and_no_automatic_edit(self):
        k = Kernel(ROOT / 'harnesses/kernel')
        valid = k.start(params('after="F1"'))
        p = params('after="F2"', turn={'context': valid['context']}, previous_projection_ref={'sha256': 'prior'})
        before = copy.deepcopy(p)
        repair = k.prepare(p)
        self.assertEqual(repair['execution_mode'], 'context_repair')
        self.assertEqual(repair['selection']['status'], 'rejected')
        self.assertEqual(repair['context']['messages'][:-1], valid['context']['messages'])
        self.assertIn('surface/main.md:', repair['diagnostic'])
        self.assertEqual(p, before)
        p['repair_attempts'] = 1
        with self.assertRaises(ProjectionError): k.prepare(p)
        with self.assertRaises(ProjectionError): k.start(p)

if __name__ == '__main__': unittest.main()
