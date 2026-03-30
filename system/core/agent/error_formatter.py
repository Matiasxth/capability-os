"""Translates raw tool errors into human-readable explanations."""
from __future__ import annotations

from typing import Any


def format_tool_error(tool_id: str, error: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Returns a structured error with explanation and suggestions."""
    params = params or {}
    error_lower = error.lower()

    # File not found
    if "not found" in error_lower or "no such file" in error_lower or "does not exist" in error_lower:
        path = params.get("path") or params.get("file_path") or ""
        return {
            "explanation": f"El archivo o directorio '{path}' no existe.",
            "suggestions": [
                "Verifica que la ruta sea correcta",
                "Usa list_directory para ver los archivos disponibles",
                "Puede que el nombre tenga un typo",
            ],
            "error_type": "file_not_found",
        }

    # Permission denied / security
    if "security" in error_lower or "permission" in error_lower or "denied" in error_lower or "outside" in error_lower:
        path = params.get("path") or params.get("file_path") or ""
        return {
            "explanation": f"No tienes permisos para acceder a '{path}'.",
            "suggestions": [
                "Esta ruta puede estar fuera del workspace permitido",
                "Agrega la ruta como workspace en Settings si necesitas acceso",
                "Intenta con una ruta dentro del workspace actual",
            ],
            "error_type": "permission_denied",
        }

    # Command not allowed
    if "allowlist" in error_lower or "not allowed" in error_lower or "not in" in error_lower:
        command = params.get("command", "")
        return {
            "explanation": f"El comando '{command}' no esta en la lista permitida.",
            "suggestions": [
                "Intenta con un comando alternativo",
                "Puedes agregar el comando a la allowlist en la configuracion del tool",
            ],
            "error_type": "command_blocked",
        }

    # Timeout
    if "timeout" in error_lower or "timed out" in error_lower:
        return {
            "explanation": "La operacion tardo demasiado y fue cancelada.",
            "suggestions": [
                "Intenta con un comando mas simple",
                "Aumenta el timeout en la configuracion",
                "Divide la tarea en pasos mas pequenos",
            ],
            "error_type": "timeout",
        }

    # Connection error
    if "connection" in error_lower or "network" in error_lower or "unreachable" in error_lower:
        return {
            "explanation": "Error de conexion — no se pudo alcanzar el destino.",
            "suggestions": [
                "Verifica tu conexion a internet",
                "La URL puede estar incorrecta",
                "El servicio puede estar caido",
            ],
            "error_type": "connection_error",
        }

    # Capability not found
    if "not registered" in error_lower or "capability_not_found" in error_lower:
        return {
            "explanation": "Esa capacidad no esta disponible en el sistema.",
            "suggestions": [
                "Puedo intentar con una herramienta diferente",
                "Revisa las herramientas disponibles con get_capability_status",
            ],
            "error_type": "capability_not_found",
        }

    # Generic fallback
    return {
        "explanation": f"Error en {tool_id}: {error[:200]}",
        "suggestions": [
            "Intenta de nuevo con parametros diferentes",
            "Puedo intentar un enfoque alternativo",
        ],
        "error_type": "unknown",
    }
