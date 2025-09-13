from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import FileResponse
import cv2
import os
import requests
import uuid
from typing import List

app = FastAPI()

# Sử dụng dictionary để quản lý queue theo từng session/user nếu cần
# Ở đây ta vẫn giữ đơn giản với một queue toàn cục
video_queue: List[str] = []

def download_video(url, save_path):
    """Tải video từ URL và lưu vào một file tạm."""
    try:
        # User-Agent để tránh bị một số host chặn
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        resp = requests.get(url, stream=True, headers=headers, timeout=30)
        resp.raise_for_status()  # Kiểm tra lỗi HTTP
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi tải video từ {url}: {e}")
        return None

def cleanup_files(paths: List[str]):
    """Hàm dọn dẹp các file tạm."""
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Đã xóa file: {path}")
            except OSError as e:
                print(f"Lỗi khi xóa file {path}: {e}")

@app.get("/")
def root():
    return {"message": "Video Queue API đang chạy"}

@app.post("/add_video/")
async def add_video(video_url: str = Form(...)):
    """Thêm link video vào queue"""
    if not video_url.startswith(('http://', 'https://')):
        return {"error": "URL không hợp lệ"}
    video_queue.append(video_url)
    return {"status": "added", "current_queue": video_queue}

@app.post("/clear_queue/")
async def clear_queue():
    """Xóa toàn bộ queue"""
    video_queue.clear()
    return {"status": "cleared"}

@app.post("/merge_videos/")
async def merge_videos(background_tasks: BackgroundTasks):
    """
    Ghép toàn bộ video trong queue thành 1 video mp4 với hiệu ứng chuyển cảnh.
    LƯU Ý: Vẫn có thể bị timeout trên các nền tảng miễn phí nếu video dài.
    """
    if not video_queue:
        return {"error": "Queue trống, không có video để ghép"}

    output_filename = f"merged_{uuid.uuid4()}.mp4"
    urls_to_process = list(video_queue)
    video_queue.clear()

    temp_files = []
    try:
        for i, url in enumerate(urls_to_process):
            path = f"temp_{uuid.uuid4()}.mp4"
            downloaded_path = download_video(url, path)
            if downloaded_path:
                temp_files.append(downloaded_path)

        if len(temp_files) < 1:
            return {"error": "Không thể tải bất kỳ video nào để ghép."}

        cap_first = cv2.VideoCapture(temp_files[0])
        if not cap_first.isOpened():
            cleanup_files(temp_files)
            return {"error": f"Không thể mở video đầu tiên: {temp_files[0]}"}
            
        fps = cap_first.get(cv2.CAP_PROP_FPS)
        width = int(cap_first.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_first.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap_first.release()
        
        if fps == 0: fps = 30

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

        # --- Logic Crossfade mượt mà đã được tối ưu ---
        def create_crossfade_frames(frame1, frame2, num_frames=15):
            """Tạo ra các frame chuyển cảnh bằng cách hòa trộn 2 frame."""
            faded_frames = []
            for i in range(num_frames):
                alpha = (i + 1) / num_frames
                blended = cv2.addWeighted(frame1, 1 - alpha, frame2, alpha, 0)
                faded_frames.append(blended)
            return faded_frames

        last_frame_of_previous_video = None

        for idx, path in enumerate(temp_files):
            cap = cv2.VideoCapture(path)
            is_first_frame_of_current_video = True
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    # Lưu lại frame cuối cùng trước khi kết thúc video
                    if 'current_frame_resized' in locals():
                        last_frame_of_previous_video = current_frame_resized
                    break
                
                current_frame_resized = cv2.resize(frame, (width, height))

                if is_first_frame_of_current_video and last_frame_of_previous_video is not None:
                    # Đây là video thứ 2 trở đi. Tạo hiệu ứng chuyển cảnh
                    transition_frames = create_crossfade_frames(last_frame_of_previous_video, current_frame_resized)
                    for f in transition_frames:
                        out.write(f)
                    is_first_frame_of_current_video = False
                else:
                    # Đây là video đầu tiên, hoặc các frame sau của các video tiếp theo
                    out.write(current_frame_resized)
                    is_first_frame_of_current_video = False
            
            cap.release()
        
        out.release()
        
        background_tasks.add_task(cleanup_files, [output_filename])
        return FileResponse(output_filename, media_type="video/mp4", filename="merged_video.mp4")

    except Exception as e:
        print(f"Đã có lỗi nghiêm trọng xảy ra: {e}")
        return {"error": "Đã có lỗi xảy ra trong quá trình ghép video."}
    finally:
        cleanup_files(temp_files)

