"""Module to handle file watchdog functions and stream to web"""
import os
import time
import math
import wave
import contextlib
import json

# File utilities
import shutil
from pathlib import Path

# Flask display
from flask import Flask, render_template, request, Response, jsonify
from camera import VideoCamera, CameraStatus

# Watchdog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

LOG_FILE_EVENTS = True
LOG_TIMING      = True
LOG_CAMERA      = True
LOG_FLASK       = True
LOG_MERGE_CREATE_CLOSE = True
DEFAULT_FPS     = 28.18

# Define paths
VOICE_DATA_PATH   = Path(os.path.expanduser(r"~/heygem_data/voice/data"))
VIDEO_TEMP_PATH   = Path(os.path.expanduser(r"~/heygem_data/face2face/temp"))
COPIED_VIDEO_PATH = Path(os.path.expanduser(r"~/heygem_data/face2face/copy"))
FRAMEIMAGE_PATH   = Path(os.path.expanduser(r"~/heygem_data/face2face/frameimages"))
TASK_ID = None

CAMERA     = VideoCamera()
CAMERA.log_progress = LOG_CAMERA
CAMERA.log_files = LOG_FILE_EVENTS

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
    if LOG_FILE_EVENTS:
        print(f"{action} {"Directory" if is_directory else "File" } : {rpath}")

# Expect the following events to happen as the rendering progresses

# Audio file creation:
# 01. Create a <random_id_audio_gen>.wav file in the rpath root
# 02. Create a <task_id> folder
# 03. Copy audio file as <task_id>/temp.wav
# 04. Copy numpy audio data as <task_id>/audio_data.npy

# Image and video creation
# Example below is from Text Input, not Adio Upload synthesis
# 05. Create directory <task_id>/png only for long synthesis
# 06. Create directory <task_id>/avi
# 07. Run video generation, <number++>.avi video files are saved
# 08. Save Final files: mylist.txt, result.avi (video-only)

# Merge and cleanup
# 09. Merge audio+vid with ffmpeg: <task_id>-r.mp4
# 10. Delete <task_id> directory


# Start process with
# 02. Create a <task_id> folder, in handle_created_directories()

def handle_created_directories(rpath: os.PathLike):
    """Handler when directories are created"""
    global TASK_ID
    if not (str(rpath).endswith("/avi") or str(rpath).endswith("/png")):
        # 02. Create a <task_id> folder, so get TASK_ID
        TASK_ID = str(rpath)
        if LOG_FILE_EVENTS:
            print (f"Task <{TASK_ID}> is cleaning previous copied files")
        if os.path.exists(COPIED_VIDEO_PATH):
            shutil.rmtree(COPIED_VIDEO_PATH)
        # Clean previous run
        CAMERA.clear_videos()

    # Copy directory
    os.makedirs(COPIED_VIDEO_PATH / rpath, exist_ok=True)

def handle_closed_files(action:str, rpath: os.PathLike, is_directory:bool, fpath: os.PathLike):
    """Handler when created or modified files have been closed"""
    global CAMERA, DEFAULT_FPS
    if LOG_FILE_EVENTS:
        print_file_event(action, rpath, is_directory)
    # Copy files before they're gone
    shutil.copy(fpath, COPIED_VIDEO_PATH / rpath)

    if not TASK_ID:
        return

    # 03. Copy audio file as <task_id>/temp.wav
    if rpath == f"{TASK_ID}/temp.wav":
        # The audio file has been writen. We are ready to start receiving video files
        audio_length = get_audio_length(fpath)
        expected_frames = int(DEFAULT_FPS * audio_length) - 1
        expected_videos = math.ceil(expected_frames / 2)
        if LOG_FILE_EVENTS:
            print(f"Audio: {audio_length}s, Expected: Frames: {expected_frames}, Videos: {expected_videos}")
        # Clear previous run
        CAMERA.clear_videos()
        CAMERA.set_status(CameraStatus.AUDIO_GENERATED, "temp.wav created")
        CAMERA.audio_start = time.time()
        CAMERA.video_start = -1
        return

    # 07. Run video generation, <number++>.avi video files are saved
    synthesis_vid_dir = f"{TASK_ID}/avi/"
    if rpath.startswith(synthesis_vid_dir):
        # Add to camera video queue
        if CAMERA.video_start <= 0:
            CAMERA.set_status(CameraStatus.VIDEO_BUFFERING, "avi dir created")
            CAMERA.video_start = time.time()
            print(f"Audio to Video latency: {CAMERA.video_start - CAMERA.audio_start}s")
        CAMERA.add_video(COPIED_VIDEO_PATH / rpath, time.time())
        return

    # 08. Save Final files: mylist.txt, result.avi (video-only)
    if rpath == f"{TASK_ID}/mylist.txt":
        CAMERA.set_status(CameraStatus.STREAM_VIDEO_DONE, "mylist.txt created")

def generate_camera(camera:VideoCamera, frame_rate = DEFAULT_FPS):
    """Generated camera fron openCV serviving single image frames"""
    # Set Initial state.
    avg_frame_duration = 0
    sleep_time = 1.0 / frame_rate
    delta_time = 0
    play_time = 0

    while not is_finished(camera.status):
        if is_playing(camera.status):
            # Time retrieval time
            frame_start = time.time()
            success, frame, framenum, video,  = camera.get_frame()
            retrieval_duration = time.time() - frame_start
            if success:
                frameprint_start = time.time()
                videofilename_without_ext, _ = os.path.splitext(os.path.basename(video['path']))
                avg_frame_duration = ((avg_frame_duration * framenum) + sleep_time) / (framenum + 1)
                # Time print
                if LOG_TIMING:
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
                if LOG_TIMING:
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
    if video_list: # For offline mode
        update_camera_status(CameraStatus.VIDEO_LOADED, "load_camera: videos loaded")
    return Response(generate_camera(CAMERA, frame_rate),
        mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_wav(filepath: os.PathLike):
    """Generate audio stream from .wav"""
    with open(filepath, "rb") as fwav:
        data = fwav.read(1024)
        while data:
            if is_playing(CAMERA.status):
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

def get_load_directory() -> tuple:
    """Returns the last copied task directory and the task id, for use in offline loading"""
    # The name of the subdirectory is the task id
    subdirectories = []
    for entry in os.scandir(COPIED_VIDEO_PATH):
        if entry.is_dir():
            subdirectories.append(entry.path)
    if not subdirectories:
        return (COPIED_VIDEO_PATH, None)
    # Order by most recent run
    subdirectories.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return (COPIED_VIDEO_PATH / subdirectories[0], subdirectories[0])

def update_camera_status(new:CameraStatus, label:str=""):
    """Function to handle status change depending on current one"""
    print(f"Update: {CAMERA.status} -> {new} ({label})")
    if CAMERA.status == new:
        return
    if CAMERA.status == CameraStatus.OFF and new != CameraStatus.IDLE:
        print(f"Camera was OFF, switching to IDLE: {CAMERA.status} -> {new}")
        CAMERA.set_status(CameraStatus.IDLE, label)

    if new == CameraStatus.IDLE:
        # Don't return to idle if waiting (video/audio race condition on reload)
        if CAMERA.status == CameraStatus.AUDIO_LOADED or CAMERA.status == CameraStatus.VIDEO_LOADED:
            return
    if CAMERA.status == CameraStatus.IDLE:
        CAMERA.set_status(new, label)
        return
    if new == CameraStatus.AUDIO_LOADED:
        if CAMERA.status == CameraStatus.VIDEO_LOADED:
            CAMERA.set_status(CameraStatus.OFFLINE_PLAY, label)
            return
    if new == CameraStatus.VIDEO_LOADED:
        if CAMERA.status == CameraStatus.AUDIO_LOADED:
            CAMERA.set_status(CameraStatus.OFFLINE_PLAY, label)
            return
    CAMERA.set_status(new, label)

def is_finished(current:CameraStatus):
    """Return if camera is finished in either offline or streaming mode"""
    return current in [CameraStatus.OFFLINE_FINISHED, CameraStatus.STREAM_FINISHED, CameraStatus.STREAM_VIDEO_DONE]

def is_playing(current:CameraStatus):
    """Return if camera is playing in either offline or streaming mode"""
    return current in [CameraStatus.OFFLINE_PLAY, CameraStatus.STREAM_PLAY]


###################
# Flask functions #
###################
app = Flask(__name__)

@app.route('/')
def index():
    """Render main flask page"""
    return render_template('index.html')

###########
# OFFLINE #
###########

@app.route('/load')
def load():
    """Render video load flask page"""
    return render_template('load.html', audioAutoPlay = 'autoplay')

@app.route("/wav_load")
def wav_load():
    """Get audio file and synchronize it to the images being displayed"""
    last_task_dir, last_task_id = get_load_directory()
    wav_file = last_task_dir / "temp.wav"
    if LOG_FLASK:
        print (f"Load wav_file: {wav_file}")
    update_camera_status(CameraStatus.AUDIO_LOADED, "wav_load")
    return Response(generate_wav(last_task_dir / "temp.wav"), mimetype="audio/x-wav")

@app.route('/video_load')
def video_load():
    """Get camera and load existing videos"""
    last_task_dir, last_task_id = get_load_directory()
    if not last_task_id:
        return load_camera([], DEFAULT_FPS)
    avi_dir = last_task_dir / 'avi'
    if LOG_FLASK:
        print (f"Loading videos from subdirectory: {avi_dir}")

    video_files = [
        os.path.join(dirpath,f)
            for (dirpath, dirnames, filenames) in os.walk(avi_dir)
        for f in filenames]
    video_files.sort()
    # Get existing audio file
    wav_file = last_task_dir / "temp.wav"

    audio_duration = get_audio_length(wav_file.as_posix())
    # There might be missing videos. Use last video's index as reference
    last_item_index = get_videofile_index(video_files[-1])
    # Two frames per expected video. Last video only has 1 frame.
    # Synthesized video is shorter than audio length
    VIDFRAMEOFFSET = 1 # Taken empirically
    num_vid_frames  = (last_item_index * 2) + 1 # Video has extra frame
    audio_based_framerate = num_vid_frames / audio_duration
    video_duration  = (num_vid_frames - VIDFRAMEOFFSET) / audio_based_framerate
    video_framerate = num_vid_frames / video_duration

    if LOG_FLASK:
        print (f"Video files: {len(video_files)}. Expected: {last_item_index + 1}. Frames: {num_vid_frames}")
        print (f"audio_based_framerate: {audio_based_framerate}")
        print (f"Audio_duration: {audio_duration}")
        print (f"video_duration: {video_duration}")
        print (f"video_framerate: {video_framerate}")

    return load_camera(video_files, video_framerate)

@app.route("/stop_loaded_videos", methods=['POST'])
def stop_loaded_videos():
    """Called from the `/load` page"""
    CAMERA.set_status(CameraStatus.OFFLINE_FINISHED, "stop_loaded_videos")
    CAMERA.reset()
    return jsonify({'camera': 'Idle', 'mode': 'offline'})

##########
# STREAM #
##########

@app.route('/live')
def live():
    """Render video load flask page"""
    return render_template('live.html', audioAutoPlay = 'autoplay')

@app.route("/wav")
def wav():
    """Get audio file and synchronize it to the images being displayed"""
    audio_task_id = request.args.get('task_id')
    audio_path = COPIED_VIDEO_PATH / audio_task_id
    audio_file = audio_path / "temp.wav"
    print(f"audio_file: {audio_file}")
    return Response(generate_wav(audio_file), mimetype="audio/x-wav")

@app.route('/video_feed')
def video_feed():
    """Get camera with empty video queue while waiting"""
    return load_camera([])

@app.route("/start_streaming", methods=['POST'])
def start_streaming():
    """Called from the `/` HTML page"""
    CAMERA.set_status(CameraStatus.STREAM_PLAY, "start_streaming")
    if LOG_FLASK:
        print(CAMERA)
    return jsonify({'camera': 'Playing', 'mode': 'streaming'})

@app.route("/is_live")
def is_live():
    """While waiting on live, retrieve camera status"""
    return jsonify({
        'camera': json.dumps(CAMERA.status, default=str),
        'task_id': TASK_ID
    })

#################
# Main function #
#################

def main():
    """Main watchdog function to observe files created by heygem-gen-video docker service"""
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
