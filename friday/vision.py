import cv2
import threading
import time
import numpy as np
import mediapipe as mp
import math


# --- CONFIGURATION ---
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

