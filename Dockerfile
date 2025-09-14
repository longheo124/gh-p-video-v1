1. Base Image
Use an official Python runtime as a parent image
FROM python:3.12-slim

2. System Dependencies
Install system libraries required by OpenCV and ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg

3. Working Directory
Set the working directory in the container
WORKDIR /app

4. Python Dependencies
Copy the requirements file and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

5. Application Code
Copy the local application code to the container's working directory
COPY . .

6. Run the Application
Command to run the app using uvicorn. Railway provides the $PORT environment variable.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "$PORT"]
