from fastapi import FastAPI
from fastapi.responses import FileResponse
import requests
import os
import subprocess

app = FastAPI()

# Danh sách tạm giữ các video link
video_queue = []

@app.post("/add")
def add_video(link: str):
    global video_queue
    # Tách theo dấu ; hoặc khoảng trắng
    links = [l.strip() for l in link.replace("\n", " ").split(";") if l.strip()]
    video_queue.extend(links)
    return {"message": "Video(s) added", "queue_length": len(video_queue), "added": links}


@app.post("/merge")
def merge_videos():
    global video_queue
    if not video_queue:
        return {"error": "No videos to merge"}
    
    downloaded_files = []
    
    # 1. Tải từng link về (giữ đúng thứ tự)
    for i, link in enumerate(video_queue):
        filename = f"video_{i}.mp4"
        r = requests.get(link)
        with open(filename, "wb") as f:
            f.write(r.content)
        downloaded_files.append(filename)
    
    # 2. Tạo file list cho ffmpeg
    with open("file_list.txt", "w") as f:
        for file in downloaded_files:
            f.write(f"file '{file}'\n")
    
    # 3. Dùng ffmpeg để merge
    output_file = "merged.mp4"
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", 
        "-i", "file_list.txt", "-c", "copy", output_file
    ])
    
    # 4. Xóa queue và file tạm
    video_queue = []
    for file in downloaded_files:
        os.remove(file)
    os.remove("file_list.txt")
    
    # 5. Trả về file trực tiếp
    return FileResponse(output_file, media_type="video/mp4", filename="merged.mp4")

@app.post("/clear")
def clear_queue():
    global video_queue
    video_queue = []
    return {"message": "Queue cleared"}
from fastapi import FastAPI
from fastapi.responses import FileResponse
import requests
import os
import subprocess

app = FastAPI()

# Danh sách tạm giữ các video link
video_queue = []

@app.post("/add")
def add_video(link: str):
    global video_queue
    video_queue.append(link)
    return {"message": "Video link added", "queue_length": len(video_queue)}

@app.post("/merge")
def merge_videos():
    global video_queue
    if not video_queue:
        return {"error": "No videos to merge"}
    
    downloaded_files = []
    
    # 1. Tải từng link về (giữ đúng thứ tự)
    for i, link in enumerate(video_queue):
        filename = f"video_{i}.mp4"
        r = requests.get(link)
        with open(filename, "wb") as f:
            f.write(r.content)
        downloaded_files.append(filename)
    
    # 2. Tạo file list cho ffmpeg
    with open("file_list.txt", "w") as f:
        for file in downloaded_files:
            f.write(f"file '{file}'\n")
    
    # 3. Dùng ffmpeg để merge
    output_file = "merged.mp4"
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", 
        "-i", "file_list.txt", "-c", "copy", output_file
    ])
    
    # 4. Xóa queue và file tạm
    video_queue = []
    for file in downloaded_files:
        os.remove(file)
    os.remove("file_list.txt")
    
    # 5. Trả về file trực tiếp
    return FileResponse(output_file, media_type="video/mp4", filename="merged.mp4")

@app.post("/clear")
def clear_queue():
    global video_queue
    video_queue = []
    return {"message": "Queue cleared"}

