import io, subprocess, tempfile, requests
from flask import Flask, request, send_file

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

@app.route('/process', methods=['POST'])
def process():
    intro_url = request.form.get('intro_url')
    categoria  = request.form.get('categoria', 'default')
    audio_file = request.files.get('audio') or request.files.get('audio_mp3') or (next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    color = BACKGROUNDS.get(categoria, BACKGROUNDS['default'])

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/output.mp4"

        # Guardar audio subido
        audio_file.save(audio_path)

        # Descargar intro de Runway
        r = requests.get(intro_url, stream=True, timeout=120)
        with open(intro_path, 'wb') as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)

        # Duración del audio
        probe = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', audio_path],
            capture_output=True, text=True
        )
        duration = float(probe.stdout.strip())

        # FFmpeg: intro(10s) + fondo de color + narración desfasada 10s
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)

