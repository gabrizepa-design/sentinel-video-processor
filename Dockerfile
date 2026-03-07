FROM alpine:3.18
RUN apk add --no-cache ffmpeg libass font-dejavu python3 py3-pip
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY server.py .
EXPOSE 3000
CMD ["python3", "server.py"]
RUN pip3 install --no-cache-dir yt-dlp
RUN apk add --no-cache ffmpeg python3 py3-pip libass font-dejavu nodejs
