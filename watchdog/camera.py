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

        self.videos = [] # video list implemented as a queue
        #self.videos.append('samples/sample.mp4') # Append sample
        placeholder_image = np.zeros((400, 600, 3), dtype=np.uint8)
        _, self.latest_frame_jpeg = cv2.imencode('.jpg', placeholder_image)
        self.current_video = {
            'index': 0,
            'capture': None,
            'path': None,
            'frame_count': 0,
            'frame_rate': 0,
        }
        self.video = None
        self.videopath = ""
        self.videoframenum = 0
        self.framedir = "frames"
        self.framenum = 0

    def __str__(self):
        return f"Camera object. Video queue: {len(self.videos)}. Current video: {self.video}"

    def __del__(self):
        self.video.release()

    def set_frame_output_dir(self, framedir: os.PathLike):
        """Set frame directory to save each video frame for testing"""
        self.framedir = framedir
        os.makedirs(self.framedir, exist_ok=True)


    def get_frame(self):
        """Use opencv get get frame image from a loaded video, otherwise load video in queue"""
        if not self.video: # load next video in queue
            self.next_video()
        if not self.video: # If still no next video, return last frame
            return False, self.framenum, self.videoframenum, self.latest_frame_jpeg.tobytes()

        success, image = self.video.read()
        # We are using Motion JPEG, but OpenCV defaults to capture raw images,
        # so we must encode it into JPEG in order to correctly display the
        # video stream.
        if success: # Always on, even if static
            # Get jpeg into memory buffer
            ret, self.latest_frame_jpeg = cv2.imencode('.jpg', image)
            frame_filepath = self.framedir + "/" +  \
                os.path.basename(self.videopath) + "_"+ \
                str(self.videoframenum).zfill(2) + "_"+ \
                str(self.framenum).zfill(4) + ".jpg"
            #print(f"frame filepath: {frame_filepath}")
            with open(frame_filepath, 'wb') as f:
                # Write the encoded image data (which is a NumPy array of bytes)
                f.write(self.latest_frame_jpeg)
            self.framenum += 1
            self.videoframenum += 1

            #self.video = None # Allow only 1 frame per video
        else:
            self.video = None
        return True, self.framenum, self.videoframenum, self.latest_frame_jpeg.tobytes()

    def clear_videos(self):
        """Clear video render queue"""
        self.videos = []

    def load_videos(self, video_list:list):
        """Load multiple videos into queue"""
        for video in video_list:
            self.add_video(video)

    def add_video(self, path: os.PathLike):
        """Add videos, from watchdog or bulk add"""
        self.videos.append(path)
        #print(f"Video [{ len(self.videos) - 1 }] added: {path}")

    def next_video(self):
        """Load new videos from top of queue if available"""
        if len(self.videos) > 0:
            self.video = cv2.VideoCapture(self.videos[0])
            #fps = self.video.get(cv2.CAP_PROP_FPS)
            #print(f"Loaded video from queue: {self.videos[0]} Frames per second of video file: {fps}")
            self.videopath = self.videos[0]
            self.videoframenum = 0
            self.videos.pop(0)
        else:
            self.video = None
