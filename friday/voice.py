"""Local neural speech: no text leaves the host."""
import importlib.util
import io
import os
import threading
import wave
from pathlib import Path


class VoiceUnavailable(RuntimeError):
    pass


class Voice:
    def __init__(self):
        state = Path(os.getenv('FRIDAY_STATE_DIR', '~/.friday')).expanduser()
        self.path = Path(os.getenv('FRIDAY_VOICE_MODEL', str(state / 'voices/en_GB-northern_english_male-medium.onnx'))).expanduser()
        self.lock = threading.Lock()
        self.model = None

    def status(self):
        ready = (importlib.util.find_spec('piper') is not None and self.path.is_file()
                 and Path(str(self.path) + '.json').is_file())
        return {'available': ready, 'name': 'British · local neural',
                'engine': 'Piper', 'local': True,
                'message': 'Ready on this host' if ready else 'Install requirements-voice.txt and download the voice model. Browser voices remain available.'}

    def synthesize(self, text, rate=1.0):
        if not self.status()['available']:
            raise VoiceUnavailable('Local neural voice is not installed. Use a browser voice or follow the voice setup instructions.')
        if not self.lock.acquire(blocking=False):
            raise VoiceUnavailable('Voice is busy. Please try again in a moment.')
        try:
            from piper import PiperVoice, SynthesisConfig
            if self.model is None:
                self.model = PiperVoice.load(str(self.path))
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                self.model.synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=1.0 / rate))
            return output.getvalue()
        except Exception as error:
            self.model = None
            raise VoiceUnavailable('Neural speech could not be generated. Try a browser voice.') from error
        finally:
            self.lock.release()
