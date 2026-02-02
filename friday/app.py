import cv2
import threading
import time
import numpy as np
import mediapipe as mp
import math
from flask import Flask, render_template, Response, jsonify, request
from PIL import Image
import ollama

# --- 1. SYSTEM INIT ---
app = Flask(__name__)

# --- CONFIGURATION ---
SYSTEM_NAME = "FRIDAY"
SYSTEM_NAME = "FRIDAY"
CURRENT_MODE = "normal" 
IS_AWAKE = True
SCAN_MODE = "describe" # 'describe' or 'threat' 

# --- MEDIAPIPE (OPTIMIZED HANDS) ---
# --- MEDIAPIPE (OPTIMIZED HANDS) ---
mp_hands = None
hands_detector = None

try:
    if hasattr(mp, 'solutions'):
        mp_hands = mp.solutions.hands
        hands_detector = mp_hands.Hands(
            max_num_hands=2,
            model_complexity=0, 
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    else:
        print(">> ERROR: MediaPipe solutions API not available.")
except Exception as e:
    hands_detector = None
    print(f">> ERROR: MediaPipe init failed: {e}")

outputFrame = None
lock = threading.Lock()
cap = cv2.VideoCapture(0)

drawing_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
prev_x, prev_y = 0, 0
is_drawing = False

model = None
try:
    import torch
    import clip
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)
    LABELS = ["cat", "dog", "laptop", "Gun", "coffee cup", "person", "keyboard"]
    text_inputs = clip.tokenize(LABELS).to(device)
except:
    model = None # Fallback

def calculate_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def process_hands(image):
    global drawing_canvas, prev_x, prev_y, is_drawing
    if not hands_detector: return image
    
    image.flags.writeable = False
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = hands_detector.process(rgb)
    image.flags.writeable = True
    
    height, width, _ = image.shape

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            idx_x = int(hand_landmarks.landmark[8].x * width)
            idx_y = int(hand_landmarks.landmark[8].y * height)
            thm_x = int(hand_landmarks.landmark[4].x * width)
            thm_y = int(hand_landmarks.landmark[4].y * height)

            cv2.circle(image, (idx_x, idx_y), 10, (0, 255, 255), 2) 
            cv2.circle(image, (thm_x, thm_y), 10, (255, 0, 255), 2) 

            #  Logic
            dist = calculate_distance((idx_x, idx_y), (thm_x, thm_y))
            if dist < 40:
                cv2.line(image, (idx_x, idx_y), (thm_x, thm_y), (0, 255, 0), 3) 
                if prev_x == 0 and prev_y == 0: prev_x, prev_y = idx_x, idx_y
                cv2.line(drawing_canvas, (prev_x, prev_y), (idx_x, idx_y), (0, 255, 255), 5)
                prev_x, prev_y = idx_x, idx_y
                is_drawing = True
            else:
                prev_x, prev_y = 0, 0
                is_drawing = False

    gray = cv2.cvtColor(drawing_canvas, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    mask_inv = cv2.bitwise_not(mask)
    img_bg = cv2.bitwise_and(image, image, mask=mask_inv)
    img_fg = cv2.bitwise_and(drawing_canvas, drawing_canvas, mask=mask)
    return cv2.add(img_bg, img_fg)

def capture_frames():
    global outputFrame, cap, CURRENT_MODE
    
    # Try to set resolution, but don't fail if it doesn't work
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    except:
        pass
        
    if not cap.isOpened():
        print(">> ERROR: Camera 0 could not be opened in capture_frames.")
        # Try to reopen
        cap = cv2.VideoCapture(0)
    
    print(f">> CAMERA STATUS: Opened={cap.isOpened()}")
    
    fail_count = 0
    while True:
        success, frame = cap.read()
        if not success:
            fail_count += 1
            if fail_count % 30 == 0:
                print(f">> WARNING: Failed to capture frame. Count: {fail_count}")
                # Try to reinitialize camera if continuous failure
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(0)
            time.sleep(0.1)
            continue
        
        fail_count = 0 # Reset counter on success
        
        fail_count = 0 # Reset counter on success


        # Resize for performance and consistency
        try:
            frame = cv2.resize(frame, (1280, 720))
        except:
            pass
            
        frame = cv2.flip(frame, 1)

        if CURRENT_MODE == "mesh":
            frame = process_hands(frame)
        
        # Add a timestamp or indicator to prove it's live
        cv2.putText(frame, f"SYSTEM: {CURRENT_MODE.upper()}", (30, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 240, 255), 2)

        with lock:
            outputFrame = frame.copy()

t = threading.Thread(target=capture_frames)
t.daemon = True
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    def gen():
        global outputFrame
        while True:
            with lock:
                if outputFrame is None: continue
                _, encoded = cv2.imencode(".jpg", outputFrame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + bytearray(encoded) + b'\r\n')
            # print(">> Yielded frame") # Commented out to avoid spam, but can enable if needed
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/command', methods=['POST'])
def command_handler():
    global CURRENT_MODE, drawing_canvas, IS_AWAKE, SCAN_MODE
    data = request.json
    text = data.get('command', '').lower()
    
    response = {"action": "none", "speech": ""}

    # --- 1. WAKE / SLEEP ---
    if "hey friday" in text or "wake up" in text:
        IS_AWAKE = True
        return jsonify({"action": "none", "speech": "I am online."})
    
    if "go to sleep" in text:
        IS_AWAKE = False
        return jsonify({"action": "none", "speech": "Entering standby mode."})

    if not IS_AWAKE:
        return jsonify({"action": "none", "speech": ""})

    # --- 3. EXPLICIT VISION COMMANDS (PRIORITY) ---
    # Triggered by "scan", "look", "what is this", "describe", "scanner"
    scan_triggers = ["scan", "look", "what is this", "describe", "scanner", "analyze", "check", "monitor", "see"]
    if any(trigger in text for trigger in scan_triggers):
        SCAN_MODE = "describe"
        response["action"] = "scan"
        response["speech"] = "Scanning object."
        return jsonify(response)

    if "threat" in text or "danger" in text or "protocol" in text:
        SCAN_MODE = "threat"
        response["action"] = "scan"
        response["speech"] = "Scanning for threats."
        return jsonify(response)

    # --- 3. EXISTING COMMANDS ---
    if "google" in text:
        response["action"] = "open_window"
        response["url"] = "https://www.google.com"
        response["speech"] = "Accessing Google Database."
        return jsonify(response)

    elif "mesh" in text or "draw" in text:
        CURRENT_MODE = "mesh"
        response["action"] = "mode_switch"
        response["speech"] = "Creative mode active."
        return jsonify(response)
    
    elif "clear" in text:
        drawing_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
        response["speech"] = "Canvas wiped."
        return jsonify(response)

    elif "normal" in text or "stop" in text:
        CURRENT_MODE = "normal"
        response["action"] = "mode_switch"
        response["speech"] = "Disengaging UI."
        return jsonify(response)

    # --- 4. GENERAL CHAT (Ollama Fallback) ---
    print(f">> Chat Query: {text}")
    try:
        chat_resp = ollama.chat(model='gemini-3-flash-preview:latest', messages=[
            {'role': 'user', 'content': f"You are FRIDAY, an AI assistant. Answer this briefly: {text}"}
        ])
        reply = chat_resp['message']['content']
        response["speech"] = reply
    except Exception as e:
        print(f">> Chat Error: {e}")
        response["speech"] = "I coould not process that."

    return jsonify(response)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    global outputFrame
    with lock:
        if outputFrame is None: 
            return jsonify({"ui_text": "VIDEO LOSS", "speech_text": "Camera offline.", "is_threat": False})
        # Encode for Ollama
        _, buffer = cv2.imencode('.jpg', outputFrame)
        image_bytes = buffer.tobytes()

    print(">> Sending to Llava...")
    prompt = "Describe this image in one short sentence."
    if SCAN_MODE == "threat":
        prompt = "Identify potential threats in this image. Answer 'SAFE' if none, or 'DANGER: <reason>' if any."

    try:
        response = ollama.chat(model='llava:7b', messages=[
            {
                'role': 'user',
                'content': prompt,
                'images': [image_bytes]
            }
        ])
        description = response['message']['content']
        print(f">> Llava says: {description}")
        
        # Basic threat detection
        threat_keywords = ["danger", "weapon", "gun", "knife", "fire", "threat"]
        is_threat = any(k in description.lower() for k in threat_keywords)
        
        return jsonify({
            "ui_text": "ANALYSIS COMPLETE",
            "speech_text": description,
            "confidence": 100,
            "is_threat": is_threat
        })
    except Exception as e:
        print(f">> Ollama Error: {e}")
        return jsonify({
            "ui_text": "LLM ERROR",
            "speech_text": "I am having trouble seeing right now.",
            "confidence": 0,
            "is_threat": False
        })


if __name__ == '__main__':
    app.run(port=5001)