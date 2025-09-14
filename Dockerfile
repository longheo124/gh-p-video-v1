Sử dụng base image Python
FROM python:3.12-slim

Cài lib cần thiết cho OpenCV + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg

Đặt thư mục làm việc
WORKDIR /app

Copy requirements trước để cache install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

Copy toàn bộ code
COPY . .

Lệnh để khởi động ứng dụng. Railway sẽ đọc biến $PORT
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "$PORT"]
