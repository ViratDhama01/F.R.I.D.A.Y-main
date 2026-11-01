<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:d0f11713edb545aa3552340945f902e5c241ea8f4001f23c7672e62aaf145ef0 -->

<!-- coderabbit-ai-generated-section:v1:d663b3c4049e31baa688540e92b3abb9c993f8cfaa699d73417052f9ad2fcbbd -->

# FRIDAY — Local system agent

A Flask dashboard with conversational tools, host diagnostics, workspace files, approved app launches, saved conversations, optional voice input, and a camera / gesture canvas. Actions run on the **host running FRIDAY**, not the device viewing the dashboard.

## Start

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-agent.txt
python -m friday.app
```

Open http://127.0.0.1:5001. `python friday/app.py` also works. The development server defaults to loopback and is intended for local use.

## Enable natural-language intelligence

Install Ollama separately, start its service, and pull a tool-capable model:

```bash
ollama pull qwen3:8b
ollama serve
```

If Ollama is already running, you only need to pull the model. Choose another installed tool-capable model with `FRIDAY_MODEL`. Set `OLLAMA_HOST` to use another Ollama endpoint. Conversation context and tool results are sent to that endpoint. Model quality and host resources determine planning performance. The agent uses a bounded tool loop and stops for approval before changes.

Try “Read notes.txt and summarize it” or “Create plan.txt with a checklist”. Without a model, use the Tools panel or type `system status`, `list files`, `show processes`, or `help`.

## Capabilities

- Actual OS, CPU count, load average where available, and disk usage.
- List and read workspace files (UTF-8 reads limited to 32KB).
- Create new text files after approval. Existing files are never overwritten; parent directories must exist.
- List running processes by PID and name.
- Launch configured applications after approval. No arbitrary shell execution.
- Persistent SQLite conversation and action history, including pending approvals.
- Optional browser voice input and spoken replies.
- Optional host webcam, gesture drawing, and image description.

Configure application names and executable argument arrays on the host, for example on a Linux desktop:

```bash
export FRIDAY_APPS='{"calculator":["gnome-calculator"],"editor":["gedit"]}'
python -m friday.app
```

Programs must be installed and able to access the host desktop session. Launch results confirm process creation, not that a window opened.

## Control boundaries

Approval cards show exact tool arguments. Each proposal can be approved or rejected once. The model cannot approve its own proposals. File creation refuses overwrites. File access is confined to the configured directory; this is not an OS sandbox. Run as an ordinary user, choose a workspace containing only files intended for agent access, and prevent untrusted local users from modifying it.

This is a single-owner local agent with a shared workspace and history. It does not provide unrestricted desktop control, arbitrary command execution, process termination, or system shutdown. It can manage the tools listed above; add further capabilities as explicit tools with their own validation and approvals.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `FRIDAY_WORKSPACE` | `~/FridayWorkspace`, created automatically |
| `FRIDAY_STATE_DIR` | `~/.friday`, private SQLite history |
| `FRIDAY_MODEL` | `qwen3:8b` |
| `OLLAMA_HOST` | `http://localhost:11434` |
| `FRIDAY_APPS` | `{}`, named executable argument arrays |
| `FRIDAY_HOST` | `127.0.0.1` |
| `PORT` | `5001` |
| `FRIDAY_ACCESS_TOKEN` | Dashboard sign-in token; required by CLI for non-loopback binding |
| `FRIDAY_CAMERA` | Disabled; set to `1` for host webcam and gesture controls |
| `FRIDAY_VISION_MODEL` | `llava:7b`, installed separately in Ollama |

Use a trusted HTTPS connection when accessing remotely and keep the access token private. Sessions reset on server restart; history remains. API mutations require the browser's CSRF token. If deploying through a custom WSGI entry point, configure a stable private Flask secret and access token, and enforce the same network restrictions.

## Natural voice / JARVIS-inspired delivery

The Voice Interface uses an original synthetic British voice with calm, concise delivery. It is not the film actor's voice. Click **Preview voice** to hear it; **Speak replies** is enabled by default. Select a browser voice if you prefer, adjust the speaking pace, replay a reply, or stop speech immediately. Settings stay in your browser. Long replies are limited to a spoken excerpt; full text remains in the console. System status gets a short spoken summary instead of reading JSON.

Install the optional local neural engine and voice (about 65MB of model data):

```bash
pip install -r requirements-voice.txt
python -m piper.download_voices --download-dir ~/.friday/voices en_GB-northern_english_male-medium
python -m friday.app
```

With a custom `FRIDAY_STATE_DIR`, download into its `voices/` subdirectory instead. Alternatively set `FRIDAY_VOICE_MODEL` to the absolute path of a Piper `.onnx` file; its companion `.onnx.json` file must be beside it. Restart FRIDAY after installing dependencies or changing the model. Neural synthesis runs on the host CPU and sends no text to a speech provider. Missing models and synthesis errors are shown in the UI; browser voices can be selected explicitly. Browser voices depend on the browser/OS and may use a vendor service.

Enable **Send voice instructions automatically after dictation** for a voice conversation. This changes dictation from review-before-send to immediate submission after recognition; tool approvals still require a click. The option is off by default and resets on reload. The microphone is one-shot, started by clicking its button; there is no background wake-word listener. Stop speaking before dictation prevents the assistant's own speech from being picked up. Microphone permissions and recognition support still depend on your browser.

Piper engine: [OHF Voice Piper](https://github.com/OHF-Voice/piper1-gpl), GPL-3.0. The default voice is [en_GB-northern_english_male-medium](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/northern_english_male/medium/MODEL_CARD), trained on [OpenSLR 83, Copyright 2018–2019 Google, Inc.; Demirsahin, Kjartansson, Gutkin, and Rivera](https://www.openslr.org/83/), licensed CC BY-SA 4.0. No voice weights are bundled in this repository. Retain the model's attribution and applicable license terms when sharing it or generated recordings.

## Voice and camera

Voice input is opt-in and depends on browser support, microphone permissions, and a secure context. Transcribed text is placed in the input for review before sending. Browser speech recognition may use a vendor service. Typed instructions work independently.

For camera features install `requirements.txt`, set `FRIDAY_CAMERA=1`, and restart. Camera hardware is attached to the host. Gesture drawing requires a MediaPipe version exposing `solutions.hands`; otherwise video runs without gestures. Image description requires an installed Ollama vision model. Image descriptions do not certify safety.

## Verify

```bash
python -m unittest discover -s tests -v
node --check friday/static/app.js
```

Tests cover approval execution/rejection/replay, file boundaries, history persistence, authentication, CSRF, validation, and mocked model tool calls. Hardware availability and real model quality require separate checks on the target computer.


<!-- /coderabbit-ai-generated:v1 -->