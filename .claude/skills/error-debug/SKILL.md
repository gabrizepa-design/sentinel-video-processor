# Skill: Error Debug — Diagnóstico de errores en automatizaciones

## Cómo usar esta skill
Cuando tengas un error en n8n (o cualquier automatización), comparte:
1. El mensaje de error exacto (screenshot o texto)
2. En qué nodo ocurrió
3. Qué debería hacer ese nodo

Con eso puedo darte un diagnóstico directo.

---

## Protocolo de diagnóstico (lo que hago internamente)

### Paso 1: Leer el error completo
- No asumir nada antes de leer el mensaje completo
- Buscar: tipo de error, nodo afectado, línea si hay stack trace
- Si el error es genérico ("Something went wrong"), hay que buscar más adentro

### Paso 2: Clasificar el error

| Tipo | Síntomas | Causa más común |
|---|---|---|
| **Parse error** | "Unexpected token", "Unterminated string" | JSON mal formado, respuesta truncada |
| **Empty data** | Campo vacío, `undefined`, `null` | El nodo anterior no devolvió lo esperado |
| **Connection error** | Timeout, ECONNREFUSED, 5xx | Servicio caído, URL incorrecta, timeout corto |
| **Auth error** | 401, 403, "Invalid API key" | Credencial vencida, header faltante, scope incorrecto |
| **Data path error** | "Cannot read property of undefined" | Estás accediendo a un campo que no existe en esa ruta |
| **n8n expression** | "Invalid syntax" en expresión `={{ }}` | `\n` literal, variable mal referenciada, typo |

### Paso 3: Verificar el input del nodo que falló
- ¿El nodo anterior devolvió datos? Revisar output del nodo previo
- ¿La estructura es la que esperas? (`$json.campo` vs `$json.body.campo`)
- ¿Hay items vacíos o el array está vacío?

### Paso 4: Verificar el nodo mismo
- ¿Las expresiones `={{ }}` referencian el nodo correcto?
- ¿La URL/endpoint es correcta?
- ¿Los headers necesarios están presentes?
- ¿El timeout es suficiente?

### Paso 5: Testear en aislamiento
- Desconectar el nodo del flujo y ejecutarlo solo con datos de prueba
- Si pasa: el problema viene del input
- Si falla: el problema es el nodo en sí

---

## Errores conocidos en el stack de Noctis Ops

### n8n v2.4.7
- `\n` en expresiones `={{ }}` → usar `String.fromCharCode(10)` en Code node
- `$getWorkflowStaticData` no disponible como global en task runner → declarar `var staticData = $getWorkflowStaticData('global')` al inicio del Code node
- Google Sheets `getAll` no funciona → usar `$getWorkflowStaticData` como alternativa
- Datos de webhook en `$input.first().json.body` (no directo en `$json`)
- Binary data se pierde en nodos intermedios → re-inyectar desde el nodo original: `$('NombreNodo').first().binary`

### Gemini 2.5-flash
- `finishReason: MAX_TOKENS` con output muy corto → el thinking consume el budget → añadir `thinkingConfig: { thinkingBudget: 0 }` + `maxOutputTokens: 4096`
- Respuesta en `_readableState.buffer` (no en `candidates`) → usar `utf8Decode()` manual
- `guion` puede llegar como array de objetos → usar `extractText()` para normalizar

### ElevenLabs
- Response es binaria → `responseFormat: "file"`, `outputPropertyName: "audio_mp3"`
- Después del nodo, `$json` queda vacío → retomar datos con `$('NombreNodo').first().json`

### FFmpeg microservice (EasyPanel)
- Deploy no reinicia el contenedor → Stop + Start manual después de cada deploy
- Timeout por defecto insuficiente para videos largos → configurar 600-900s en el nodo HTTP

### Runway ML
- Status `THROTTLED` no es error fatal → dejar pasar al loop de polling
- Error vacío con status `FAILED` → causa probable: contenido sensible en el prompt
- Loop infinito si no hay `throw` en `FAILED`/`CANCELLED` → verificar nodo Check Runway Error

---

## Checklist rápido antes de pedir ayuda

- [ ] ¿Leíste el mensaje de error completo?
- [ ] ¿Revisaste el output del nodo anterior?
- [ ] ¿El error siempre pasa o es intermitente?
- [ ] ¿Pasó después de un cambio reciente? ¿Cuál?
- [ ] ¿Probaste ejecutar solo ese nodo con datos de prueba?

Si puedes responder esas 5 preguntas, el diagnóstico es mucho más rápido.
