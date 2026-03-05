# Sentinel — Notas Técnicas

## Stack
- Orquestador: n8n (self-hosted en Hostinger vía EasyPanel)
- LLM: Google Gemini (gemini-2.5-flash vía API)
- Base de datos: Google Sheets (ID: 1xESoA77WP3qDyFvZjJ3MRI1RACo-GzpZ7cW_f3_Ecm0)
- Alertas: Telegram Bot @ElSentinela (chat_id: 5484208881)
- TTS: ElevenLabs (voice: NWqMOQLlMBaUbjKYdhbW, modelo: eleven_multilingual_v2)
- Video: Runway ML (solo legacy — ya no se usa en flujo activo)
- Publicación: YouTube Data API v3
- Microservicio FFmpeg: https://noctisiops-sentinel-video.gpsefe.easypanel.host

## Estado de fases
- Fases 1–10: COMPLETADAS ✓
- Fase 11 (Videos Reales + Lower Thirds + Guion 10min): EN PROGRESO

## Pendiente Fase 11
- Miniaturas YouTube: thumbnails generados pero no llegan a YouTube — debug nodo Upload Thumbnail YT
- Scripts de deploy: update_digest_prompt_v2.py, update_broll_digest.py, update_digest_realvideo.py, update_lower_thirds.py

## Workflows n8n
- Workflow Fase 1: cEhX2JS8PEacZgQm — "Sentinel - Tubería Fáctica"
- Workflow Motor de Video: R0HljXY78MZPa8fa — "Sentinel - Motor de Video"
- Webhook YouTube: https://noctisiops-n8n.gpsefe.easypanel.host/webhook/youtube-sentinel

## Notas técnicas críticas (n8n v2.4.7)
- Google Sheets getAll via API NO funciona → usar $getWorkflowStaticData
- \n dentro de expresiones {{ }} → usar String.fromCharCode(10) en Code nodes
- Telegram: HTTP Request directo al Bot API (no nodo nativo)
- $getWorkflowStaticData('global') persiste entre ejecuciones
- n8n Free: sin $vars, sin enterprise features
- Gemini 2.5-flash: OBLIGATORIO añadir thinkingConfig:{thinkingBudget:0} + maxOutputTokens:4096
- Schedule trigger: re-activar con POST /activate después de cada PUT al workflow
- EasyPanel: hacer Stop + Start manual después de cada deploy (Deploy no reinicia contenedor)
- Code nodes NO tienen acceso a red: $helpers, fetch, require, Buffer — todos bloqueados

## Gemini API
- Key: AIzaSyDdLVHAS9BjhtzPE6fSEoH5i6N_c8WOKNo
- Endpoint: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent

## Daily Digest
- Trigger: cron 0 5 * * * (05:00 UTC = hora Irlanda)
- Guion: 1400-1600 palabras (~10 min), prompt con estructura por secciones
- Videos reales: og:video → Pexels fallback → negro
- Lower thirds ASS: estilo noticiero, DejaVu Sans Bold
- Privacidad: private (revisar manualmente en YouTube Studio)

## Shorts (DESACTIVADOS temporalmente)
- Conexión Alert IF → Limit YouTube desconectada en Fase 1
