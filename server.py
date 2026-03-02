@app.route('/process_v2', methods=['POST'])
def process_v2():
    intro_url  = request.form.get('intro_url', '').strip()
    categoria  = request.form.get('categoria', 'default')
    stock_urls = json.loads(request.form.get('stock_urls', '[]'))
    audio_file = (request.files.get('audio') or
                  request.files.get('audio_mp3'))

    if not audio_file:
        return jsonify({'error': 'audio requerido'}), 400

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = os.path.join(tmp, 'audio.mp3')
        audio_file.save(audio_path)

        # Duración del audio
        probe   = subprocess.run(
            ['ffprobe','-v','quiet','-print_format','json',
             '-show_streams', audio_path],
            capture_output=True, text=True)
        streams = json.loads(probe.stdout).get('streams', [])
        audio_duration = float(next(
            (s['duration'] for s in streams if s['codec_type']=='audio'), 30))

        has_intro = bool(intro_url)

        # ── Intro Runway (opcional) ──────────────────────────────
        intro_path = None
        if has_intro:
            intro_path = os.path.join(tmp, 'intro.mp4')
            r = requests.get(intro_url, timeout=60)
            with open(intro_path, 'wb') as f:
                f.write(r.content)
            body_duration = max(1, audio_duration - 10)
        else:
            body_duration = audio_duration   # ← sin intro: todo el audio

        # ── B-Roll ───────────────────────────────────────────────
        broll_path = _build_broll(stock_urls, body_duration, tmp, categoria)

        # ── Concat intro + broll (o solo broll) ─────────────────
        if has_intro and intro_path:
            concat_list = os.path.join(tmp, 'concat.txt')
            with open(concat_list, 'w') as f:
                f.write(f"file '{intro_path}'\nfile '{broll_path}'\n")
            body_video = os.path.join(tmp, 'body.mp4')
            subprocess.run([
                'ffmpeg','-y','-f','concat','-safe','0',
                '-i', concat_list,
                '-c','copy', body_video
            ], check=True)
        else:
            body_video = broll_path   # ← sin intro: broll directamente

        # ── Mezcla audio ────────────────────────────────────────
        out_path = os.path.join(tmp, 'final.mp4')
        audio_offset = 10 if has_intro else 0   # ← delay solo si hay intro
        subprocess.run([
            'ffmpeg','-y',
            '-i', body_video,
            '-i', audio_path,
            '-filter_complex',
                f'[1:a]adelay={audio_offset*1000}|{audio_offset*1000}[aud]',
            '-map','0:v','-map','[aud]',
            '-c:v','copy','-c:a','aac',
            '-shortest', out_path
        ], check=True)

        return send_file(out_path, mimetype='video/mp4',
                         as_attachment=True,
                         download_name='final.mp4')
