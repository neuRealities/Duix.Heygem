"""Module to handle file watchdog functions and stream to web"""
import os
import time

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

AUTOPLAY   = False
IS_PLAYING = True
CAMERA     = VideoCamera()

def rel_vidpath(abs_path:str):
    """Returns relative path from watched directory, for easier display"""
    return os.path.relpath(abs_path, start=VIDEO_TEMP_PATH)

# Add watchdog class to observe temp folder
class TempFileHandler(FileSystemEventHandler):
    """Watchdog class to handle file system events"""
    def on_created(self, event):
        rpath = rel_vidpath(event.src_path)
        if event.is_directory:
            print("Created: Directory:", rpath)
        else:
            #print("Created: File:", rpath)
            pass
        return super().on_created(event)

    def on_modified(self, event):
        if event.is_directory:  # Ignore directory modifications if only files are desired
            return
        rpath = rel_vidpath(event.src_path)
        #print("Modified: File:", rpath)
        return super().on_modified(event)

    def on_deleted(self, event):
        rpath = rel_vidpath(event.src_path)
        if event.is_directory:
            print("Deleted: Directory:", rpath)
        else:
            print("Deleted: File:", rpath)
        return super().on_deleted(event)

    def on_closed(self, event):
        rpath = rel_vidpath(event.src_path)
        handle_closed_files(event.src_path, rpath)
        return super().on_closed(event)

def handle_closed_files(fpath: os.PathLike, rpath: os.PathLike):
    """Handler when created or modified files have been closed"""
    global CAMERA
    if rpath == "output/audio_data.npy":
        # The audio file has been writen, and processed into numpy
        # We are ready to start receiving video files
        print(f"audio_data.npy", CAMERA)
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

    print("Closed: File:", rpath)

app = Flask(__name__)

@app.route('/')
def index():
    """Render main flask page"""
    return render_template('index.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')

@app.route('/test')
def test():
    """Render test flask page"""
    return render_template('test.html', audioAutoPlay = 'autoplay' if AUTOPLAY else '')

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
    while True:
        if IS_PLAYING:
            success, fnum, vidfnum, frame = camera.get_frame()
            if success:
                sleep_time = 1.0 / frame_rate
                time_diff = time.time() - current_time
                current_time = time.time()
                avg_frame_time = ((avg_frame_time * fnum - 1) + sleep_time) / fnum
                print(f"time_diff [{fnum} {vidfnum}]: {time_diff:.8f} avg_frame_time: {avg_frame_time:.8f}")
                time.sleep(sleep_time)
            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_load')
def video_load():
    """Get camera and load existiing videos"""
    onlyfiles = [
        os.path.join(dirpath,f)
            for (dirpath, dirnames, filenames) in os.walk(COPIED_VIDEO_PATH)
        for f in filenames]
    onlyfiles.sort()
    audio_length = 21.0
    framerate = len(onlyfiles) * 3 / audio_length
    return load_camera(onlyfiles, framerate)

@app.route('/video_feed')
def video_feed():
    """Get camera with empty video queue"""
    return load_camera([])

def load_camera(video_list:list, frame_rate=28.18):
    """Initialize camera object from cv2.VideoCapture with video queue"""
    global CAMERA
    CAMERA.clear_videos()
    CAMERA.set_frame_output_dir("framedir")
    CAMERA.load_videos(video_list)
    print(CAMERA)
    return Response(gen(CAMERA, frame_rate),
        mimetype='multipart/x-mixed-replace; boundary=frame')

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

def generate_wav(filepath: os.PathLike):
    """Generate audio stream from .wav"""
    with open(filepath, "rb") as fwav:
        data = fwav.read(1024)
        while data:
            yield data
            data = fwav.read(1024)


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
