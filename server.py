import io, math, json, subprocess, tempfile, requests
from flask import Flask, request, send_file
from PIL import Image, ImageDraw, ImageFont
# sentinel-video v5 — Fase 8A: Short sin Runway

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_audio_duration(audio_path):
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', audio_path],
        capture_output=True, text=True
    )
    return float(probe.stdout.strip())


def _get_video_duration(video_path):
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', video_path],
        capture_output=True, text=True
    )
    try:
        return float(probe.stdout.strip())
    except Exception:
        return 0.0


def _download(url, path):
    r = requests.get(url, stream=True, timeout=120,
                     headers={'User-Agent': 'Mozilla/5.0 Sentinel/3.0'})
    r.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)


def _normalize_clip(src, dst, width=1280, height=720, max_dur=30):
    """Re-encoda clip a resolución objetivo, máx max_dur segundos, sin audio."""
    vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
          f'crop={width}:{height}')
    subprocess.run([
        'ffmpeg', '-y', '-i', src, '-t', str(max_dur),
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-an', dst
    ], check=True, capture_output=True)


def _build_broll(tmp, stock_urls, body_dur, width=1280, height=720):
    """
    Descarga, normaliza y concatena clips de stock para cubrir body_dur segundos.
    Retorna path al broll.mp4 final. Si no hay clips, retorna None (fallback sólido).
    """
    norm_clips = []
    for i, url in enumerate(stock_urls[:4]):
        raw  = f"{tmp}/raw_{i}.mp4"
        norm = f"{tmp}/norm_{i}.mp4"
        try:
            _download(url, raw)
            _normalize_clip(raw, norm, width=width, height=height)
            norm_clips.append(norm)
        except Exception as e:
            print(f"[broll] clip {i} FAILED: {e}")

    if not norm_clips:
        return None  # llamador usará fondo sólido como fallback

    broll_path = f"{tmp}/broll.mp4"

    if len(norm_clips) == 1:
        # Loop de un solo clip
        subprocess.run([
            'ffmpeg', '-y',
            '-stream_loop', '-1', '-i', norm_clips[0],
            '-t', str(body_dur),
            '-c:v', 'libx264', '-preset', 'fast',
            broll_path
        ], check=True, capture_output=True)
        return broll_path

    # Múltiples clips: repetir hasta cubrir body_dur
    single_dur = _get_video_duration(norm_clips[0]) or 20.0
    needed = max(1, math.ceil(body_dur / (single_dur * len(norm_clips))))
    tiled  = (norm_clips * needed)[:12]  # máx 12 segmentos

    concat_txt = f"{tmp}/broll_concat.txt"
    with open(concat_txt, 'w') as f:
        for p in tiled:
            f.write(f"file '{p}'\n")

    subprocess.run([
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', concat_txt,
        '-t', str(body_dur),
        '-c:v', 'libx264', '-preset', 'fast',
        broll_path
    ], check=True, capture_output=True)
    return broll_path


# ---------------------------------------------------------------------------
# Endpoint /process  (legacy — fondo de color sólido, 1280x720)
# ---------------------------------------------------------------------------

@app.route('/process', methods=['POST'])
def process():
    intro_url  = request.form.get('intro_url')
    categoria  = request.form.get('categoria', 'default')
    audio_file = (request.files.get('audio')
                  or request.files.get('audio_mp3')
                  or next(iter(request.files.values()), None))

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


# ---------------------------------------------------------------------------
# Endpoint /process_short  (legacy — fondo sólido, 720x1280 vertical)
# ---------------------------------------------------------------------------

@app.route('/process_short', methods=['POST'])
def process_short():
    intro_url  = request.form.get('intro_url')
    categoria  = request.form.get('categoria', 'default')
    audio_file = (request.files.get('audio')
                  or request.files.get('audio_mp3')
                  or next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    color = BACKGROUNDS.get(categoria, BACKGROUNDS['default'])

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/short.mp4"

        audio_file.save(audio_path)
        _download(intro_url, intro_path)

        raw_duration   = _get_audio_duration(audio_path)
        audio_duration = min(raw_duration, 50.0)
        body_duration  = audio_duration - 10.0

        cmd = [
            'ffmpeg', '-y',
            '-i', intro_path,
            '-f', 'lavfi', '-i', f'color=c={color}:size=720x1280:rate=24',
            '-i', audio_path,
            '-filter_complex',
            f'[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=720:1280[intro_v];'
            f'[1:v]trim=0:{body_duration},setpts=PTS-STARTPTS[body];'
            f'[intro_v][body]concat=n=2:v=1:a=0[v];'
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


# ---------------------------------------------------------------------------
# Endpoint /process_v2  (Fase 6 — B-Roll Pexels, 1280x720)
# ---------------------------------------------------------------------------

@app.route('/process_v2', methods=['POST'])
def process_v2():
    intro_url  = request.form.get('intro_url')
    stock_urls = json.loads(request.form.get('stock_urls', '[]'))
    audio_file = (request.files.get('audio')
                  or request.files.get('audio_mp3')
                  or next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/output_v2.mp4"

        audio_file.save(audio_path)
        _download(intro_url, intro_path)
        duration     = _get_audio_duration(audio_path)
        body_dur     = max(duration - 10.0, 1.0)

        # Intentar construir B-Roll
        broll_path = _build_broll(tmp, stock_urls, body_dur, width=1280, height=720)

        if broll_path:
            # B-Roll disponible: intro + broll + audio con adelay 10s
            cmd = [
                'ffmpeg', '-y',
                '-i', intro_path,
                '-i', broll_path,
                '-i', audio_path,
                '-filter_complex',
                f'[0:v][1:v]concat=n=2:v=1:a=0[v];'
                f'[2:a]adelay=10000:all=1[a]',
                '-map', '[v]', '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                output_path
            ]
        else:
            # Fallback a fondo sólido (igual que /process)
            color = BACKGROUNDS['default']
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


# ---------------------------------------------------------------------------
# Endpoint /process_short_v2  (Fase 6 — B-Roll Pexels, 720x1280 vertical)
# ---------------------------------------------------------------------------

@app.route('/process_short_v2', methods=['POST'])
def process_short_v2():
    intro_url  = request.form.get('intro_url')
    stock_urls = json.loads(request.form.get('stock_urls', '[]'))
    audio_file = (request.files.get('audio')
                  or request.files.get('audio_mp3')
                  or next(iter(request.files.values()), None))

    if not intro_url or not audio_file:
        return {'error': 'Missing intro_url or audio'}, 400

    with tempfile.TemporaryDirectory() as tmp:
        intro_path  = f"{tmp}/intro.mp4"
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/short_v2.mp4"

        audio_file.save(audio_path)
        _download(intro_url, intro_path)

        raw_dur        = _get_audio_duration(audio_path)
        audio_duration = min(raw_dur, 50.0)
        body_dur       = max(audio_duration - 10.0, 1.0)

        broll_path = _build_broll(tmp, stock_urls, body_dur, width=720, height=1280)

        if broll_path:
            cmd = [
                'ffmpeg', '-y',
                '-i', intro_path,
                '-i', broll_path,
                '-i', audio_path,
                '-filter_complex',
                # Intro: crop center 9:16
                f'[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=720:1280[intro_v];'
                # Concat intro + broll
                f'[intro_v][1:v]concat=n=2:v=1:a=0[v];'
                # Audio recortado y desfasado
                f'[2:a]atrim=0:{audio_duration},adelay=10000:all=1[a]',
                '-map', '[v]', '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-t', '60',
                output_path
            ]
        else:
            # Fallback a fondo sólido vertical
            color = BACKGROUNDS['default']
            cmd = [
                'ffmpeg', '-y',
                '-i', intro_path,
                '-f', 'lavfi', '-i', f'color=c={color}:size=720x1280:rate=24',
                '-i', audio_path,
                '-filter_complex',
                f'[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=720:1280[intro_v];'
                f'[1:v]trim=0:{body_dur},setpts=PTS-STARTPTS[body];'
                f'[intro_v][body]concat=n=2:v=1:a=0[v];'
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


# ---------------------------------------------------------------------------
# Endpoint /image/<categoria>  (legacy — sin cambios)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Endpoint /generate_thumbnail  (Fase 7 — 1280x720 JPEG)
# ---------------------------------------------------------------------------

ACCENT_COLORS = {
    'militar':     (30,  60, 120),   # azul acero
    'tecnologia':  (0,  180, 120),   # verde tech
    'conflicto':   (180, 30,  30),   # rojo urgente
    'geopolitica': (180, 120,  0),   # ámbar
    'default':     (220,  50,  50),  # rojo Sentinel
}

FONT_PATHS = [
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/ttf-dejavu/DejaVuSans-Bold.ttf',
]

def _load_font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:3]  # máximo 3 líneas

@app.route('/generate_thumbnail', methods=['POST'])
def generate_thumbnail():
    image_url = request.form.get('image_url', '')
    titulo    = request.form.get('titulo', 'SENTINEL NEWS')
    categoria = request.form.get('categoria', 'default')

    W, H = 1280, 720
    accent = ACCENT_COLORS.get(categoria, ACCENT_COLORS['default'])

    # --- Fondo ---
    try:
        r = requests.get(image_url, timeout=15,
                         headers={'User-Agent': 'Mozilla/5.0 Sentinel/4.0'})
        r.raise_for_status()
        bg = Image.open(io.BytesIO(r.content)).convert('RGB')
        # Crop center 16:9
        bw, bh = bg.size
        if bw / bh > W / H:
            nw = int(bh * W / H)
            bg = bg.crop(((bw - nw) // 2, 0, (bw - nw) // 2 + nw, bh))
        else:
            nh = int(bw * H / W)
            bg = bg.crop((0, (bh - nh) // 2, bw, (bh - nh) // 2 + nh))
        bg = bg.resize((W, H), Image.LANCZOS)
    except Exception:
        bg = Image.new('RGB', (W, H), (15, 15, 25))

    draw = ImageDraw.Draw(bg, 'RGBA')

    # --- Overlay oscuro en parte inferior (45% del alto) ---
    overlay_h = int(H * 0.45)
    draw.rectangle([(0, H - overlay_h), (W, H)], fill=(0, 0, 0, 190))

    # --- Barra de acento superior (8px) ---
    draw.rectangle([(0, 0), (W, 8)], fill=accent)

    # --- Badge de categoría (top-left) ---
    badge_font = _load_font(22)
    badge_text = categoria.upper()
    bx, by = 20, 20
    bpad = 8
    bb = draw.textbbox((bx + bpad, by + bpad), badge_text, font=badge_font)
    draw.rectangle(
        [(bx, by), (bb[2] + bpad, bb[3] + bpad)],
        fill=accent
    )
    draw.text((bx + bpad, by + bpad), badge_text, font=badge_font, fill='white')

    # --- Texto del título ---
    title_font  = _load_font(54)
    margin      = 40
    text_y_base = H - overlay_h + 30
    lines = _wrap_text(titulo, title_font, W - margin * 2, draw)
    line_h = 64
    for i, line in enumerate(lines):
        y = text_y_base + i * line_h
        # Sombra
        draw.text((margin + 2, y + 2), line, font=title_font, fill=(0, 0, 0, 200))
        draw.text((margin, y),         line, font=title_font, fill='white')

    # --- Branding "SENTINEL" bottom-right ---
    brand_font = _load_font(26)
    brand_text = '▶ SENTINEL'
    bb2 = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw2 = bb2[2] - bb2[0]
    draw.text((W - bw2 - 20, H - 38), brand_text,
              font=brand_font, fill=(220, 220, 220, 210))

    # --- Serializar y devolver ---
    out = io.BytesIO()
    bg.convert('RGB').save(out, format='JPEG', quality=92)
    out.seek(0)
    return send_file(out, mimetype='image/jpeg', download_name='thumbnail.jpg')


# ---------------------------------------------------------------------------
# Endpoint /process_short_v3  (Fase 8A — Short sin Runway, B-Roll puro, 720x1280)
# ---------------------------------------------------------------------------

@app.route('/process_short_v3', methods=['POST'])
def process_short_v3():
    """Short vertical sin intro de Runway. Solo B-Roll Pexels + audio ElevenLabs."""
    stock_urls = json.loads(request.form.get('stock_urls', '[]'))
    audio_file = (request.files.get('audio')
                  or request.files.get('audio_mp3')
                  or next(iter(request.files.values()), None))

    if not audio_file:
        return {'error': 'Missing audio'}, 400

    with tempfile.TemporaryDirectory() as tmp:
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/short_v3.mp4"

        audio_file.save(audio_path)
        raw_dur       = _get_audio_duration(audio_path)
        audio_dur     = min(raw_dur, 55.0)

        broll_path = _build_broll(tmp, stock_urls, audio_dur, width=720, height=1280)

        if broll_path:
            cmd = [
                'ffmpeg', '-y',
                '-i', broll_path,
                '-i', audio_path,
                '-filter_complex',
                f'[1:a]atrim=0:{audio_dur}[a]',
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-t', '60',
                output_path
            ]
        else:
            # Fallback: fondo negro liso
            cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', f'color=c=0x0a0a0a:size=720x1280:rate=24',
                '-i', audio_path,
                '-filter_complex',
                f'[0:v]trim=0:{audio_dur},setpts=PTS-STARTPTS[v];'
                f'[1:a]atrim=0:{audio_dur}[a]',
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
                     as_attachment=True, download_name='sentinel_short_v3.mp4')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
