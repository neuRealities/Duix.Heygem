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

def gen(camera):
    """Get frames from camera class"""
    global AUTOPLAY, IS_PLAYING
    # Set Initial state.
    # Notice that AUTOPLAY=True might not work due to browser
    # restrictions on unwanted audio play without user intervention
    IS_PLAYING = AUTOPLAY
    while True:
        if IS_PLAYING:
            frame = camera.get_frame()
            time.sleep(1.0 / 25.0)
            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_feed')
def video_feed():
    """Get camera object from cv2.VideoCapture"""
    global CAMERA
    print(CAMERA)
    return Response(gen(CAMERA),
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
    def generate():
        with open("samples/sample.wav", "rb") as fwav:
            data = fwav.read(1024)
            while data:
                yield data
                data = fwav.read(1024)
    return Response(generate(), mimetype="audio/x-wav")


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
