FROM alpine:3.18
RUN apk add --no-cache ffmpeg python3 py3-pip
RUN pip3 install flask requests --break-system-packages
WORKDIR /app
COPY server.py .
COPY requirements.txt .
EXPOSE 3000
CMD ["python3", "server.py"]
