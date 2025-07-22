"""Module to handle file watchdog functions and stream to web"""
import os
import time
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
DEBUG_TIMING      = False

def rel_vidpath(abs_path:str):
    """Returns relative path from watched directory, for easier display"""
    return os.path.relpath(abs_path, start=VIDEO_TEMP_PATH)

# Add watchdog class to observe temp folder
class TempFileHandler(FileSystemEventHandler):
    """Watchdog class to handle file system events"""
    def on_created(self, event):
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


def handle_closed_files(action:str, rpath: os.PathLike, is_directory:bool, fpath: os.PathLike):
    """Handler when created or modified files have been closed"""
    print_file_event(action, rpath, is_directory)
    global CAMERA
    if rpath == "output/audio_data.npy":
        # The audio file has been writen, and processed into numpy
        # We are ready to start receiving video files
        print(f"audio_data.npy: {CAMERA}")
        # Clear previous run
        CAMERA.clear_videos()
        if os.path.exists(COPIED_VIDEO_PATH):
            shutil.rmtree(COPIED_VIDEO_PATH)
        os.makedirs(COPIED_VIDEO_PATH, exist_ok=True)
        return

    synthesis_vid_dir = "output/avi/"
    if rpath.startswith(synthesis_vid_dir):
        # Copy the intermediate file before it's too late
        os.makedirs(COPIED_VIDEO_PATH / synthesis_vid_dir, exist_ok=True)
        shutil.copy(fpath, COPIED_VIDEO_PATH / rpath)
        CAMERA.add_video(COPIED_VIDEO_PATH / rpath)
        return

def gen(camera, frame_rate = 28.18):
    """Get frames from camera class"""
    global AUTOPLAY, IS_PLAYING
    # Set Initial state.
    # Notice that AUTOPLAY=True might not work due to browser
    # restrictions on unwanted audio play without user intervention
    IS_PLAYING = AUTOPLAY
    print(f"frame_rate = {frame_rate}")
    current_time = time.time()
    avg_frame_time = 0
    delta_sleep = 0
    while True:
        if IS_PLAYING:
            # Time retrieval time
            retrieval_time_start = time.time()
            success, frame, framenum, video,  = camera.get_frame()
            retrieval_time = time.time() - retrieval_time_start
            if success:
                sleep_time = 1.0 / frame_rate
                time_diff = time.time() - current_time
                current_time = time.time()
                avg_frame_time = ((avg_frame_time * (framenum)) + sleep_time) / (framenum + 1)
                # Time print
                start_print_time = time.time()
                if DEBUG_TIMING:
                    print(f"Frame: {framenum:03d}. Video: {video['index']:03d}, Vid.Frame: {video['current_frame']} Diff: {time_diff:.8f} Avg: {avg_frame_time:.8f}")
                print_time = time.time() - start_print_time
                # Time actual sleep
                requested_sleep = sleep_time - (retrieval_time + print_time + delta_sleep)
                start_sleep = time.time()
                time.sleep(requested_sleep)
                total_sleep_time =time.time() - start_sleep
                delta_sleep = total_sleep_time - requested_sleep
                if DEBUG_TIMING:
                    print(f"Times: current_time: {current_time:.8f}, retrieval_time: {retrieval_time:.8f}, print_time: {print_time:.8f}, total_sleep_time: {total_sleep_time:.8f} delta_sleep: {delta_sleep:.8f}")

            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

def load_camera(video_list:list, frame_rate=28.18):
    """Initialize camera object from cv2.VideoCapture with video queue"""
    global CAMERA, FRAMEIMAGE_PATH
    CAMERA.clear_videos()
    CAMERA.set_frame_output_dir(FRAMEIMAGE_PATH.as_posix())
    CAMERA.load_videos(video_list)
    print(CAMERA)
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

# Flask functions
app = Flask(__name__)

@app.route('/')
def index():
    """Render main flask page"""
    return render_template('index.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')

@app.route('/test')
def test():
    """Render test flask page"""
    return render_template('test.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')


@app.route('/video_load')
def video_load():
    """Get camera and load existiing videos"""
    onlyfiles = [
        os.path.join(dirpath,f)
            for (dirpath, dirnames, filenames) in os.walk(COPIED_VIDEO_PATH)
        for f in filenames]
    onlyfiles.sort()
    # Get existing audio file
    audio_duration = get_audio_length((VIDEO_TEMP_PATH / "source_audio_wav.wav").as_posix())
    print (f"audio_duration: {audio_duration}")
    framerate = len(onlyfiles) * 2 / audio_duration
    return load_camera(onlyfiles, framerate)

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
