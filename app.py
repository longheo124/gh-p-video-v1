import os
import uuid
import cv2
import requests
import numpy as np
from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Dict, List, Union

app = FastAPI()

# --- Cấu trúc dữ liệu trong bộ nhớ ---
tasks: Dict[str, Dict[str, Union[str, None]]] = {}
video_queues: Dict[str, List[str]] = {}

# --- Hàm xử lý video (Tác vụ nền) ---
def process_video_merge(task_id: str, video_urls: List[str], width: int, height: int, fps: float):
    """Tải, ghép và lưu video. Đây là tác vụ nặng chạy trong nền."""
    temp_files = []
    output_filename = f"{task_id}.mp4"

    try:
        for i, url in enumerate(video_urls):
            temp_path = f"temp_{task_id}_{i}.mp4"
            resp = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            temp_files.append(temp_path)

        if not temp_files:
            tasks[task_id] = {"status": "failed", "result_path": "No videos could be downloaded."}
            return

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))
        
        last_frame_from_prev_video = None

        for idx, path in enumerate(temp_files):
            cap = cv2.VideoCapture(path)
            
            # Xử lý chuyển cảnh
            if idx > 0 and last_frame_from_prev_video is not None:
                ret, first_frame_of_current_video = cap.read()
                if ret:
                    first_frame_resized = cv2.resize(first_frame_of_current_video, (width, height))
                    transition_frames = int(fps) # 1 giây
                    for i in range(transition_frames):
                        alpha = i / transition_frames
                        blended = cv2.addWeighted(last_frame_from_prev_video, 1 - alpha, first_frame_resized, alpha, 0)
                        out.write(blended)
                # Bỏ qua frame đầu tiên đã dùng cho chuyển cảnh
            
            # Ghi các frame còn lại
            current_last_frame = None
            frame_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                # Bỏ qua frame đầu tiên của các video sau vì đã dùng cho transition
                if idx > 0 and frame_count == 0:
                    frame_count += 1
                    current_last_frame = frame
                    continue
                
                out.write(cv2.resize(frame, (width, height)))
                current_last_frame = frame
                frame_count += 1

            if current_last_frame is not None:
                 last_frame_from_prev_video = cv2.resize(current_last_frame, (width, height))

            cap.release()
        
        out.release()
        tasks[task_id] = {"status": "completed", "result_path": output_filename}

    except Exception as e:
        tasks[task_id] = {"status": "failed", "result_path": str(e)}
    finally:
        for path in temp_files:
            if os.path.exists(path):
                os.remove(path)

# --- Endpoints API ---
@app.on_event("startup")
async def startup_event():
    port = os.getenv("PORT", "8000")
    print(f"--- Application starting up on port: {port} ---")

@app.get("/")
def root():
    return {"message": "Video Merge API with Background Tasks is running"}

@app.post("/add_video/")
async def add_video(session_id: str = Form(...), video_url: str = Form(...)):
    if session_id not in video_queues:
        video_queues[session_id] = []
    video_queues[session_id].append(video_url)
    return {"status": "added", "session_id": session_id, "queue_length": len(video_queues[session_id])}

@app.post("/clear_queue/")
async def clear_queue(session_id: str = Form(...)):
    if session_id in video_queues:
        video_queues[session_id] = []
        return {"status": "cleared", "session_id": session_id}
    return {"error": "Session not found", "session_id": session_id}

@app.post("/merge_videos/")
async def merge_videos(session_id: str = Form(...), background_tasks: BackgroundTasks = None):
    if session_id not in video_queues or not video_queues[session_id]:
        return {"error": "Queue for this session is empty or does not exist."}

    video_urls = video_queues[session_id][:]
    video_queues[session_id] = [] # Xóa queue ngay

    try:
        # Tải file đầu tiên để lấy thông số
        temp_probe_path = f"probe_{uuid.uuid4()}.mp4"
        resp = requests.get(video_urls[0], stream=True)
        resp.raise_for_status()
        with open(temp_probe_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        cap = cv2.VideoCapture(temp_probe_path)
        if not cap.isOpened():
             raise ValueError("Cannot open video file to get specs")
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        os.remove(temp_probe_path)
        
        if fps == 0: fps = 30 # Giá trị mặc định nếu không đọc được fps

    except Exception as e:
        return {"error": f"Could not process first video to get specs: {e}"}

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result_path": None}
    
    background_tasks.add_task(process_video_merge, task_id, video_urls, width, height, fps)

    return {"message": "Video merging process started.", "task_id": task_id}

@app.get("/status/{task_id}")
def get_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return task

@app.get("/download/{task_id}")
def download_video(task_id: str, background_tasks: BackgroundTasks = None):
    task = tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    if task["status"] != "completed":
        return {"error": "Task is not completed yet", "status": task["status"]}

    file_path = task["result_path"]
    if not os.path.exists(file_path):
        return {"error": "Result file not found."}
    
    background_tasks.add_task(os.remove, file_path)
    return FileResponse(file_path, media_type="video/mp4", filename=f"merged_{task_id}.mp4")

