FROM alpine:3.18
RUN apk add --no-cache ffmpeg libass font-dejavu python3 py3-pip nodejs
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir yt-dlp
COPY server.py .
EXPOSE 3000
CMD ["python3", "server.py"]
