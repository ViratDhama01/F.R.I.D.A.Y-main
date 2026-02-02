
import cv2

def test_camera(index):
    try:
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            print(f"Index {index}: SUCCESS")
            ret, frame = cap.read()
            if ret:
                print(f"Index {index}: CAPTURED FRAME {frame.shape}")
            else:
                print(f"Index {index}: FAILED TO READ")
            cap.release()
        else:
            print(f"Index {index}: FAILED TO OPEN")
    except Exception as e:
        print(f"Index {index}: ERROR {e}")

print("Testing cameras...")
for i in range(4):
    test_camera(i)
