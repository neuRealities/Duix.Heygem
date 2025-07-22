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

        self.video_queue = []
        self.video_index = 0
        self.video = {
            'index': 0,
            'capture': None,
            'path': None,
            'frame_count': 0,
            'frame_rate': 0.0,
            'current_frame': 0
        }
        # Testing
        placeholder_image = np.zeros((400, 600, 3), dtype=np.uint8)
        _, self.latest_frame_jpeg = cv2.imencode('.jpg', placeholder_image)
        self.framedir = "frames"
        self.framenum = 0

    def __str__(self):
        return f"Camera object. Video queue: {len(self.video_queue)}. Current video: {self.video}"

    def __del__(self):
        self.video['capture'].release()

    def set_frame_output_dir(self, framedir: os.PathLike):
        """Set frame directory to save each video frame for testing"""
        self.framedir = framedir
        os.makedirs(self.framedir, exist_ok=True)


    def get_frame(self):
        """Use opencv get get frame image from a loaded video, otherwise load video in queue"""
        if not self.video or not self.video['capture']: # load next video in queue
            self.next_video()
        if not self.video: # If still no next video, return last frame
            return False, self.latest_frame_jpeg.tobytes(), self.framenum, self.video

        success, image = self.video['capture'].read()
        # We are using Motion JPEG, but OpenCV defaults to capture raw images,
        # so we must encode it into JPEG in order to correctly display the
        # video stream.
        current_frame = self.framenum
        if success: # Always on, even if static
            # Get jpeg into memory buffer
            ret, self.latest_frame_jpeg = cv2.imencode('.jpg', image)
            frame_filepath = self.framedir + "/" +  \
                os.path.basename(self.video['path']) + "_"+ \
                str(self.video['current_frame']).zfill(2) + "_"+ \
                str(self.framenum).zfill(4) + ".jpg"
            #print(f"frame filepath: {frame_filepath}")
            with open(frame_filepath, 'wb') as f:
                # Write the encoded image data (which is a NumPy array of bytes)
                f.write(self.latest_frame_jpeg)
            self.framenum += 1
            self.video['current_frame'] += 1
        else:
            self.video = None
        return success, self.latest_frame_jpeg.tobytes(), current_frame, self.video

    def clear_videos(self):
        """Clear video render queue"""
        self.video_queue = []

    def load_videos(self, video_list:list):
        """Load multiple videos into queue"""
        for video in video_list:
            self.add_video(video)

    def add_video(self, path: os.PathLike):
        """Add videos, from watchdog or bulk add"""
        self.video_queue.append(path)
        #print(f"Video [{ len(self.video_queue) - 1 }] added: {path}")

    def next_video(self):
        """Load new videos from top of queue if available"""
        if len(self.video_queue) > 0:
            vidcap = cv2.VideoCapture(self.video_queue[0])
            self.video = {
                'index': self.video_index,
                'capture': vidcap,
                'path': self.video_queue[0],
                'frame_count': int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'frame_rate': vidcap.get(cv2.CAP_PROP_FPS),
                'current_frame': 0
            }
            self.video_index += 1
            self.video_queue.pop(0)
        else:
            self.video = None
