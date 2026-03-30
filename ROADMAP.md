# Capability OS — Roadmap

## Mejoras identificadas (comparación vs OpenClaw)

### Prioridad Alta

#### 1. Proactividad (scheduler + QUEUE.md)
**Estado**: No implementado
**Descripción**: El agente debe poder ejecutar tareas en background sin necesidad de que el usuario envíe un mensaje. Implementar un scheduler que revise tareas pendientes periódicamente.
- Crear `QUEUE.md` o `queue.json` para tareas programadas
- Scheduler: cada 30 min revisa tareas ready, cada 4h trabajo profundo, diario genera resumen
- El agente puede agregar tareas a la cola desde una conversación
- Integrar con proyectos (cada proyecto puede tener su cola)
**Esfuerzo**: Medio | **Impacto**: Alto

#### 2. Function calling nativo por provider
**Estado**: Parcialmente implementado (código existe pero Cloudflare bloquea urllib en Groq)
**Descripción**: Usar la API nativa de function calling de cada provider en vez del text-based fallback.
- OpenAI/Groq: function calling API (resolver bloqueo Cloudflare usando `requests` o el adapter existente)
- Anthropic: native tool_use blocks
- Mantener text fallback para Ollama/providers sin soporte
**Esfuerzo**: Bajo | **Impacto**: Alto

#### 3. Memoria Markdown + auto-compaction
**Estado**: No implementado
**Descripción**: Reemplazar JSON memory con Markdown legible. Auto-compactar contexto antes de perder información.
- `MEMORY.md` para decisiones y preferencias permanentes
- `memory/YYYY-MM-DD.md` para notas diarias
- Auto-compaction: antes de alcanzar límite de contexto, el agente escribe un resumen a memoria
- Daily summary: resumen automático de actividad del día
**Esfuerzo**: Medio | **Impacto**: Alto

#### 4. Skill marketplace
**Estado**: Registry básico existe, sin marketplace
**Descripción**: Permitir instalar skills desde URLs, repositorios git, o un marketplace centralizado.
- Formato estándar: `SKILL.md` (Markdown con YAML frontmatter) + tools
- Instalar desde: URL directa, GitHub repo, npm package
- Listing/búsqueda de skills disponibles
- Versionamiento y actualizaciones
**Esfuerzo**: Alto | **Impacto**: Alto

### Prioridad Media

#### 5. CLI mode (terminal chat)
**Estado**: No implementado
**Descripción**: Permitir interactuar con el sistema desde la terminal sin necesidad de la UI web.
- `python -m capabilityos chat "mensaje"` — envía y recibe respuesta
- `python -m capabilityos run "capability" --inputs '{}'` — ejecuta capability directa
- Streaming output en terminal
- Modo interactivo con historial
**Esfuerzo**: Bajo | **Impacto**: Medio

#### 6. Más canales de mensajería (Signal, iMessage)
**Estado**: No implementado
**Descripción**: Agregar Signal y iMessage como channel adapters.
- Signal: via signal-cli o Signal REST API
- iMessage: via AppleScript (solo macOS)
- Seguir el patrón ChannelAdapter + ChannelPollingWorker existente
**Esfuerzo**: Medio | **Impacto**: Medio

#### 7. Community setup
**Estado**: Parcial (README existe, CONTRIBUTING no actualizado)
**Descripción**: Preparar el proyecto para contribuciones de la comunidad.
- CONTRIBUTING.md detallado con guía de skills, tools, integrations
- Issue templates (bug, feature, skill request)
- PR template
- Code of conduct
- Skill development guide con ejemplos
**Esfuerzo**: Bajo | **Impacto**: Medio

### Backlog (futuro)

#### 8. Multi-agent collaboration
Agentes que trabajan juntos en un proyecto, delegando tareas entre sí.

#### 9. Voice mode
Entrada/salida por voz con TTS y STT integrado.

#### 10. Mobile app
App nativa o PWA restaurada para acceso desde el teléfono.

#### 11. Plugin system
Plugins que extiendan la UI del Control Center con paneles custom.

#### 12. Agent marketplace
Compartir y descargar agentes creados por la comunidad.

---

*Última actualización: 2026-03-30*
*Basado en comparación técnica con OpenClaw (247K+ stars)*
