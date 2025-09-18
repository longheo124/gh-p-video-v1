from fastapi import FastAPI
from fastapi.responses import FileResponse
import os
import subprocess
import requests

app = FastAPI()
video_queue = []  # Khai báo toàn cục

@app.post("/merge")
def merge_videos(smooth: bool = False):
    global video_queue
    if not video_queue:
        return {"error": "Không có video nào trong hàng đợi để ghép."}

    downloaded_files = []

    def get_duration(file):
        """Lấy độ dài video (giây) bằng ffprobe"""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        try:
            return float(result.stdout.strip())
        except:
            return 0.0

    try:
        # 1. Tải từng link về
        for i, link in enumerate(video_queue):
            filename = f"video_{i}.mp4"
            print(f"Downloading: {link} -> {filename}")
            r = requests.get(link, stream=True)
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_files.append(filename)

        output_file = "merged_video.mp4"

        if not smooth:
            # 🔹 Chế độ ghép nhanh + loại bỏ frame lặp
            with open("file_list.txt", "w", encoding="utf-8") as f:
                for file in downloaded_files:
                    f.write(f"file '{os.path.abspath(file)}'\n")

            command = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", "file_list.txt",
                "-vf", "mpdecimate,setpts=N/FRAME_RATE/TB",
                "-c:a", "copy",
                output_file,
                "-y"
            ]

        else:
            # 🔹 Chế độ mượt: crossfade giữa các clip
            inputs = []
            for file in downloaded_files:
                inputs.extend(["-i", file])

            fade_duration = 1.0  # giây crossfade
            filter_complex = ""
            last_video = "[0:v]"
            last_audio = "[0:a]"

            for i in range(1, len(downloaded_files)):
                dur = get_duration(downloaded_files[i - 1])
                offset = max(dur - fade_duration, 0)

                video_tag = f"[{i}:v]"
                audio_tag = f"[{i}:a]"

                filter_complex += (
                    f"{last_video}{last_audio}{video_tag}{audio_tag}"
                    f"xfade=transition=fade:duration={fade_duration}:offset={offset}[v{i}][a{i}];"
                )

                last_video = f"[v{i}]"
                last_audio = f"[a{i}]"

            filter_complex = filter_complex.rstrip(";")

            command = [
                "ffmpeg",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", last_video,
                "-map", last_audio,
                output_file,
                "-y"
            ]

        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True)

        video_queue = []
        return FileResponse(output_file, media_type="video/mp4", filename=output_file)

    finally:
        print("Cleaning up temporary files...")
        for file in downloaded_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists("file_list.txt"):
            os.remove("file_list.txt")