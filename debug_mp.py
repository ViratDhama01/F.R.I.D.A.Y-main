
try:
    import mediapipe as mp
    print("MP imported")
    try:
        print(mp.solutions)
    except AttributeError:
        print("mp.solutions missing")
        
    import mediapipe.python.solutions as solutions
    print("Found solutions at mediapipe.python.solutions")
except ImportError as e:
    print(e)
except Exception as e:
    print(e)
