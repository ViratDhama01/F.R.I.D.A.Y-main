import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from friday.app import create_app


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'workspace'
        self.app = create_app({'TESTING': True, 'WORKSPACE': self.root, 'DATABASE': Path(self.temp.name) / 'state.sqlite3'})
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.headers = {'X-Friday-CSRF': session['csrf']}
        self.agent = self.app.extensions['agent']

    def tearDown(self):
        self.temp.cleanup()

    def post(self, route, data):
        return self.client.post(route, json=data, headers=self.headers)

    def test_offline_status_and_history_persist(self):
        response = self.post('/api/command', {'command': 'system status'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('cpu_count', response.json['speech'])
        second = create_app({'TESTING': True, 'WORKSPACE': self.root, 'DATABASE': self.agent.database})
        self.assertEqual(len(second.extensions['agent'].history()['messages']), 2)

    def test_write_requires_approval_and_cannot_repeat(self):
        response = self.post('/api/tools', {'name': 'write_file', 'arguments': {'path': 'hello.txt', 'content': 'Hello'}})
        action = response.json['result']['approval_required']
        self.assertFalse((self.root / 'hello.txt').exists())
        self.assertEqual(self.post('/api/actions/' + action, {'approve': True}).json['status'], 'completed')
        self.assertEqual((self.root / 'hello.txt').read_text(), 'Hello')
        self.assertEqual(self.post('/api/actions/' + action, {'approve': True}).status_code, 400)

    def test_rejection_and_no_overwrite(self):
        (self.root / 'keep.txt').write_text('original')
        result = self.agent.use('write_file', {'path': 'keep.txt', 'content': 'replacement'})
        self.assertEqual(self.agent.decide(result['approval_required'], True)['status'], 'failed')
        self.assertEqual((self.root / 'keep.txt').read_text(), 'original')
        result = self.agent.use('write_file', {'path': 'no.txt', 'content': 'no'})
        self.agent.decide(result['approval_required'], False)
        self.assertFalse((self.root / 'no.txt').exists())

    def test_traversal_symlinks_and_unknown_tools(self):
        (self.root / 'outside').symlink_to(Path(self.temp.name))
        for path in ('../state.sqlite3', '/etc/passwd', 'outside/state.sqlite3'):
            response = self.post('/api/tools', {'name': 'read_file', 'arguments': {'path': path}})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post('/api/tools', {'name': 'shell', 'arguments': {'command': 'id'}}).status_code, 400)

    def test_csrf_and_validation(self):
        self.assertEqual(self.client.post('/api/command', json={'command': 'system status'}).status_code, 403)
        for data in ({}, {'command': 4}, {'command': ''}, []):
            self.assertEqual(self.post('/api/command', data).status_code, 400)
        self.assertEqual(self.client.get('/video_feed').status_code, 503)
        self.assertEqual(self.post('/api/actions/nope', {'approve': 'true'}).status_code, 400)

    def test_model_tool_loop(self):
        responses = [{'message': {'role': 'assistant', 'tool_calls': [{'function': {'name': 'system_info', 'arguments': {}}}]}}, {'message': {'role': 'assistant', 'content': 'Host inspected.'}}]
        class FakeResponse:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(self.value).encode()
        with patch('friday.agent.urlopen', side_effect=[FakeResponse(r) for r in responses]) as call:
            self.assertEqual(self.agent.chat('Inspect this host'), 'Host inspected.')
            payload = json.loads(call.call_args.args[0].data)
            self.assertEqual(payload['messages'][-1]['role'], 'tool')
        self.assertEqual(self.agent.history()['actions'][0]['status'], 'completed')

    def test_model_approval_stops_execution(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({'message': {'role': 'assistant', 'tool_calls': [{'function': {'name': 'write_file', 'arguments': {'path': 'model.txt', 'content': 'hi'}}}]}}).encode()
        with patch('friday.agent.urlopen', return_value=FakeResponse()):
            self.assertIn('Approval needed', self.agent.chat('Make a file'))
        self.assertFalse((self.root / 'model.txt').exists())

    def test_unavailable_model_and_disallowed_app(self):
        with patch('friday.agent.urlopen', side_effect=OSError('offline')):
            self.assertIn('unavailable', self.agent.chat('Tell me something'))
        with self.assertRaises(ValueError):
            self.agent.use('launch_app', {'name': 'unconfigured'})

    def test_launch_only_after_approval_without_shell(self):
        self.agent.apps = {'demo': ['demo-app', '--new-window']}
        with patch('friday.agent.subprocess.Popen') as launch:
            result = self.agent.use('launch_app', {'name': 'demo'})
            launch.assert_not_called()
            launch.return_value.pid = 123
            result = self.agent.decide(result['approval_required'], True)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(launch.call_args.args[0], ['demo-app', '--new-window'])
            self.assertFalse(launch.call_args.kwargs['shell'])

    def test_speech_endpoint_validation_and_csrf(self):
        self.assertEqual(self.client.post('/api/speech', json={'text': 'Hello'}).status_code, 403)
        for data in ({}, {'text': ''}, {'text': 'x' * 2001}, {'text': 3}, {'text': 'Hello', 'rate': True}, {'text': 'Hello', 'rate': 2}):
            self.assertEqual(self.post('/api/speech', data).status_code, 400)
        with patch.object(self.app.extensions['voice'], 'synthesize', return_value=b'RIFFaudio') as synth:
            response = self.post('/api/speech', {'text': '  Hello  ', 'rate': 1.1})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'audio/wav')
            self.assertEqual(response.data, b'RIFFaudio')
            synth.assert_called_once_with('Hello', 1.1)
        from friday.voice import VoiceUnavailable
        with patch.object(self.app.extensions['voice'], 'synthesize', side_effect=VoiceUnavailable('unavailable')):
            self.assertEqual(self.post('/api/speech', {'text': 'Hello'}).status_code, 503)

    def test_spoken_status_preserves_console_details(self):
        response = self.post('/api/command', {'command': 'system status'})
        self.assertIn('cpu_count', response.json['speech'])
        self.assertIn('Systems online', response.json['spoken'])
        self.assertNotIn('{', response.json['spoken'])

    def test_access_token(self):
        with patch.dict(os.environ, {'FRIDAY_ACCESS_TOKEN': 'test-only-token'}):
            app = create_app({'TESTING': True, 'WORKSPACE': self.root, 'DATABASE': self.agent.database})
        client = app.test_client()
        self.assertEqual(client.get('/api/state').status_code, 401)
        self.assertEqual(client.post('/login', data={'token': 'wrong'}).status_code, 401)
        self.assertEqual(client.post('/login', data={'token': 'test-only-token'}).status_code, 302)
        self.assertEqual(client.get('/api/state').status_code, 200)


if __name__ == '__main__':
    unittest.main()
