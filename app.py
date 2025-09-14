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
    # Tách chuỗi theo dấu ; và làm sạch dữ liệu
    links = [l.strip() for l in link.replace("\n", ";").split(";") if l.strip()]
    
    # Thêm các link đã tách vào hàng đợi
    video_queue.extend(links)
    
    return {
        "message": "Đã thêm thành công các video vào hàng đợi.",
        "queue_length": len(video_queue),
        "added": links
    }


@app.post("/merge")
def merge_videos():
    global video_queue
    if not video_queue:
        return {"error": "Không có video nào trong hàng đợi để ghép."}
    
    downloaded_files = []
    
    try:
        # 1. Tải từng link về (giữ đúng thứ tự)
        for i, link in enumerate(video_queue):
            filename = f"video_{i}.mp4"
            print(f"Downloading: {link} -> {filename}")
            r = requests.get(link, stream=True)
            r.raise_for_status() # Báo lỗi nếu request không thành công (vd: 404)
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_files.append(filename)
        
        # 2. Tạo file list cho ffmpeg
        with open("file_list.txt", "w", encoding="utf-8") as f:
            for file in downloaded_files:
                f.write(f"file '{os.path.abspath(file)}'\n")
        
        # 3. Dùng ffmpeg để merge
        output_file = "merged_video.mp4"
        command = [
            "ffmpeg", 
            "-f", "concat", 
            "-safe", "0", 
            "-i", "file_list.txt", 
            "-c", "copy", 
            output_file,
            "-y" # Ghi đè file output nếu đã tồn tại
        ]
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True) # check=True sẽ báo lỗi nếu ffmpeg chạy không thành công
        
        # Xóa queue
        video_queue = []
        
        # Trả về file trực tiếp
        return FileResponse(output_file, media_type="video/mp4", filename=output_file)

    finally:
        # 4. Luôn dọn dẹp file tạm sau khi hoàn thành hoặc có lỗi
        print("Cleaning up temporary files...")
        for file in downloaded_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists("file_list.txt"):
            os.remove("file_list.txt")


@app.post("/clear")
def clear_queue():
    global video_queue
    video_queue = []
    return {"message": "Đã xóa hàng đợi."}

@app.get("/queue")
def show_queue():
    return {"current_queue": video_queue, "count": len(video_queue)}
