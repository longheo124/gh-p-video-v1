from fastapi import FastAPI, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
import cv2
import os
import requests
import uuid
from typing import List, Dict

app = FastAPI()

# --- Hệ thống quản lý tác vụ nền ---
# Sử dụng dictionary để lưu trạng thái các tác vụ.
# Trong ứng dụng thực tế, nên dùng database hoặc Redis.
tasks: Dict[str, Dict] = {}
# Ví dụ: tasks['some-uuid'] = {"status": "processing", "result_path": None, "error": None}

# --- Các hàm xử lý video (Logic của "đầu bếp") ---

def download_video(url, save_path):
    """Tải video từ URL và lưu vào một file tạm."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        resp = requests.get(url, stream=True, headers=headers, timeout=60) # Tăng timeout tải
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi tải video từ {url}: {e}")
        return None

def cleanup_files(paths: List[str]):
    """Hàm dọn dẹp các file."""
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Đã xóa file: {path}")
            except OSError as e:
                print(f"Lỗi khi xóa file {path}: {e}")

def run_video_merge_task(task_id: str, urls: List[str]):
    """
    Hàm xử lý nền (background task) để ghép video.
    Hàm này sẽ cập nhật trạng thái vào biến `tasks` toàn cục.
    """
    tasks[task_id]["status"] = "processing"
    temp_files = []
    output_filename = f"merged_{task_id}.mp4"

    try:
        # 1. Tải tất cả video
        for url in urls:
            path = f"temp_{uuid.uuid4()}.mp4"
            downloaded_path = download_video(url, path)
            if downloaded_path:
                temp_files.append(downloaded_path)

        if len(temp_files) < 1:
            raise ValueError("Không thể tải bất kỳ video nào.")

        # 2. Chuẩn bị để ghép
        cap_first = cv2.VideoCapture(temp_files[0])
        if not cap_first.isOpened():
            raise IOError(f"Không thể mở video file: {temp_files[0]}")
        
        fps = cap_first.get(cv2.CAP_PROP_FPS) or 30
        width = int(cap_first.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_first.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap_first.release()

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

        # 3. Logic ghép và chuyển cảnh
        last_frame_of_previous_video = None
        for path in temp_files:
            cap = cv2.VideoCapture(path)
            is_first_frame = True
            while True:
                ret, frame = cap.read()
                if not ret:
                    if 'current_frame_resized' in locals():
                        last_frame_of_previous_video = current_frame_resized
                    break
                
                current_frame_resized = cv2.resize(frame, (width, height))

                if is_first_frame and last_frame_of_previous_video is not None:
                    # Tạo chuyển cảnh
                    for i in range(15): # 15 frames transition
                        alpha = (i + 1) / 15
                        blended = cv2.addWeighted(last_frame_of_previous_video, 1 - alpha, current_frame_resized, alpha, 0)
                        out.write(blended)
                
                out.write(current_frame_resized)
                is_first_frame = False
            cap.release()

        out.release()
        
        # 4. Báo thành công
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result_path"] = output_filename

    except Exception as e:
        print(f"[TASK {task_id}] Lỗi: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
    finally:
        # Luôn dọn dẹp file tạm
        cleanup_files(temp_files)


# --- API Endpoints (Giao diện của "nhân viên thu ngân") ---

# Biến tạm để lưu trữ video, vẫn giữ lại để tương thích
video_queue: List[str] = []

@app.get("/")
def root():
    return {"message": "Video Merge API with Background Tasks is running"}

@app.post("/add_video/")
async def add_video(video_url: str = Form(...)):
    if not video_url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="URL không hợp lệ")
    video_queue.append(video_url)
    return {"status": "added", "current_queue_length": len(video_queue)}

@app.post("/clear_queue/")
async def clear_queue():
    video_queue.clear()
    return {"status": "cleared"}

@app.post("/merge_videos/")
async def start_merge_videos(background_tasks: BackgroundTasks):
    """
    Bắt đầu quá trình ghép video trong nền và trả về một task_id.
    """
    if not video_queue:
        raise HTTPException(status_code=400, detail="Queue trống, không có video để ghép")

    task_id = str(uuid.uuid4())
    urls_to_process = list(video_queue)
    video_queue.clear()

    # Khởi tạo trạng thái tác vụ
    tasks[task_id] = {"status": "queued", "result_path": None, "error": None}
    
    # Giao việc cho "đầu bếp"
    background_tasks.add_task(run_video_merge_task, task_id, urls_to_process)

    return {"message": "Yêu cầu ghép video đã được tiếp nhận.", "task_id": task_id}

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Kiểm tra trạng thái của một tác vụ ghép video.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return task

@app.get("/download/{task_id}")
async def download_merged_video(task_id: str, background_tasks: BackgroundTasks):
    """
    Tải về video đã ghép xong.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    
    if task["status"] == "completed" and task["result_path"]:
        file_path = task["result_path"]
        if os.path.exists(file_path):
            # Dọn dẹp file sau khi đã gửi đi
            background_tasks.add_task(cleanup_files, [file_path])
            # Xóa task khỏi bộ nhớ
            del tasks[task_id]
            return FileResponse(file_path, media_type="video/mp4", filename="merged_video.mp4")
        else:
            raise HTTPException(status_code=404, detail="Không tìm thấy file kết quả")
    elif task["status"] == "failed":
        raise HTTPException(status_code=500, detail=f"Tác vụ thất bại: {task['error']}")
    else:
        raise HTTPException(status_code=400, detail=f"Tác vụ đang trong trạng thái: {task['status']}")

