import io, subprocess, tempfile, requests
from flask import Flask, request, send_file
# sentinel-video v2

app = Flask(__name__)

BACKGROUNDS = {
    'militar':     '0x1a1a2e',
    'tecnologia':  '0x0d1117',
    'conflicto':   '0x2d0000',
    'geopolitica': '0x002d00',
    'default':     '0x0a0a0a',
}

@app.route('/health')
def health():
    return {'status': 'ok'}

def _get_audio_duration(audio_path):
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', audio_path],
        capture_output=True, text=True
    )
    return float(probe.stdout.strip())

def _download(url, path):
    r = requests.get(url, stream=True, timeout=120)
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)

@app.route('/process', methods=['POST'])
def process():
    intro_url  = request.form.get('intro_url')
    categoria  = request.form.get('categoria', 'default')
    audio_file = request.files.get('audio') or request.files.get('audio_mp3') or (next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    color = BACKGROUNDS.get(categoria, BACKGROUNDS['default'])

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/output.mp4"

        audio_file.save(audio_path)
        _download(intro_url, intro_path)
        duration = _get_audio_duration(audio_path)

        cmd = [
            'ffmpeg', '-y',
            '-i', intro_path,
            '-f', 'lavfi', '-i', f'color=c={color}:size=1280x720:rate=24',
            '-i', audio_path,
            '-filter_complex',
            f'[1:v]trim=0:{duration},setpts=PTS-STARTPTS[body];'
            f'[0:v][body]concat=n=2:v=1:a=0[v];'
            f'[2:a]adelay=10000:all=1[a]',
            '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(output_path, 'rb') as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype='video/mp4',
                     as_attachment=True, download_name='sentinel.mp4')

@app.route('/process_short', methods=['POST'])
def process_short():
    intro_url  = request.form.get('intro_url')
    categoria  = request.form.get('categoria', 'default')
    audio_file = request.files.get('audio') or request.files.get('audio_mp3') or (next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    color = BACKGROUNDS.get(categoria, BACKGROUNDS['default'])

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/short.mp4"

        audio_file.save(audio_path)
        _download(intro_url, intro_path)

        raw_duration = _get_audio_duration(audio_path)
        # Short: max 50s de audio (10s intro + 40s cuerpo = 50s total)
        audio_duration = min(raw_duration, 50.0)
        body_duration  = audio_duration - 10.0

        cmd = [
            'ffmpeg', '-y',
            '-i', intro_path,
            '-f', 'lavfi', '-i', f'color=c={color}:size=720x1280:rate=24',
            '-i', audio_path,
            '-filter_complex',
            # Intro: crop center 9:16 del clip 16:9
            f'[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=720:1280[intro_v];'
            # Cuerpo: fondo vertical
            f'[1:v]trim=0:{body_duration},setpts=PTS-STARTPTS[body];'
            # Concat intro + cuerpo
            f'[intro_v][body]concat=n=2:v=1:a=0[v];'
            # Audio recortado a audio_duration, desfasado 10s
            f'[2:a]atrim=0:{audio_duration},adelay=10000:all=1[a]',
            '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-t', '60',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(output_path, 'rb') as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype='video/mp4',
                     as_attachment=True, download_name='sentinel_short.mp4')

@app.route('/image/<categoria>')
def get_image(categoria):
    colors = {
        'militar':    '0x0a0f1a',
        'tecnologia': '0x0a1a0f',
        'conflicto':  '0x1a0a0a',
        'geopolitica':'0x0a0a1a',
        'default':    '0x0a0a0f',
    }
    color = colors.get(categoria, colors['default'])
    with tempfile.TemporaryDirectory() as tmp:
        img_path = f"{tmp}/bg.jpg"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'lavfi',
            '-i', f'color=c={color}:size=1280x720',
            '-frames:v', '1', '-q:v', '2', img_path
        ], check=True, capture_output=True)
        with open(img_path, 'rb') as f:
            data = f.read()
    return send_file(io.BytesIO(data), mimetype='image/jpeg')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
