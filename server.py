import io, math, json, os, random, re, subprocess, tempfile, requests
from flask import Flask, request, send_file
from PIL import Image, ImageDraw, ImageFont
# sentinel-video v5 — Fase 11: Real news videos + B-Roll

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
    import shutil
    ytdlp_path = shutil.which('yt-dlp')
    ytdlp_version = None
    if ytdlp_path:
        try:
            r = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=5)
            ytdlp_version = r.stdout.strip()
        except Exception:
            ytdlp_version = 'error'
    node_path = shutil.which('node')
    node_version = None
    if node_path:
        try:
            nv = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
            node_version = nv.stdout.strip()
        except Exception:
            node_version = 'error'
    return {
        'status': 'ok',
        'version': 'v5.4-diag',
        'ytdlp_installed': ytdlp_path is not None,
        'ytdlp_version': ytdlp_version,
        'node_installed': node_path is not None,
        'node_version': node_version,
        'youtube_api_key_set': bool(YOUTUBE_API_KEY),
        'youtube_api_key_prefix': YOUTUBE_API_KEY[:8] + '...' if YOUTUBE_API_KEY else None,
    }


@app.route('/test-ytdlp')
def test_ytdlp():
    """Test si yt-dlp puede descargar un video de YouTube."""
    import tempfile, time, traceback
    test_url = request.args.get('url', 'https://www.youtube.com/watch?v=U7kJaDVN00s')
    with tempfile.TemporaryDirectory() as tmp:
        out = f"{tmp}/test.mp4"
        t0 = time.time()
        try:
            result = subprocess.run([
                'yt-dlp', '--no-playlist',
                '--format', 'best[ext=mp4][height<=480]/best[height<=480]',
                '--output', out,
                '--socket-timeout', '20',
                '--quiet',
                '--extractor-args', 'youtube:player_client=android',
                test_url
            ], capture_output=True, text=True, timeout=60)
            elapsed = round(time.time() - t0, 1)
            if result.returncode == 0 and os.path.exists(out):
                size = os.path.getsize(out)
                return {'ok': True, 'url': test_url, 'size_bytes': size, 'elapsed_s': elapsed}
            return {'ok': False, 'returncode': result.returncode,
                    'stderr': result.stderr[:500], 'elapsed_s': elapsed}
        except Exception as e:
            return {'ok': False, 'error': traceback.format_exc()[-300:],
                    'elapsed_s': round(time.time() - t0, 1)}


@app.route('/test-broll')
def test_broll():
    """Endpoint de diagnóstico: prueba búsqueda YouTube CC y devuelve resultado."""
    query = request.args.get('q', 'military technology AI')
    import tempfile, traceback
    results = []
    error = None
    try:
        search_url = (
            'https://www.googleapis.com/youtube/v3/search'
            f'?part=snippet&q={requests.utils.quote(query)}'
            '&type=video&videoLicense=creativeCommon&maxResults=3'
            f'&key={YOUTUBE_API_KEY}'
        )
        r = requests.get(search_url, timeout=10)
        data = r.json()
        if 'error' in data:
            error = data['error']
        else:
            for item in data.get('items', []):
                vid = item['id'].get('videoId')
                title = item['snippet']['title']
                results.append({'videoId': vid, 'title': title,
                                'url': f'https://www.youtube.com/watch?v={vid}'})
    except Exception as e:
        error = traceback.format_exc()
    return {'query': query, 'results': results, 'error': error,
            'youtube_api_key_set': bool(YOUTUBE_API_KEY)}


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


def _extract_video_from_article(article_url):
    """Extrae video de un artículo de noticias con estrategia en capas.
    Retorna ('mp4_url', url) | ('ytdlp_url', url) | (None, None)"""
    try:
        r = requests.get(article_url, timeout=15,
                         headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'},
                         allow_redirects=True)
        r.raise_for_status()
        html = r.text  # leer TODO el HTML, no solo 50KB

        # 1. og:video / og:video:url / og:video:secure_url con MP4 directo
        for prop in ['og:video:secure_url', 'og:video:url', 'og:video']:
            ep = re.escape(prop)
            m = re.search(
                r'<meta[^>]+property=["\']' + ep + r'["\'][^>]+content=["\'](https?://[^"\']+\.mp4[^"\']*)["\']',
                html, re.I)
            if not m:
                m = re.search(
                    r'<meta[^>]+content=["\'](https?://[^"\']+\.mp4[^"\']*)["\'][^>]+property=["\']' + ep + r'["\']',
                    html, re.I)
            if m:
                return ('mp4_url', m.group(1))

        # 2. <video> / <source> con src MP4
        for pattern in [
            r'<source[^>]+src=["\'](https?://[^"\']+\.mp4[^"\']*)["\']',
            r'<video[^>]+src=["\'](https?://[^"\']+\.mp4[^"\']*)["\']',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                return ('mp4_url', m.group(1))

        # 3. YouTube iframe embed — muy común en BBC, CNN, Reuters, etc.
        for pattern in [
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube-nocookie\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
            r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                yt_url = f'https://www.youtube.com/watch?v={m.group(1)}'
                print(f'[extract] YouTube embed encontrado: {yt_url}')
                return ('ytdlp_url', yt_url)

        # No se encontró video extraíble — no intentar yt-dlp en URLs de noticias genéricas
        # (Reuters, AP, BBC tienen paywalls/players propietarios que yt-dlp no puede descargar)
        return (None, None)

    except Exception as e:
        print(f'[extract] {article_url[:60]}: {e}')
    return (None, None)


def _ytdlp_download(url, output_path, max_dur=60):
    """Descarga video usando yt-dlp. Retorna True si éxito."""
    try:
        result = subprocess.run([
            'yt-dlp',
            '--no-playlist',
            '--format', 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]',
            '--merge-output-format', 'mp4',
            '--output', output_path,
            '--no-warnings',
            '--quiet',
            '--socket-timeout', '30',
            '--extractor-args', 'youtube:player_client=android',
            url
        ], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
            return True
        print(f'[yt-dlp] FAILED ({url[:60]}): {result.stderr[:200]}')
    except Exception as e:
        print(f'[yt-dlp] error: {e}')
    return False


YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')


def _search_youtube_broll(query, tmp, width=1280, height=720, max_clips=3):
    """Busca videos CC en YouTube y descarga los primeros max_clips resultados.
    Retorna lista de paths a clips normalizados. Requiere YOUTUBE_API_KEY env var."""
    if not YOUTUBE_API_KEY or not query:
        return []

    try:
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'videoLicense': 'creativeCommon',
                'maxResults': max_clips + 2,  # pedir de más por si alguno falla
                'videoDuration': 'medium',    # 4-20 min — clips usables
                'order': 'relevance',
                'key': YOUTUBE_API_KEY,
            },
            timeout=15
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
    except Exception as e:
        print(f'[yt-search] API error: {e}')
        return []

    clips = []
    for i, item in enumerate(items):
        if len(clips) >= max_clips:
            break
        vid_id = item.get('id', {}).get('videoId')
        if not vid_id:
            continue
        yt_url = f'https://www.youtube.com/watch?v={vid_id}'
        raw  = f"{tmp}/yt_broll_raw_{i}.mp4"
        norm = f"{tmp}/yt_broll_norm_{i}.mp4"
        try:
            if not _ytdlp_download(yt_url, raw):
                continue
            _normalize_clip(raw, norm, width=width, height=height, max_dur=30)
            dur = _get_video_duration(norm)
            if dur > 1.0:
                clips.append(norm)
                title = item.get('snippet', {}).get('title', '')[:50]
                print(f'[yt-broll] clip {i} OK: {title} ({dur:.0f}s)')
        except Exception as e:
            print(f'[yt-broll] clip {i} FAILED: {e}')

    return clips


def _extract_real_videos(article_urls, tmp, width=1280, height=720, max_per_article=60):
    """Para cada URL de articulo, extrae y normaliza el video real.
    Estrategia: MP4 directo → YouTube embed → yt-dlp en el artículo.
    Retorna lista de paths a clips normalizados (puede estar vacía)."""
    clips = []
    for i, url in enumerate(article_urls):
        if not url or not url.startswith('http'):
            continue
        vtype, vval = _extract_video_from_article(url)
        if not vtype:
            continue
        raw  = f"{tmp}/real_raw_{i}.mp4"
        norm = f"{tmp}/real_norm_{i}.mp4"
        try:
            if vtype == 'mp4_url':
                _download(vval, raw)
                if os.path.getsize(raw) < 50000:
                    continue
            elif vtype == 'ytdlp_url':
                if not _ytdlp_download(vval, raw, max_dur=max_per_article):
                    continue
            _normalize_clip(raw, norm, width=width, height=height, max_dur=max_per_article)
            dur = _get_video_duration(norm)
            if dur > 1.0:
                clips.append(norm)
                print(f'[real] clip {i} OK via {vtype}: {vval[:60]} ({dur:.0f}s)')
        except Exception as e:
            print(f'[real] clip {i} FAILED: {e}')
    return clips


def _fmt_ass_time(seconds):
    """Convierte segundos a formato ASS: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _create_lower_thirds_ass(subtitles, total_dur, width=1280, height=720, vertical=False):
    """Genera archivo ASS con lower thirds estilo noticiero.
    subtitles: lista de strings con datos clave.
    Retorna contenido ASS como string."""
    if not subtitles:
        return None

    # Fuente y tamaño segun orientacion
    font_size = 28 if not vertical else 24
    margin_v = 40 if not vertical else 60
    margin_l = 30
    margin_r = 30

    # Colores ASS: &HAABBGGRR (alpha, blue, green, red)
    # PrimaryColour: blanco, OutlineColour: negro, BackColour: fondo semi-transparente oscuro
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: LowerThird,DejaVu Sans,{font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&HC0000000,"
        "1,0,0,0,100,100,1,0,3,2,0,"
        f"1,{margin_l},{margin_r},{margin_v},1\n"
        f"Style: Accent,DejaVu Sans,{font_size},"
        "&H0000BFFF,&H000000FF,&H00000000,&HC0000000,"
        "1,0,0,0,100,100,1,0,3,2,0,"
        f"1,{margin_l},{margin_r},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []
    n = len(subtitles)
    # Empezar a los 15s (despues del cold open), terminar 15s antes del final
    start_offset = 15.0
    end_offset = total_dur - 15.0
    if end_offset <= start_offset:
        start_offset = 5.0
        end_offset = total_dur - 5.0

    usable = end_offset - start_offset
    interval = usable / n
    show_dur = min(interval - 1.0, 7.0)  # cada uno visible 5-7s con 1s de gap

    for i, text in enumerate(subtitles):
        t_start = start_offset + i * interval
        t_end = t_start + show_dur
        # Sanitizar texto para ASS (sin llaves, sin newlines)
        clean = text.replace('{', '(').replace('}', ')').replace('\n', ' ').strip()
        # Alternar estilo: datos con numeros en color acento
        style = 'LowerThird'
        if any(c.isdigit() for c in clean):
            style = 'Accent'
        events.append(
            f"Dialogue: 0,{_fmt_ass_time(t_start)},{_fmt_ass_time(t_end)},{style},,0,0,0,,"
            f"{{\\an1}}{clean}\n"
        )

    return header + ''.join(events)


def _normalize_clip(src, dst, width=1280, height=720, max_dur=30):
    """Re-encoda clip a resolución objetivo, máx max_dur segundos, sin audio."""
    vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
          f'crop={width}:{height}')
    subprocess.run([
        'ffmpeg', '-y', '-i', src, '-t', str(max_dur),
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-r', '24', '-pix_fmt', 'yuv420p',
        '-an', dst
    ], check=True, capture_output=True)


def _build_broll(tmp, stock_urls, body_dur, width=1280, height=720, max_clips=4):
    """
    Descarga, normaliza y concatena clips de stock para cubrir body_dur segundos.
    Retorna path al broll.mp4 final. Si no hay clips, retorna None (fallback sólido).
    max_clips=4 para videos cortos, usar 12+ para Daily Digest.
    """
    norm_clips = []
    for i, url in enumerate(stock_urls[:max_clips]):
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
            '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
            broll_path
        ], check=True, capture_output=True)
        return broll_path

    # Múltiples clips: repetir en orden aleatorio hasta cubrir body_dur
    single_dur = _get_video_duration(norm_clips[0]) or 20.0
    total_clip_dur = single_dur * len(norm_clips)
    needed = max(1, math.ceil(body_dur / total_clip_dur))
    # Shuffle cada ronda para que la repetición no sea obvia
    tiled = []
    for _ in range(needed):
        batch = list(norm_clips)
        random.shuffle(batch)
        tiled.extend(batch)

    concat_txt = f"{tmp}/broll_concat.txt"
    with open(concat_txt, 'w') as f:
        for p in tiled:
            f.write(f"file '{p}'\n")

    subprocess.run([
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', concat_txt,
        '-t', str(body_dur),
        '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
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
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
    'militar':     ( 30,  60, 120),  # azul acero
    'tecnologia':  ( 41, 128, 185),  # azul tech #2980B9
    'conflicto':   (192,  57,  43),  # rojo #C0392B
    'geopolitica': (180, 120,   0),  # ámbar
    'diplomacia':  ( 39, 174,  96),  # verde #27AE60
    'otro':        (127, 140, 141),  # gris #7F8C8D
    'default':     (220,  50,  50),  # rojo Sentinel
}

FONT_PATHS = [
    '/tmp/DejaVuSans-Bold.ttf',                                        # descargada en runtime
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/ttf-dejavu/DejaVuSans-Bold.ttf',
]

_FONT_URLS = [
    'https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts@master/ttf/DejaVuSans-Bold.ttf',
    'https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf',
]

def _ensure_font():
    """Descarga DejaVuSans-Bold a /tmp si no existe en ninguna ruta del sistema."""
    cached = '/tmp/DejaVuSans-Bold.ttf'
    if os.path.exists(cached):
        return
    for path in FONT_PATHS[1:]:
        if os.path.exists(path):
            return
    import urllib.request
    for url in _FONT_URLS:
        try:
            urllib.request.urlretrieve(url, cached)
            if os.path.getsize(cached) > 10000:  # verifica descarga real
                return
        except Exception:
            continue

_ensure_font()  # ejecutar una vez al arrancar el módulo

def _load_font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    # Pillow >= 10.0.0 soporta size en load_default
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
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
    image_url       = request.form.get('image_url', '')
    titulo          = request.form.get('titulo', 'SENTINEL NEWS')
    texto_miniatura = request.form.get('texto_miniatura', '').strip()
    categoria       = request.form.get('categoria', 'default')

    # Fallback: si no viene texto_miniatura, usar las primeras 4 palabras del título
    if not texto_miniatura:
        clean_words = [w for w in titulo.split() if not w.startswith('#') and len(w) > 1]
        texto_miniatura = ' '.join(clean_words[:4]).upper()

    W, H = 1280, 720
    accent = ACCENT_COLORS.get(categoria, ACCENT_COLORS['default'])

    # --- Fondo ---
    try:
        r = requests.get(image_url, timeout=15,
                         headers={'User-Agent': 'Mozilla/5.0 Sentinel/4.0'})
        r.raise_for_status()
        bg = Image.open(io.BytesIO(r.content)).convert('RGB')
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

    # --- Overlay oscuro sobre toda la imagen (legibilidad) ---
    draw.rectangle([(0, 0), (W, H)], fill=(0, 0, 0, 120))

    # --- Gradiente extra en zona inferior (badge + branding) ---
    draw.rectangle([(0, H - 120), (W, H)], fill=(0, 0, 0, 160))

    # --- Barra de acento superior (6px) ---
    draw.rectangle([(0, 0), (W, 6)], fill=accent)

    # --- Badge de categoría (top-left) ---
    badge_font = _load_font(22)
    badge_text = categoria.upper()
    bx, by = 20, 20
    bpad = 8
    bb = draw.textbbox((bx + bpad, by + bpad), badge_text, font=badge_font)
    draw.rectangle([(bx, by), (bb[2] + bpad, bb[3] + bpad)], fill=accent)
    draw.text((bx + bpad, by + bpad), badge_text, font=badge_font, fill='white')

    # --- TEXTO_MINIATURA centrado, 96px, con stroke negro 3px ---
    main_font = _load_font(96)
    margin = 60
    lines = _wrap_text(texto_miniatura, main_font, W - margin * 2, draw)
    lines = lines[:2]  # máximo 2 líneas
    line_h = 110
    total_text_h = len(lines) * line_h
    y_start = (H - total_text_h) // 2 - 10  # ligeramente arriba del centro

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=main_font)
        text_w = bbox[2] - bbox[0]
        x = (W - text_w) // 2
        y = y_start + i * line_h
        # Stroke negro 3px (8 direcciones) para máxima legibilidad sobre cualquier fondo
        stroke = 3
        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=main_font, fill=(0, 0, 0, 255))
        # Texto principal blanco
        draw.text((x, y), line, font=main_font, fill='white')

    # --- Branding "▶ SENTINEL" bottom-right ---
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
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
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                '-t', '60',
                output_path
            ]

        subprocess.run(cmd, check=True, capture_output=True)

        with open(output_path, 'rb') as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype='video/mp4',
                     as_attachment=True, download_name='sentinel_short_v3.mp4')


# ---------------------------------------------------------------------------
# Endpoint /process_short_v4  (og:image como fondo principal + fallback Pexels)
# ---------------------------------------------------------------------------

@app.route('/process_short_v4', methods=['POST'])
def process_short_v4():
    """Short vertical 720x1280 con lower thirds.
    Prioridad: 0) og:video/yt-dlp del artículo → 1) YouTube CC broll → 2) Pexels → 3) negro."""
    og_video_url     = request.form.get('og_video_url', '').strip()
    article_url      = request.form.get('article_url', '').strip()  # URL del artículo para yt-dlp
    image_url        = request.form.get('image_url', '').strip()
    stock_urls       = json.loads(request.form.get('stock_urls', '[]'))
    subtitulos_clave = json.loads(request.form.get('subtitulos_clave', '[]'))
    broll_query      = request.form.get('broll_query', '').strip()
    audio_file       = (request.files.get('audio')
                        or request.files.get('audio_mp3')
                        or next(iter(request.files.values()), None))

    if not audio_file:
        return {'error': 'Missing audio'}, 400

    with tempfile.TemporaryDirectory() as tmp:
        audio_path  = f"{tmp}/audio.mp3"
        output_path = f"{tmp}/short_v4.mp4"

        audio_file.save(audio_path)
        raw_dur   = _get_audio_duration(audio_path)
        audio_dur = min(raw_dur, 55.0)

        video_input = None

        # 0a. og:video URL explícita (MP4 directo)
        if og_video_url:
            try:
                vid_raw  = f"{tmp}/og_video_raw.mp4"
                vid_norm = f"{tmp}/og_video_norm.mp4"
                resp = requests.get(og_video_url, timeout=15,
                                    headers={'User-Agent': 'Mozilla/5.0 Sentinel/4.0'})
                resp.raise_for_status()
                if len(resp.content) > 50000:
                    with open(vid_raw, 'wb') as fh:
                        fh.write(resp.content)
                    _normalize_clip(vid_raw, vid_norm, width=720, height=1280, max_dur=60)
                    norm_dur = _get_video_duration(vid_norm)
                    if norm_dur > 1.0:
                        if norm_dur >= audio_dur:
                            video_input = vid_norm
                        else:
                            vid_loop = f"{tmp}/og_video_loop.mp4"
                            subprocess.run([
                                'ffmpeg', '-y', '-stream_loop', '-1', '-i', vid_norm,
                                '-t', str(audio_dur),
                                '-c:v', 'libx264', '-preset', 'fast',
                                '-r', '24', '-pix_fmt', 'yuv420p', vid_loop
                            ], check=True, capture_output=True)
                            video_input = vid_loop
                        print(f'[short] og:video directo OK')
            except Exception as e:
                print(f'[short] og:video falló ({e}), intentando extracción del artículo')

        # 0b. Extracción profunda del artículo (YouTube embed / yt-dlp)
        if not video_input and article_url:
            vtype, vval = _extract_video_from_article(article_url)
            if vtype == 'ytdlp_url':
                vid_raw  = f"{tmp}/article_raw.mp4"
                vid_norm = f"{tmp}/article_norm.mp4"
                try:
                    if _ytdlp_download(vval, vid_raw):
                        _normalize_clip(vid_raw, vid_norm, width=720, height=1280, max_dur=60)
                        norm_dur = _get_video_duration(vid_norm)
                        if norm_dur > 1.0:
                            if norm_dur >= audio_dur:
                                video_input = vid_norm
                            else:
                                vid_loop = f"{tmp}/article_loop.mp4"
                                subprocess.run([
                                    'ffmpeg', '-y', '-stream_loop', '-1', '-i', vid_norm,
                                    '-t', str(audio_dur),
                                    '-c:v', 'libx264', '-preset', 'fast',
                                    '-r', '24', '-pix_fmt', 'yuv420p', vid_loop
                                ], check=True, capture_output=True)
                                video_input = vid_loop
                            print(f'[short] yt-dlp artículo OK')
                except Exception as e:
                    print(f'[short] yt-dlp artículo falló: {e}')

        # 1. YouTube CC B-Roll por keywords
        if not video_input and broll_query and YOUTUBE_API_KEY:
            yt_clips = _search_youtube_broll(broll_query, tmp, width=720, height=1280, max_clips=2)
            if yt_clips:
                broll_path = _build_broll(tmp, [], audio_dur, width=720, height=1280, max_clips=0) or None
                concat_txt = f"{tmp}/yt_short_concat.txt"
                with open(concat_txt, 'w') as f:
                    needed = max(1, math.ceil(audio_dur / (sum(_get_video_duration(c) for c in yt_clips) or 1)))
                    for _ in range(needed):
                        for p in yt_clips:
                            f.write(f"file '{p}'\n")
                yt_broll_path = f"{tmp}/yt_short_broll.mp4"
                subprocess.run([
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt,
                    '-t', str(audio_dur),
                    '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
                    yt_broll_path
                ], check=True, capture_output=True)
                video_input = yt_broll_path
                print(f'[short] YouTube CC broll OK')

        # 2. Pexels fallback
        if not video_input:
            broll_path = _build_broll(tmp, stock_urls, audio_dur, width=720, height=1280)
            if broll_path:
                video_input = broll_path

        # 3. Construir video base sin audio
        video_raw = f"{tmp}/short_raw.mp4"
        if video_input:
            subprocess.run([
                'ffmpeg', '-y', '-i', video_input,
                '-t', '60',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-r', '24', '-pix_fmt', 'yuv420p', '-an', video_raw
            ], check=True, capture_output=True)
        else:
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=0x0a0a0a:size=720x1280:rate=24',
                '-t', str(audio_dur), '-pix_fmt', 'yuv420p', video_raw
            ], check=True, capture_output=True)

        # 4. Quemar lower thirds si hay subtitulos
        ass_content = _create_lower_thirds_ass(subtitulos_clave, audio_dur, 720, 1280, vertical=True)
        video_final = video_raw
        if ass_content:
            ass_path = f"{tmp}/subs_short.ass"
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            video_with_subs = f"{tmp}/short_subs.mp4"
            ass_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
            try:
                subprocess.run([
                    'ffmpeg', '-y', '-i', video_raw,
                    '-vf', f"ass={ass_escaped}",
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                    '-r', '24', '-pix_fmt', 'yuv420p', '-an', video_with_subs
                ], check=True, capture_output=True)
                video_final = video_with_subs
                print(f'[short] lower thirds burned OK ({len(subtitulos_clave)} subs)')
            except subprocess.CalledProcessError as e:
                print(f'[short] ASS subtitle burn FAILED: {e.stderr[:200] if e.stderr else ""}')
                print('[short] continuing without subtitles')

        # 5. Mezclar video + audio
        subprocess.run([
            'ffmpeg', '-y',
            '-i', video_final,
            '-i', audio_path,
            '-filter_complex', f'[1:a]atrim=0:{audio_dur}[a]',
            '-map', '0:v', '-map', '[a]',
            '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            '-t', '60',
            output_path
        ], check=True, capture_output=True)

        with open(output_path, 'rb') as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype='video/mp4',
                     as_attachment=True, download_name='sentinel_short_v4.mp4')


# ---------------------------------------------------------------------------
# Endpoint /process_digest  (Fase 8B — Daily Digest, B-Roll puro, sin límite, 1280x720)
# ---------------------------------------------------------------------------

@app.route('/process_digest', methods=['POST'])
def process_digest():
    """Daily Digest v4: real videos + YouTube CC broll + Pexels fallback + lower thirds, max 14 min. 1280x720."""
    stock_urls       = json.loads(request.form.get('stock_urls', '[]'))
    article_urls     = json.loads(request.form.get('article_urls', '[]'))
    subtitulos_clave = json.loads(request.form.get('subtitulos_clave', '[]'))
    broll_query      = request.form.get('broll_query', '').strip()  # keywords para YouTube CC search
    audio_file       = (request.files.get('audio')
                        or request.files.get('audio_mp3')
                        or next(iter(request.files.values()), None))

    if not audio_file:
        return {'error': 'Missing audio'}, 400

    MAX_DURATION = 840.0  # 14 minutos — safe para YouTube sin verificar

    with tempfile.TemporaryDirectory() as tmp:
        audio_path  = f"{tmp}/audio.mp3"
        video_raw   = f"{tmp}/video_raw.mp4"
        output_path = f"{tmp}/digest.mp4"

        audio_file.save(audio_path)
        audio_dur = min(_get_audio_duration(audio_path), MAX_DURATION)

        # 1. Intentar videos reales de las noticias (max 60s cada uno)
        real_clips = _extract_real_videos(article_urls, tmp, width=1280, height=720, max_per_article=60)
        real_dur = sum(_get_video_duration(c) for c in real_clips)
        print(f'[digest] {len(real_clips)} real clips, {real_dur:.0f}s total')

        # 2. Calcular cuanto falta cubrir con B-roll
        remaining = audio_dur - real_dur
        pexels_clips = []
        if remaining > 5.0:
            # 2a. Primero intentar YouTube CC (más relevante que Pexels)
            if broll_query and YOUTUBE_API_KEY:
                yt_clips = _search_youtube_broll(broll_query, tmp, width=1280, height=720, max_clips=4)
                if yt_clips:
                    yt_broll = _build_broll(tmp, [], remaining, width=1280, height=720, max_clips=0)
                    # Concatenar clips de YouTube directamente
                    concat_txt = f"{tmp}/yt_concat.txt"
                    with open(concat_txt, 'w') as f:
                        needed = max(1, math.ceil(remaining / (sum(_get_video_duration(c) for c in yt_clips) or 1)))
                        for _ in range(needed):
                            batch = list(yt_clips)
                            random.shuffle(batch)
                            for p in batch:
                                f.write(f"file '{p}'\n")
                    yt_broll_path = f"{tmp}/yt_broll_final.mp4"
                    subprocess.run([
                        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt,
                        '-t', str(remaining),
                        '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
                        yt_broll_path
                    ], check=True, capture_output=True)
                    pexels_clips = [yt_broll_path]
                    print(f'[digest] YouTube CC broll OK: {remaining:.0f}s cubiertos')

            # 2b. Fallback a Pexels si YouTube no funcionó
            if not pexels_clips and stock_urls:
                broll_path = _build_broll(tmp, stock_urls, remaining, width=1280, height=720, max_clips=12)
                if broll_path:
                    pexels_clips = [broll_path]
                    print(f'[digest] Pexels broll fallback usado')

        # 3. Construir video base (sin audio, sin subs)
        all_clips = real_clips + pexels_clips
        if not all_clips:
            # Fondo negro
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=0x0a0a0a:size=1280x720:rate=24',
                '-t', str(audio_dur), '-pix_fmt', 'yuv420p', video_raw
            ], check=True, capture_output=True)
        elif len(all_clips) == 1:
            # Copiar o trim al tamanio correcto
            subprocess.run([
                'ffmpeg', '-y', '-i', all_clips[0],
                '-t', str(audio_dur),
                '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
                '-an', video_raw
            ], check=True, capture_output=True)
        else:
            concat_txt = f"{tmp}/digest_concat.txt"
            with open(concat_txt, 'w') as f:
                for p in all_clips:
                    f.write(f"file '{p}'\n")
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0', '-i', concat_txt,
                '-t', str(audio_dur),
                '-c:v', 'libx264', '-preset', 'fast', '-r', '24', '-pix_fmt', 'yuv420p',
                '-an', video_raw
            ], check=True, capture_output=True)

        # 4. Quemar lower thirds si hay subtitulos
        ass_content = _create_lower_thirds_ass(subtitulos_clave, audio_dur, 1280, 720)
        video_final = video_raw
        if ass_content:
            ass_path = f"{tmp}/subs.ass"
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            video_with_subs = f"{tmp}/video_subs.mp4"
            ass_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
            try:
                subprocess.run([
                    'ffmpeg', '-y',
                    '-i', video_raw,
                    '-vf', f"ass={ass_escaped}",
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                    '-r', '24', '-pix_fmt', 'yuv420p',
                    '-an', video_with_subs
                ], check=True, capture_output=True)
                video_final = video_with_subs
                print(f'[digest] lower thirds burned OK ({len(subtitulos_clave)} subs)')
            except subprocess.CalledProcessError as e:
                print(f'[digest] ASS subtitle burn FAILED (libass missing?): {e.stderr[:200] if e.stderr else ""}')
                print('[digest] continuing without subtitles')

        # 5. Mezclar video + audio
        subprocess.run([
            'ffmpeg', '-y',
            '-i', video_final,
            '-i', audio_path,
            '-filter_complex', f'[1:a]atrim=0:{audio_dur}[a]',
            '-map', '0:v', '-map', '[a]',
            '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            output_path
        ], check=True, capture_output=True)

        with open(output_path, 'rb') as f:
            data = f.read()

    return send_file(io.BytesIO(data), mimetype='video/mp4',
                     as_attachment=True, download_name='sentinel_digest.mp4')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
