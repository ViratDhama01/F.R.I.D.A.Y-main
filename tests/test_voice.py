import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from friday.voice import Voice, VoiceUnavailable


class VoiceTests(unittest.TestCase):
    def test_missing_model_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            voice = Voice()
            voice.path = Path(directory) / 'missing.onnx'
            self.assertFalse(voice.status()['available'])
            with self.assertRaises(VoiceUnavailable):
                voice.synthesize('Hello')

    def test_busy_voice_does_not_queue_unbounded_work(self):
        voice = Voice()
        with patch.object(voice, 'status', return_value={'available': True}):
            voice.lock.acquire()
            try:
                with self.assertRaisesRegex(VoiceUnavailable, 'busy'):
                    voice.synthesize('Hello')
            finally:
                voice.lock.release()

    def test_failure_releases_lock(self):
        voice = Voice()
        with patch.object(voice, 'status', return_value={'available': True}), patch.dict('sys.modules', {'piper': None}):
            with self.assertRaises(VoiceUnavailable):
                voice.synthesize('Hello')
        self.assertFalse(voice.lock.locked())
