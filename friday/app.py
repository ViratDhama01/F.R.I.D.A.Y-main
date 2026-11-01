"""FRIDAY local control server. Run with python -m friday.app."""
import hmac
import os
import secrets
from pathlib import Path
from flask import Flask, jsonify, render_template, request, session, Response
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "friday"
from .agent import Agent
from .voice import Voice, VoiceUnavailable


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=65536,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')
    if config:
        app.config.update(config)
    state = Path(os.getenv('FRIDAY_STATE_DIR', '~/.friday')).expanduser()
    agent = Agent(app.config.get('WORKSPACE', os.getenv('FRIDAY_WORKSPACE', '~/FridayWorkspace')),
                  app.config.get('DATABASE', state / 'agent.sqlite3'))
    app.extensions['agent'] = agent
    voice = Voice()
    app.extensions['voice'] = voice
    access_token = os.getenv('FRIDAY_ACCESS_TOKEN', '')

    @app.before_request
    def protect():
        if request.path == '/health' or request.path.startswith('/static/'):
            return None
        if access_token and not session.get('authenticated') and request.path != '/login':
            if request.path.startswith('/api/'):
                return jsonify(error='Sign in required'), 401
            return render_template('login.html')
        if request.method == 'POST' and request.path != '/login':
            token = request.headers.get('X-Friday-CSRF', '')
            if not token or not hmac.compare_digest(token, session.get('csrf', '')):
                return jsonify(error='Refresh the page and try again'), 403

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.post('/login')
    def login():
        if access_token and hmac.compare_digest(request.form.get('token', ''), access_token):
            session.clear()
            session['authenticated'] = True
            from flask import redirect
            return redirect('/')
        return render_template('login.html', error='Invalid access token'), 401

    @app.get('/')
    def index():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('index.html', csrf=session['csrf'])

    @app.get('/health')
    def health():
        return jsonify(status='ok')

    @app.get('/api/state')
    def get_state():
        return jsonify(**agent.history(), system=agent.status(), tools=agent.tools(), camera=os.getenv('FRIDAY_CAMERA') == '1')

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object')
        return data

    @app.post('/api/command')
    def command():
        text = body().get('command')
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError('Command must contain 1–8000 characters')
        reply = agent.chat(text.strip())
        spoken = reply
        if text.strip().lower() == 'system status':
            info = agent.status()
            spoken = f"Systems online. {info['cpu_count']} CPU cores available. Disk usage is {info['disk_used_gb']} of {info['disk_total_gb']} gigabytes. Ready for your next instruction."
        elif text.strip().lower() in ('list files', 'show processes'):
            spoken = 'Inspection complete. The results are in your console.'
        return jsonify(speech=reply, spoken=spoken, action='none')

    @app.get('/api/voice')
    def voice_status():
        return jsonify(voice.status())

    @app.post('/api/speech')
    def speech():
        data = body()
        text, rate = data.get('text'), data.get('rate', 1.0)
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError('Speech text must contain 1–2000 characters')
        if isinstance(rate, bool) or not isinstance(rate, (float, int)) or not 0.75 <= rate <= 1.25:
            raise ValueError('Speech rate must be between 0.75 and 1.25')
        try:
            return Response(voice.synthesize(text.strip(), rate), mimetype='audio/wav')
        except VoiceUnavailable as error:
            return jsonify(error=str(error)), 503

    @app.post('/api/tools')
    def tool():
        data = body()
        return jsonify(result=agent.use(data.get('name'), data.get('arguments', {})))

    @app.post('/api/actions/<action_id>')
    def decide(action_id):
        approve = body().get('approve')
        if not isinstance(approve, bool):
            raise ValueError('approve must be true or false')
        return jsonify(agent.decide(action_id, approve))

    @app.get('/video_feed')
    def video():
        if os.getenv('FRIDAY_CAMERA') != '1':
            return jsonify(error='Enable FRIDAY_CAMERA=1 on a host with a camera'), 503
        from . import vision
        if not vision.cap.isOpened():
            return jsonify(error='Camera unavailable'), 503
        def frames():
            import time
            while True:
                with vision.lock:
                    frame = vision.outputFrame.copy() if vision.outputFrame is not None else None
                if frame is not None:
                    ok, encoded = vision.cv2.imencode('.jpg', frame)
                    if ok:
                        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + encoded.tobytes() + b'\r\n'
                time.sleep(.05)
        return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.post('/api/vision/mode')
    def vision_mode():
        if os.getenv('FRIDAY_CAMERA') != '1':
            raise ValueError('Camera is disabled')
        mode = body().get('mode')
        if mode not in ('normal', 'mesh', 'clear'):
            raise ValueError('Unknown camera mode')
        from . import vision
        if mode == 'clear':
            vision.drawing_canvas.fill(0)
        else:
            vision.CURRENT_MODE = mode
        return jsonify(mode=vision.CURRENT_MODE)

    @app.post('/api/analyze')
    def analyze():
        if os.getenv('FRIDAY_CAMERA') != '1':
            raise ValueError('Camera is disabled')
        from . import vision
        import ollama
        with vision.lock:
            frame = vision.outputFrame.copy() if vision.outputFrame is not None else None
        if frame is None:
            raise ValueError('Camera is offline')
        ok, encoded = vision.cv2.imencode('.jpg', frame)
        if not ok:
            raise ValueError('Could not encode camera image')
        try:
            result = ollama.Client(host=agent.endpoint, timeout=90).chat(model=os.getenv('FRIDAY_VISION_MODEL', 'llava:7b'), messages=[{'role': 'user', 'content': 'Describe this image briefly. Do not infer certainty about safety.', 'images': [encoded.tobytes()]}])
            return jsonify(speech_text=result['message']['content'], ui_text='Analysis complete')
        except Exception:
            return jsonify(error='Vision model unavailable. Check Ollama and FRIDAY_VISION_MODEL.'), 503

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(OSError)
    def unavailable(error):
        return jsonify(error='Local operation failed. Check the path and host permissions.'), 400

    return app


if __name__ == '__main__':
    host = os.getenv('FRIDAY_HOST', '127.0.0.1')
    if host not in ('127.0.0.1', 'localhost', '::1') and not os.getenv('FRIDAY_ACCESS_TOKEN'):
        raise SystemExit('Set FRIDAY_ACCESS_TOKEN before exposing FRIDAY beyond localhost')
    create_app().run(host=host, port=int(os.getenv('PORT', '5001')), threaded=True)
