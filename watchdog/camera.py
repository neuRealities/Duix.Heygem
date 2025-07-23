"""Module to get camera feed from video file queue"""
import os
import cv2
import numpy as np
import time

class VideoCamera(object):
    """Use opencv to read from video files and create stream"""
    def __init__(self):
        # Using OpenCV to capture from device 0. If you have trouble capturing
        # from a webcam, comment the line below out and use a video file
        # instead.
        # self.video = cv2.VideoCapture(0)
        # If you decide to use video.mp4, you must have this file in the folder
        # as the main.py.

        self.idle = True
        self.framenum = 0
        self.video_queue = []
        self.video_index = 0
        self.video = {
            'index': 0,
            'capture': None,
            'path': None,
            'frame_count': 0,
            'frame_rate': 0.0,
            'current_frame': 0,
            'load_time': 0
        }
        # Timing
        self.audio_start = 0
        self.video_start = 0
        self.last_video_load_time = -1
        self.video_rate  = 0
        # Debugging
        self.write_output_images = False
        self.output_frames_dir = "frames"
        # Logging
        self.log_progress = True
        # Testing
        placeholder_image = np.zeros((400, 600, 3), dtype=np.uint8)
        _, self.latest_frame_jpeg = cv2.imencode('.jpg', placeholder_image)

    def __str__(self):
        return f"Camera object. Video queue: {len(self.video_queue)}. Current video: {self.video}. idle: {self.idle}"

    def __del__(self):
        self.video['capture'].release()

    def set_frame_output_dir(self, output_frames_dir: os.PathLike):
        """Set frame directory to save each video frame for testing"""
        self.output_frames_dir = output_frames_dir
        if self.write_output_images:
            os.makedirs(self.output_frames_dir, exist_ok=True)

    def get_frame(self):
        """Use opencv get get frame image from a loaded video, otherwise load video in queue"""
        if self.idle:
            return False, self.latest_frame_jpeg.tobytes(), self.framenum, self.video
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
            frame_filepath = self.output_frames_dir + "/" +  \
                os.path.basename(self.video['path']) + "_"+ \
                str(self.video['current_frame']).zfill(2) + "_"+ \
                str(self.framenum).zfill(4) + ".jpg"
            if self.write_output_images:
                with open(frame_filepath, 'wb') as f:
                    # Write the encoded image data (which is a NumPy array of bytes)
                    f.write(self.latest_frame_jpeg)
                    if self.log_progress:
                        print(f"Wrote frame {self.framenum} to: {frame_filepath}")

            self.framenum += 1
            self.video['current_frame'] += 1
        else:
            self.video = None
        return success, self.latest_frame_jpeg.tobytes(), current_frame, self.video

    def clear_videos(self):
        """Clear video render queue"""
        self.video_queue = []

    def load_videos(self, video_list:list, load_time:float):
        """Load multiple videos into queue"""
        for video in video_list:
            self.add_video(video, load_time)
        self.idle = False

    def add_video(self, path: os.PathLike, load_time:float):
        """Add videos, from watchdog or bulk add"""

        prev_video = self.video_queue[-1] if self.video_queue else {}
        prev_load_time = prev_video['load_time'] if prev_video else 0
        self.video_queue.append({'path':path, 'load_time': load_time})
        if self.log_progress:
            latency = load_time - prev_load_time
            print(f"Video [{ len(self.video_queue) - 1 }] added: {os.path.basename(path)}. load_time: {load_time-self.video_start} latency:{latency}")


    def next_video(self):
        """Load new videos from top of queue if available"""
        if len(self.video_queue) > 0:
            video = self.video_queue[0]
            vidcap = cv2.VideoCapture(video['path'])
            self.last_video_load_time = -1
            self.video = {
                'index': self.video_index,
                'capture': vidcap,
                'path': video['path'],
                'frame_count': int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'frame_rate': vidcap.get(cv2.CAP_PROP_FPS),
                'current_frame': 0,
                'load_time': video['load_time']
            }
            self.video_index += 1
            self.video_queue.pop(0)
        else:
            self.video = None
