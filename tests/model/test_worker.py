"""Independent Pi-worker contract tests using a test-only JSON-RPC peer.

Real subprocess/Pi/provider SDK; controlled HTTP/SSE. These test the worker
protocol, not Go Runtime custody. The Go acceptance suite covers composition.
"""
import copy
import io
import logging
import os
import subprocess
import threading
import time
import unittest
from urllib.request import Request, urlopen
from provider_fixture import CONTEXT, TOOL, model, provider

class EnvironmentTest(unittest.TestCase):

    def test_http_fixture_is_executable(self):
        with provider() as server:
            request = Request(server.base_url + '/chat/completions', data=b'{}', headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                body = response.read().decode()
            self.assertIn('"reasoning_content": "considered"', body)
            self.assertIn('[DONE]', body)
            self.assertEqual(len(server.calls), 1)

class ModelContractTest(unittest.TestCase):

    def setUp(self):
        from rpc_client import WorkerClient
        self.client = WorkerClient()
        self.addCleanup(self.client.close)

    def complete(self, server, **kwargs):
        return self.client.complete(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture-secret-only-in-pipe', timeout=4, **kwargs)

    def test_pi_loop_and_durable_observation_order(self):
        sequence = []

        def observe(event):
            if event['type'] == 'message_end':
                sequence.append(event['message']['role'])

        def execute(name, args, call_id):
            self.assertIn('assistant', sequence)
            sequence.append('execute')
            self.assertEqual((name, args, call_id), ('shell', {'command': 'echo ok'}, 'call_fixture'))
            return {'content': [{'type': 'text', 'text': 'ok'}], 'details': {'receipt': 'r1'}}
        with provider('loop') as server:
            messages = self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=execute, max_turns=3, timeout=4, on_event=observe)
            self.assertEqual([message['role'] for message in messages], ['assistant', 'toolResult', 'assistant'])
            self.assertEqual(len(server.calls), 2)
            self.assertEqual(messages[-1]['stopReason'], 'stop')
            self.assertEqual(sequence[:2], ['assistant', 'execute'])
            self.assertIn('ok', str(server.calls[1]['body']['messages']))

    def test_tool_unknown_outcome_aborts_without_new_call(self):

        def uncertain(*_):
            raise RuntimeError('remote receipt lost')
        with provider('loop') as server:
            with self.assertRaises(Exception):
                self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=uncertain, max_turns=3, timeout=4)
            self.assertEqual(len(server.calls), 1)

    def test_schema_length_and_turn_budget_stop_execution(self):
        for mode in ('invalid', 'length'):
            calls = []
            with self.subTest(mode=mode), provider(mode) as server:
                messages = self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=lambda *args: calls.append(args), max_turns=1, timeout=4)
                self.assertFalse(calls)
                self.assertEqual(len(server.calls), 1)
                self.assertTrue(any((m['role'] == 'toolResult' and m['isError'] for m in messages)))
        with provider('loop') as server:
            self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=lambda *_: {'content': [{'type': 'text', 'text': 'ok'}], 'details': {}}, max_turns=1, timeout=4)
            self.assertEqual(len(server.calls), 1)

    def test_external_strategy_hooks_and_image_tool_result(self):
        checkpoints = []

        def execute(*_):
            return {'content': [{'type': 'image', 'data': 'aGVsbG8=', 'mimeType': 'image/png'}], 'details': {}}

        def prepare(turn):
            return {'context': {**turn['context'], 'systemPrompt': 'external updated projection'}}
        with provider('loop') as server:
            self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=execute, max_turns=3, timeout=4, should_continue=lambda _: True, prepare_turn=prepare, on_event=lambda event: checkpoints.append(event) if event['type'] == 'model_request' else None)
            self.assertEqual(len(server.calls), 2)
            self.assertIn('external updated projection', str(server.calls[1]['body']))
            self.assertIn('data:image/png;base64,aGVsbG8=', str(server.calls[1]['body']))
            self.assertEqual(len(checkpoints), 2)
            self.assertEqual(checkpoints[1]['context']['systemPrompt'], 'external updated projection')
            self.assertEqual(checkpoints[0]['context']['tools'], [TOOL])
            self.assertNotIn('apiKey', str(checkpoints))
        with provider('loop') as server:
            self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=execute, max_turns=3, timeout=4, should_continue=lambda _: False)
            self.assertEqual(len(server.calls), 1)

    def test_custody_rejection_prevents_tool_dispatch(self):
        for boundary, http_calls in (('turn_start', 0), ('model_request', 0), ('message_end', 1)):
            calls = []

            def observe(event):
                if event['type'] == boundary:
                    raise RuntimeError('durable store failed')
            with self.subTest(boundary=boundary), provider('loop') as server:
                with self.assertRaises(Exception):
                    self.client.run(copy.deepcopy(CONTEXT), model=model(server), api_key='fixture', tools=[TOOL], handle_tool=lambda *a: calls.append(a), max_turns=3, timeout=4, on_event=observe)
                self.assertEqual(calls, [])
                self.assertEqual(len(server.calls), http_calls)

    def test_credentials_are_not_in_argv_environment_or_logs(self):
        from rpc_client import WorkerClient
        secret = 'synthetic-secret-model-contract-M08'
        previous = os.environ.get('OPENAI_API_KEY')
        os.environ['OPENAI_API_KEY'] = secret
        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        logging.getLogger().addHandler(handler)
        try:
            with WorkerClient() as client, provider('plain') as server:
                result = client.complete(CONTEXT, model=model(server), api_key=secret, timeout=4)
                self.assertEqual(result['stopReason'], 'stop')
                observed = subprocess.check_output(['ps', 'eww', '-p', str(client.process.pid), '-o', 'command='], text=True)
                self.assertNotIn(secret, observed)
                self.assertNotIn('OPENAI_API_KEY', observed)
                self.assertNotIn(secret, log_output.getvalue())
            checkpoints = []
            with WorkerClient() as client, provider('plain') as server:
                native_model = model(server)
                native_model['headers'] = {'x-private': secret}
                client.run(CONTEXT, model=native_model, api_key=secret, timeout=4, tools=[], handle_tool=lambda *_: None, max_turns=1, options={'headers': {'x-private-options': secret}}, on_event=lambda event: checkpoints.append(event) if event['type'] == 'model_request' else None)
                self.assertEqual(len(checkpoints), 1)
                self.assertNotIn(secret, str(checkpoints))
        finally:
            logging.getLogger().removeHandler(handler)
            if previous is None:
                os.environ.pop('OPENAI_API_KEY', None)
            else:
                os.environ['OPENAI_API_KEY'] = previous
if __name__ == '__main__':
    unittest.main()
