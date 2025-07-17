import os
import cv2

class VideoCamera(object):

    videos = [] # Implemented as a queue

    def __init__(self):
        # Using OpenCV to capture from device 0. If you have trouble capturing
        # from a webcam, comment the line below out and use a video file
        # instead.
        # self.video = cv2.VideoCapture(0)
        # If you decide to use video.mp4, you must have this file in the folder
        # as the main.py.
        self.video = cv2.VideoCapture('samples/sample.mp4')
    
    def __del__(self):
        self.video.release()
    
    def get_frame(self):
        """Use opencv get get frame image"""
        success, image = self.video.read()
        # We are using Motion JPEG, but OpenCV defaults to capture raw images,
        # so we must encode it into JPEG in order to correctly display the
        # video stream.
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes()
    
    def add_video(self, path: os.PathLike):
        """Add videos from watchdog"""
        self.videos.append(path)
        print(f"Video [{self.videos.count}] added: {path}")

    def clear_videos(self):
        """Clear video render queue"""
        print("Cleared videos")
        self.videos = []
