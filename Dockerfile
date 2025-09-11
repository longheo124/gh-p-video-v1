# Sử dụng base image Python chính thức
FROM python:3.12-slim

# Cài đặt các thư viện hệ thống cần thiết cho OpenCV
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# Đặt thư mục làm việc trong container
WORKDIR /app

# Sao chép các tệp yêu cầu và cài đặt chúng
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn ứng dụng
COPY . .

# Chỉ định lệnh để chạy ứng dụng
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]