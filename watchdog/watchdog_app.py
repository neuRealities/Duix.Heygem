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

VOICE_DATA_PATH = os.path.expanduser(r"~/heygem_data/voice/data")
VIDEO_TEMP_PATH = os.path.expanduser(r"~/heygem_data/face2face/temp")
autoPlay  = False
isPlaying = True


def rel_path(abs_path:str):
    """Returns relative path from watched directory, for easier display"""
    return os.path.relpath(abs_path, start=VIDEO_TEMP_PATH)

# Add watchdog class to observe temp folder
class TempFileHandler(FileSystemEventHandler):
    """Watchdog class to handle file system events"""
    def on_created(self, event):
        rpath = rel_path(event.src_path)
        if event.is_directory:
            print("Created: Directory:", rpath)
        else:
            print("Created: File:", rpath)
        return super().on_created(event)

    def on_modified(self, event):
        if event.is_directory:  # Ignore directory modifications if only files are desired
            return
        rpath = rel_path(event.src_path)
        print("Modified: File:", rpath)
        return super().on_modified(event)

    def on_deleted(self, event):
        rpath = rel_path(event.src_path)
        if event.is_directory:
            print("Deleted: Directory", rpath)
        else:
            print("Deleted: File", rpath)
        return super().on_deleted(event)

    def on_closed(self, event):
        rpath = rel_path(event.src_path)
        handle_closed_files(rpath)
        return super().on_closed(event)

def handle_closed_files(rpath: str):
    print("Closed: File", rpath)
    if rpath == "output/audio_data.npy":
        # We are ready to start receiving video files
        return

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', audioAutoPlay = 'autoplay' if autoPlay else '')

def gen(camera):
    global autoPlay, isPlaying
    isPlaying = autoPlay
    while True:
        if isPlaying:
            frame = camera.get_frame()
            time.sleep(1.0 / 25.0)
            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen(VideoCamera()),
        mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/pause", methods=['POST'])
def pause():
    global isPlaying
    isPlaying = not(isPlaying)
    print("is Playing: ", isPlaying)
    return jsonify({'playing': isPlaying})

@app.route("/wav")
def wav():
    def generate():
        with open("samples/sample.wav", "rb") as fwav:
            data = fwav.read(1024)
            while data:
                yield data
                data = fwav.read(1024)
    return Response(generate(), mimetype="audio/x-wav")


if __name__ == "__main__":
    # Display page
    app.run(host='0.0.0.0', debug=True)
    # Watchdog subscribe
    path  = VIDEO_TEMP_PATH
    observer = Observer()
    handler = TempFileHandler()
    observer.schedule(handler, path, recursive=True)
    observer.start()
    print("Watchdog: Observing files...")
    print("Use Ctrl+C for KeyboardInterrupt.")
    try:
        while True:
            time.sleep(1) # Keep the main thread alive
    except KeyboardInterrupt:
        observer.stop()
    print("Watchdog: Finished.")
    observer.join()
