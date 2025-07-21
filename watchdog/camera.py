"""Module to get camera feed from video file queue"""
import os
import cv2
import numpy as np

class VideoCamera(object):
    """Use opencv to read from video files and create stream"""
    def __init__(self):
        # Using OpenCV to capture from device 0. If you have trouble capturing
        # from a webcam, comment the line below out and use a video file
        # instead.
        # self.video = cv2.VideoCapture(0)
        # If you decide to use video.mp4, you must have this file in the folder
        # as the main.py.

        self.videos = [] # Implemented as a queue
        #self.videos.append('samples/sample.mp4') # Append sample
        placeholder_image = np.zeros((400, 600, 3), dtype=np.uint8)
        _, self.latest_frame_jpeg = cv2.imencode('.jpg', placeholder_image)
        self.video = None
        self.donePlaying = False

    def __del__(self):
        self.video.release()

    def get_frame(self):
        """Use opencv get get frame image from a loaded video, otherwise load video in queue"""
        if not self.video:
            self.load_video()
            return self.latest_frame_jpeg.tobytes()

        success, image = self.video.read()
        # We are using Motion JPEG, but OpenCV defaults to capture raw images,
        # so we must encode it into JPEG in order to correctly display the
        # video stream.
        if success: # Always on, even if static
            ret, self.latest_frame_jpeg = cv2.imencode('.jpg', image)
            # self.video = None # Allow only 1 frame per video
        else:
            self.video = None
        return self.latest_frame_jpeg.tobytes()

    def add_video(self, path: os.PathLike):
        """Add videos from watchdog"""
        self.videos.append(path)
        #print(f"Video [{ len(self.videos) }] added: {path}")

    def clear_videos(self):
        """Clear video render queue"""
        print("Cleared videos")
        self.videos = []

    def load_video(self):
        """Load new videos from top of queue if available"""
        if len(self.videos) > 0:
            self.video = cv2.VideoCapture(self.videos[0])
            #print(f"Loaded video from queue: {self.videos[0]}")
            self.videos.pop(0)
        else:
            self.video = None
