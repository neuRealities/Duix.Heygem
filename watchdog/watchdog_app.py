"""Module to handle file watchdog functions and stream to web"""
import os
import time
import math
import wave
import contextlib

# File utilities
import shutil
from pathlib import Path

# Flask display
from flask import Flask, render_template, Response, jsonify
from camera import VideoCamera

# Watchdog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VOICE_DATA_PATH   = Path(os.path.expanduser(r"~/heygem_data/voice/data"))
VIDEO_TEMP_PATH   = Path(os.path.expanduser(r"~/heygem_data/face2face/temp"))
COPIED_VIDEO_PATH = Path(os.path.expanduser(r"~/heygem_data/face2face/copy"))
FRAMEIMAGE_PATH   = Path(os.path.expanduser(r"~/heygem_data/face2face/frameimages"))

AUTOPLAY   = False
IS_PLAYING = True
CAMERA     = VideoCamera()
DEBUG_FILE_EVENTS = False
DEBUG_TIMING      = True
DEFAULT_FPS       = 28.18

def rel_vidpath(abs_path:str):
    """Returns relative path from watched directory, for easier display"""
    return os.path.relpath(abs_path, start=VIDEO_TEMP_PATH)

# Add watchdog class to observe temp folder
class TempFileHandler(FileSystemEventHandler):
    """Watchdog class to handle file system events"""
    def on_created(self, event):
        if event.is_directory:
            handle_created_directories(rel_vidpath(event.src_path))
        print_file_event("Created", rel_vidpath(event.src_path), event.is_directory)
        return super().on_created(event)

    def on_modified(self, event):
        # print_file_event("Modified", rel_vidpath(event.src_path), event.is_directory)
        return super().on_modified(event)

    def on_deleted(self, event):
        print_file_event("Deleted", rel_vidpath(event.src_path), event.is_directory)
        return super().on_deleted(event)

    def on_closed(self, event):
        handle_closed_files(
            "Closed", rel_vidpath(event.src_path), event.is_directory,
            event.src_path)
        return super().on_closed(event)

def print_file_event(action:str, rpath:str, is_directory:bool):
    """Print what filesystem event happened"""
    if DEBUG_FILE_EVENTS:
        print(f"{action} {"Directory" if is_directory else "File" } : {rpath}")


def handle_created_directories(rpath: os.PathLike):
    """Handler when directories are created"""
    global CAMERA
    if rpath == 'output':
        # Clean previous files
        print ("Cleaning previous copied files")
        if os.path.exists(COPIED_VIDEO_PATH):
            shutil.rmtree(COPIED_VIDEO_PATH)
        # Clean previous run
        CAMERA.clear_videos()
    os.makedirs(COPIED_VIDEO_PATH / rpath, exist_ok=True)
    print (f"Creating copied directory: {rpath}")


def handle_closed_files(action:str, rpath: os.PathLike, is_directory:bool, fpath: os.PathLike):
    """Handler when created or modified files have been closed"""
    global CAMERA, DEFAULT_FPS
    print_file_event(action, rpath, is_directory)
    # Copy files before they're gone
    shutil.copy(fpath, COPIED_VIDEO_PATH / rpath)

    # Handle file progress (output subdir).
    # 1. Start with saved audio file: temp.wav and numpy audio_data.npy
    # 2. Creates a directory png, and avi
    # 3. As video generation runs, png files and .avi video files are saved
    # 4. Final files are saved: mylist.txt, result.avi (video-only)
    # 5. Saves mp4 video + audio version output-r.mp4 in parent directory
    # 6. Deleted the output directory

    # 1. Start with saved audio file: temp.wav and numpy audio_data.npy
    if rpath == "output/temp.wav":
        # The audio file has been writen. We are ready to start receiving video files
        audio_length = get_audio_length(fpath)
        expected_frames = int(DEFAULT_FPS * audio_length) - 1
        expected_videos = math.ceil(expected_frames / 2)
        print(f"Audio: {audio_length}s, Expected: Frames: {expected_frames}, Videos: {expected_videos}")
        # Clear previous run
        CAMERA.clear_videos()
        CAMERA.audio_start = time.time()
        CAMERA.video_start = -1
        return

    # 3. As video generation runs, png files and .avi video files are saved
    synthesis_vid_dir = "output/avi/"
    if rpath.startswith(synthesis_vid_dir):
        # Add to camera video queue
        CAMERA.add_video(COPIED_VIDEO_PATH / rpath, time.time())
        if CAMERA.video_start <= 0:
            CAMERA.video_start = time.time()
            if DEBUG_TIMING:
                print(f"Audio to Video latency: {CAMERA.video_start - CAMERA.audio_start}s")
        return

def gen(camera, frame_rate = DEFAULT_FPS):
    """Get frames from camera class"""
    global AUTOPLAY, IS_PLAYING
    # Set Initial state.
    # Notice that AUTOPLAY=True might not work due to browser
    # restrictions on unwanted audio play without user intervention
    IS_PLAYING = AUTOPLAY
    print(f"frame_rate = {frame_rate}")
    avg_frame_duration = 0
    sleep_time = 1.0 / frame_rate
    delta_time = 0
    play_time = 0

    while True:
        if IS_PLAYING:
            # Time retrieval time
            frame_start = time.time()
            success, frame, framenum, video,  = camera.get_frame()
            retrieval_duration = time.time() - frame_start
            if success:

                frameprint_start = time.time()
                videofilename_without_ext, _ = os.path.splitext(os.path.basename(video['path']))
                avg_frame_duration = ((avg_frame_duration * framenum) + sleep_time) / (framenum + 1)
                # Time print
                if DEBUG_TIMING:
                    print(f"Frame: {framenum:03d}. Video Queue: {video['index']:03d}, " \
                        f"Video File: {videofilename_without_ext}, " \
                        f"Vid.Frame: {video['current_frame']}, " \
                        f"delta_time:{delta_time:.7f} Avg Frame Duration: {avg_frame_duration:.8f}")
                frameprint_duration = time.time() - frameprint_start

                # Time actual sleep
                sleep_start = time.time()
                elapsed_time = retrieval_duration + frameprint_duration + delta_time
                requested_sleep = sleep_time - elapsed_time
                time.sleep(max(requested_sleep, 0))
                sleep_duration = time.time() - sleep_start
                delta_sleep = sleep_duration - requested_sleep

                # Meet timing expectations
                expected_play_time = framenum / frame_rate
                if DEBUG_TIMING:
                    print(f"Times: expected:{expected_play_time:.7f}, play: {play_time:.7f}, " \
                        f"sleep: {sleep_duration:.7f}, delta_sleep: {delta_sleep:.7f}")
                frame_duration = time.time() - frame_start # Includes any debug print statements
                play_time += frame_duration
                delta_time = play_time - expected_play_time # Carries on to next frame sleep request

            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

def load_camera(video_list:list, frame_rate=DEFAULT_FPS):
    """Initialize camera object from cv2.VideoCapture with video queue"""
    global CAMERA, FRAMEIMAGE_PATH
    CAMERA.clear_videos()
    if os.path.exists(FRAMEIMAGE_PATH):
        shutil.rmtree(FRAMEIMAGE_PATH)
    CAMERA.set_frame_output_dir(FRAMEIMAGE_PATH.as_posix())
    CAMERA.load_videos(video_list, time.time())
    print("load_camera:", CAMERA)
    return Response(gen(CAMERA, frame_rate),
        mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_wav(filepath: os.PathLike):
    """Generate audio stream from .wav"""
    with open(filepath, "rb") as fwav:
        data = fwav.read(1024)
        while data:
            yield data
            data = fwav.read(1024)

def get_audio_length(filepath: os.PathLike):
    """Get length of audio file"""
    with contextlib.closing(wave.open(filepath,'r')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)
    return duration

def get_videofile_index(videofilepath: os.PathLike):
    """Returns corresponding index integer for synthetic video"""
    vidfile = os.path.basename(videofilepath)
    vidfile_without_ext, _ = os.path.splitext(vidfile)
    return int(vidfile_without_ext)


# Flask functions
app = Flask(__name__)

@app.route('/')
def index():
    """Render main flask page"""
    return render_template('index.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')

@app.route('/load')
def load():
    """Render video load flask page"""
    return render_template('load.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')


@app.route('/video_load')
def video_load():
    """Get camera and load existing videos"""
    video_files = [
        os.path.join(dirpath,f)
            for (dirpath, dirnames, filenames) in os.walk(COPIED_VIDEO_PATH / 'output/avi')
        for f in filenames]
    video_files.sort()
    # Get existing audio file
    audio_duration = get_audio_length((VIDEO_TEMP_PATH / "source_audio_wav.wav").as_posix())
    # There might be missing videos. Use last video's index as reference
    last_item_index = get_videofile_index(video_files[-1])
    # Two frames per expected video. Last video only has 1 frame.
    num_frames = ((last_item_index + 1) * 2) - 1
    print (f"Video files: {len(video_files)}. Expected: {last_item_index + 1}. Frames: {num_frames}")
    print (f"Audio_duration: {audio_duration}")
    framerate = num_frames / audio_duration
    framerate = DEFAULT_FPS # Override
    print (f"Framerate: {framerate}")
    return load_camera(video_files, framerate)

@app.route('/video_feed')
def video_feed():
    """Get camera with empty video queue"""
    return load_camera([])


@app.route("/pause", methods=['POST'])
def pause():
    """Called from the HTML page"""
    global IS_PLAYING
    IS_PLAYING = not IS_PLAYING
    print("is Playing: ", IS_PLAYING)
    return jsonify({'playing': IS_PLAYING})

@app.route("/wav")
def wav():
    """Get audio file and synchronize it to the images being displayed"""
    return Response(generate_wav("samples/sample.wav"), mimetype="audio/x-wav")

@app.route("/wav_load")
def wav_load():
    """Get audio file and synchronize it to the images being displayed"""
    return Response(generate_wav(VIDEO_TEMP_PATH / "source_audio_wav.wav"), mimetype="audio/x-wav")

# Main function
def main():
    """Main watchdog function to observe files created by heygem-gen-video docker service"""
    # Initialize
    global AUTOPLAY, IS_PLAYING
    AUTOPLAY  = False
    IS_PLAYING = True
    # Watchdog subscribe
    observer = Observer()
    handler = TempFileHandler()
    observer.schedule(handler, VIDEO_TEMP_PATH, recursive=True)
    observer.start()
    print("Watchdog: Observing files...")
    print("Use Ctrl+C for KeyboardInterrupt.")

    # Run server
    # debug ids False because otherwise server creates another interfering watchdog instance
    app.run(host='0.0.0.0', debug=False)

    # End when server ends
    print("Watchdog: Finished.")
    observer.stop()
    observer.join()

if __name__ == '__main__':
    main()
