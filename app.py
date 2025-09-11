from fastapi import FastAPI, Form
from fastapi.responses import StreamingResponse
import cv2
import os
import requests
import numpy as np
from typing import List

app = FastAPI()

# Bộ nhớ tạm giữ danh sách video theo phiên chat
video_queue: List[str] = []

def download_video(url, save_path):
    """Tải video từ URL và lưu vào một file tạm."""
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()  # Kiểm tra lỗi HTTP
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi tải video từ {url}: {e}")
        return None

@app.get("/")
def root():
    return {"message": "Video Queue API đang chạy"}

@app.post("/add_video/")
async def add_video(video_url: str = Form(...)):
    """Thêm link video vào queue"""
    video_queue.append(video_url)
    return {"status": "added", "queue_length": len(video_queue)}

@app.post("/clear_queue/")
async def clear_queue():
    """Xóa toàn bộ queue"""
    global video_queue
    video_queue = []
    return {"status": "cleared"}

@app.post("/merge_videos/")
async def merge_videos():
    """Ghép toàn bộ video trong queue thành 1 video mp4"""
    global video_queue
    
    if not video_queue:
        return {"error": "Queue trống, không có video để ghép"}

    temp_files = []

    # Tải video từ queue
    for i, url in enumerate(video_queue):
        path = f"temp_{i}.mp4"
        downloaded_path = download_video(url, path)
        if downloaded_path:
            temp_files.append(downloaded_path)

    if not temp_files:
        return {"error": "Không thể tải video nào để ghép"}

    # Lấy thông số từ video đầu tiên
    cap0 = cv2.VideoCapture(temp_files[0])
    fps = cap0.get(cv2.CAP_PROP_FPS)
    width = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap0.release()

    # Khởi tạo VideoWriter
    out_path = "merged_output.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    def crossfade_transition(frame1, frame2, duration=15):
        """Tạo hiệu ứng crossfade giữa 2 frame"""
        transition_frames = []
        for i in range(duration):
            alpha = i / duration
            blended = cv2.addWeighted(frame1, 1 - alpha, frame2, alpha, 0)
            transition_frames.append(blended)
        return transition_frames

    prev_last_frame = None

    # Nối video
    for idx, path in enumerate(temp_files):
        cap = cv2.VideoCapture(path)
        last_frame = None
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # Đảm bảo tất cả các khung hình có cùng kích thước
            frame = cv2.resize(frame, (width, height))
            last_frame = frame
            out.write(frame)
        cap.release()

        # Thêm crossfade với video kế tiếp
        if idx < len(temp_files) - 1 and last_frame is not None:
            next_cap = cv2.VideoCapture(temp_files[idx + 1])
            ret, next_frame = next_cap.read()
            if ret:
                next_frame = cv2.resize(next_frame, (width, height))
                transition = crossfade_transition(last_frame, next_frame)
                for f in transition:
                    out.write(f)
            next_cap.release()

    out.release()

    # Xóa file tạm
    for path in temp_files:
        os.remove(path)

    # Xóa queue sau khi merge
    video_queue = []

    return StreamingResponse(open(out_path, "rb"), media_type="video/mp4")
