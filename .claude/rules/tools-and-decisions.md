# Tools & Decisions

## Evaluación de herramientas
Cuando Gabriel pregunte qué herramienta usar para X:
1. Dar una recomendación directa primero
2. Explicar por qué esa y no otras (sin listar 10 opciones)
3. Si hay trade-offs importantes, mencionarlos brevemente
4. Si no hay suficiente contexto para recomendar, hacer 1 pregunta específica

## Stack actual de Noctis Ops (no recomendar alternativas sin razón)
- Orquestación: n8n (no recomendar Make/Zapier salvo necesidad específica)
- LLM: Gemini 2.5-flash (no cambiar sin motivo)
- Deploy: EasyPanel + GitHub
- Código: VS Code + Claude Code

## Decisiones técnicas
- Cuando se tome una decisión importante, recordar registrarla en decisions/log.md
- Antes de recomendar algo nuevo, verificar si encaja con el stack existente

## Testing y errores
- Cuando Gabriel quiera testear algo: ayudar a diseñar el test mínimo viable
- Cuando haya un error: ir directo a la causa raíz, no a workarounds
- No sugerir reintentar lo mismo si ya falló — buscar la raíz del problema
