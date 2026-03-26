# Capability OS — Master Spec v1

## 1. Propósito
Capability OS es una plataforma operativa auto-extensible orientada a objetivos. Su función no es solo ejecutar herramientas, sino convertir intenciones del usuario en capacidades ejecutables, observables y ampliables.

## 2. Visión
El sistema debe poder:
- entender objetivos del usuario
- seleccionar una capacidad adecuada
- ejecutar estrategias con herramientas seguras
- registrar estado, trazas y resultados
- detectar brechas de capacidad
- incorporar nuevas integraciones como capacidades nativas

## 3. Principios de diseño
1. Capacidades antes que herramientas.
2. El usuario ve dominios y capacidades, no funciones técnicas sueltas.
3. Toda ejecución debe ser observable.
4. Toda expansión debe pasar por un pipeline estructurado.
5. Las tools no deciden; solo ejecutan.
6. El engine no contiene lógica de negocio; solo interpreta contracts.
7. Toda nueva funcionalidad entra como capacidad o mejora formal de una capacidad existente.

## 4. Modelo conceptual
Usuario -> Intención -> Capacidad -> Estrategia -> Tool -> Resultado -> Observación

## 5. Dominios de capacidad v1
### 5.1 Desarrollo
Crear proyectos, analizar código, modificar código, ejecutar build/test, diagnosticar errores.

### 5.2 Archivos
Leer, escribir, editar, listar, mover, copiar y eliminar dentro del workspace permitido.

### 5.3 Ejecución
Ejecutar comandos, scripts y procesos con límites de seguridad, timeout y captura de salida.

### 5.4 Web
Leer contenido web, parsear HTML y extraer datos. La navegación interactiva queda reservada para una fase posterior.

### 5.5 Integraciones
Registrar, listar, validar, instalar y exponer conectores con sistemas externos.

### 5.6 Automatización
Definir y ejecutar secuencias reutilizables de capacidades.

### 5.7 Observación
Ver estado de capacidades, tools, integraciones, ejecuciones, errores y disponibilidad general.

## 6. Estados estándar del sistema
- available
- not_configured
- preparing
- ready
- running
- error
- experimental
- disabled

## 7. Capability Contract
Cada capacidad debe incluir:
- id
- name
- domain
- type
- description
- inputs
- outputs
- requirements
- strategy
- exposure
- lifecycle

### 7.1 Tipos de capacidad
- base
- composed
- integration
- generated

### 7.2 Estructura base del contract
```json
{
  "id": "create_project",
  "name": "Crear proyecto React",
  "domain": "desarrollo",
  "type": "composed",
  "description": "Crea un proyecto React usando Vite",
  "inputs": {
    "project_name": {"type": "string", "required": true},
    "target_dir": {"type": "string", "required": false}
  },
  "outputs": {
    "project_path": {"type": "string"},
    "status": {"type": "string", "enum": ["success", "error"]}
  },
  "requirements": {
    "tools": ["execution_run_command", "filesystem_list_directory"],
    "capabilities": ["ejecucion", "archivos"],
    "integrations": []
  },
  "strategy": {
    "mode": "sequential",
    "steps": [
      {
        "step_id": "create_project",
        "action": "execution_run_command",
        "params": {
          "command": "npm create vite@latest {{inputs.project_name}}",
          "cwd": "{{inputs.target_dir}}"
        }
      },
      {
        "step_id": "install_dependencies",
        "action": "execution_run_command",
        "params": {
          "command": "npm install",
          "cwd": "{{steps.create_project.outputs.project_path}}"
        }
      }
    ]
  },
  "exposure": {
    "visible_to_user": true,
    "trigger_phrases": ["crear proyecto react", "nuevo proyecto react"]
  },
  "lifecycle": {
    "version": "1.1.0",
    "status": "ready"
  }
}
```

## 8. Strategy Model
### 8.1 v1
- sequential

### 8.2 v2
- conditional
- retry_policy
- fallback

### 8.3 Variables
El runtime debe soportar sustitución de variables SOLO con origen explícito.

Fuentes válidas:
- `{{inputs.<field>}}`
- `{{state.<field>}}`
- `{{steps.<step_id>.outputs.<field>}}`
- `{{runtime.<field>}}`

Ejemplos válidos:
- `{{inputs.project_name}}`
- `{{state.project_path}}`
- `{{steps.create_project.outputs.project_path}}`
- `{{runtime.execution_id}}`

Queda prohibido usar variables implícitas como `{{project_name}}`, `{{project_path}}` o `{{last_output.stdout}}`.

## 9. Capability Engine
### 9.1 Responsabilidad
Interpretar contracts, resolver intención, validar requerimientos, ejecutar estrategias, mantener estado y registrar observación.

### 9.2 Componentes
- Capability Registry
- Capability Resolver
- Capability Validator
- Strategy Interpreter
- Tool Router
- Execution Runtime
- State Manager
- Observation Logger

### 9.3 Flujo
1. Recibir intención.
2. Resolver capacidad.
3. Validar inputs y requirements.
4. Inicializar runtime.
5. Interpretar strategy.
6. Invocar tools.
7. Persistir estado intermedio.
8. Registrar observación.
9. Devolver output estructurado.

## 10. Tool System
### 10.1 Definición
Una tool es una unidad atómica de ejecución con contrato estricto y seguridad controlada.

### 10.2 Tool Contract
Cada tool debe incluir:
- id
- name
- category
- description
- inputs
- outputs
- constraints
- safety
- lifecycle

### 10.3 Categorías iniciales
- filesystem
- execution
- network
- system
- browser (futuro)

### 10.4 Ejemplo
```json
{
  "id": "execution_run_command",
  "name": "Ejecutar comando",
  "category": "execution",
  "description": "Ejecuta un comando del sistema dentro de un entorno controlado",
  "inputs": {
    "command": {"type": "string", "required": true},
    "cwd": {"type": "string", "required": false}
  },
  "outputs": {
    "stdout": {"type": "string"},
    "stderr": {"type": "string"},
    "exit_code": {"type": "integer"}
  },
  "constraints": {
    "timeout_ms": 30000,
    "allowlist": ["npm", "node", "python", "pytest", "git", "npx"],
    "workspace_only": true
  },
  "safety": {
    "level": "medium",
    "requires_confirmation": false
  },
  "lifecycle": {
    "version": "1.1.0",
    "status": "ready"
  }
}
```

### 10.5 Tool Runtime
- Tool Registry
- Tool Validator
- Tool Executor
- Sandbox / Safety Layer
- Result Formatter

## 11. Seguridad base
1. Workspace aislado.
2. Allowlist para comandos.
3. Timeout obligatorio.
4. Logs completos.
5. Prohibición de paths fuera del workspace salvo tools explícitamente autorizadas.
6. Confirmación para acciones destructivas.
7. Desinstalación reversible de integraciones.

## 12. Observabilidad
### 12.1 Eventos de ejecución
- execution_started
- capability_resolved
- validation_passed
- step_started
- step_succeeded
- step_failed
- execution_finished

### 12.2 Runtime Model canónico (v1.1)
```json
{
  "execution_id": "exec_001",
  "capability_id": "create_project",
  "status": "running",
  "current_step": "install_dependencies",
  "state": {},
  "logs": [],
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "duration_ms": 0,
  "retry_count": 0,
  "error_code": null,
  "error_message": null,
  "last_completed_step": null,
  "failed_step": null,
  "final_output": {}
}
```

Regla: este es el único modelo de runtime válido para schemas, contracts y UI. Cualquier modelo anterior queda deprecado y no debe implementarse.

## 13. Integration System
### 13.1 Objetivo
Detectar brechas de capacidad y convertirlas en integraciones estructuradas que generen nuevas capacidades nativas.

### 13.2 Componentes
- Integration Detector
- Integration Classifier
- Integration Planner
- Template Engine
- Integration Generator
- Integration Validator
- Integration Registry
- Capability Bridge

### 13.3 Tipos de integración
- web_app
- rest_api
- local_app
- file_based

### 13.4 Flujo
1. El engine no encuentra capacidad.
2. Detector marca brecha.
3. Classifier define tipo.
4. Planner propone estrategia.
5. Template Engine selecciona plantilla.
6. Generator crea estructura.
7. Validator prueba.
8. Registry instala.
9. Capability Bridge publica nuevas capacidades.

### 13.5 Estructura de integración
```text
integrations/
  installed/
    whatsapp_web_connector/
      manifest.json
      capabilities/
      tools/
      config/
      tests/
```

### 13.6 Manifest de integración
```json
{
  "id": "whatsapp_web_connector",
  "type": "web_app",
  "status": "ready",
  "capabilities": ["send_whatsapp_message", "read_whatsapp_chats"],
  "requirements": {
    "browser": true,
    "auth": "qr_login"
  },
  "lifecycle": {
    "version": "1.0.0"
  }
}
```

## 14. Reglas de crecimiento
1. Nada entra al sistema si no puede convertirse en capacidad.
2. Toda integración debe generar al menos una capacidad usable.
3. Toda integración debe poder validarse y desinstalarse.
4. Toda nueva capacidad debe tener contract, tests y estado.
5. El sistema propone y el usuario confirma antes de instalar integración nueva.

## 15. UX del sistema
### 15.1 Paneles principales
- Panel de capacidades
- Panel de ejecución
- Panel de integraciones
- Panel de observación

### 15.2 Lo que debe ver el usuario
- dominios de capacidad
- estado de cada dominio
- ejecución paso a paso
- integraciones instaladas
- brechas detectadas
- errores claros

### 15.3 Estados visibles por dominio
- listo
- limitado
- no configurado
- ejecutando
- error
- experimental
- deshabilitado

Regla: estos estados visibles deben alinearse exactamente con el mapeo oficial definido en la sección 26.3.

## 16. Capability Map v1
### Desarrollo
- create_project
- analyze_project
- modify_code
- run_build
- run_tests
- diagnose_error

### Archivos
- read_file
- write_file
- edit_file
- list_directory
- copy_file
- move_file
- delete_file

### Ejecución
- execute_command
- execute_script
- list_processes
- stop_process

### Web
- fetch_url
- parse_html
- extract_links
- extract_text

### Integraciones
- list_integrations
- inspect_integration
- validate_integration
- install_integration
- uninstall_integration

### Automatización
- run_sequence
- save_sequence
- load_sequence

### Observación
- get_system_status
- get_capability_status
- get_execution_trace
- get_error_report

## 17. Tool Map v1
### Filesystem
- filesystem_read_file
- filesystem_write_file
- filesystem_edit_file
- filesystem_list_directory
- filesystem_copy_file
- filesystem_move_file
- filesystem_delete_file

### Execution
- execution_run_command
- execution_run_script
- execution_list_processes
- execution_terminate_process
- execution_read_process_output

### Network
- network_http_get
- network_http_post

### System
- system_get_os_info
- system_get_env_var
- system_get_workspace_info

## 18. Integraciones prioritarias
### Prioridad 1
- Browser Control Layer (base para web_app connectors)
- REST API Connector Template

### Prioridad 2
- WhatsApp Web Connector
- Generic SaaS API Connector

### Prioridad 3
- Local App Connector
- File Workflow Connector

## 19. Orden de implementación recomendado
### Fase 1
- Capability Registry
- Tool Registry
- Contracts base
- Estado y observabilidad mínima

### Fase 2
- Capability Engine v1
- Tool Runtime v1
- Seguridad básica

### Fase 3
- UI operativa mínima
- panel de capacidades
- panel de ejecución

### Fase 4
- Integration System v1
- templates base
- registry de integraciones

### Fase 5
- Browser Control Layer
- primer conector real

## 20. Entregables para Codex
### 20.1 Documento de visión
Este documento.

### 20.2 Contratos base
- capability_contract.schema.json
- tool_contract.schema.json
- integration_manifest.schema.json

### 20.3 Backlog maestro
- core/runtime
- registries
- validation
- logging
- UI shell
- integration pipeline

### 20.4 Reglas para Codex
1. No crear tools sin contract.
2. No exponer tools crudas al usuario.
3. No hardcodear lógica de capacidad dentro del engine.
4. Mantener separación estricta entre capability, tool e integration.
5. Todo cambio debe incluir tests.
6. Toda nueva carpeta debe seguir la arquitectura definida.

## 21. Arquitectura de carpetas propuesta
```text
system/
  core/
    capability_engine/
    strategy/
    state/
    observation/
  capabilities/
    registry/
    contracts/
    implementations/
  tools/
    registry/
    contracts/
    runtime/
    implementations/
  integrations/
    registry/
    templates/
    installed/
    validator/
  frontend/
    app/
    components/
    views/
  tests/
    unit/
    integration/
    e2e/
```

## 22. Definición de éxito para v1
La v1 será exitosa si puede:
1. registrar capacidades y tools formales
2. resolver al menos 5 capacidades útiles reales
3. ejecutar estrategias secuenciales con trazabilidad
4. mostrar ejecución visible en UI
5. instalar al menos una integración usando pipeline formal
6. mantener aislamiento y seguridad básica

## 23. Riesgos principales
- mezclar tools con capacidades
- saltarse contracts
- agregar integración sin registry
- hacer UI sin estados reales del runtime
- meter automatización compleja antes de observabilidad sólida

## 24. Decisiones cerradas
- camino elegido: plataforma auto-extensible
- modelo: capacidades sobre herramientas
- engine: genérico, no de negocio
- crecimiento: supervisado por el usuario
- UX: sistema visible, no solo chat
- prioridad técnica: contratos, runtime, observabilidad, luego integración

## 25. Qué se le pedirá a Codex primero
1. crear schemas y contratos base
2. crear registries
3. crear capability engine mínimo
4. crear tool runtime mínimo
5. crear logger de observación
6. crear shell UI con paneles
7. recién después crear integration system

---

## 26. Estados canónicos (v1.1)
### 26.1 Estados internos (runtime)
- available
- not_configured
- preparing
- ready
- running
- error
- experimental
- disabled

### 26.2 Estados de UI
- listo
- limitado
- no configurado
- ejecutando
- error
- experimental
- deshabilitado

### 26.3 Mapeo oficial
- available | ready -> listo
- not_configured -> no configurado
- preparing -> limitado
- running -> ejecutando
- error -> error
- experimental -> experimental
- disabled -> deshabilitado

Regla: el backend SOLO emite estados internos; el frontend aplica este mapeo.

---

## 27. Naming canon (v1.1)
### 27.1 Capabilities
Formato: verb_object (snake_case)
Ej: read_file, create_project, run_tests

### 27.2 Tools
Formato: category_verb_object
Ej: filesystem_read_file, execution_run_command, network_http_get

### 27.3 Integraciones
Formato: provider_connector_type
Ej: whatsapp_web_connector, gmail_api_connector

Reglas:
1. No mezclar prefijos entre capas.
2. Los IDs son estables e inmutables.
3. El nombre humano (name) puede cambiar; el id no.

---

## 28. Variables en Strategy (v1.1)
Fuentes permitidas:
- inputs.*
- state.*
- steps.<step_id>.outputs.*
- runtime.*

### 28.1 Ejemplos
- {{inputs.project_name}}
- {{state.project_path}}
- {{steps.create_project.outputs.project_path}}

### 28.2 Reglas
1. Toda variable debe tener origen explícito.
2. Cada step debe declarar un step_id.
3. El runtime persiste outputs por step_id.
4. Queda prohibido usar variables implícitas.

---

## 29. Capability–Tool Mapping (v1.1)
Tabla mínima obligatoria para v1:

| capability            | domain         | tools requeridas                                           | dependent capabilities | outputs clave                 |
|----------------------|----------------|------------------------------------------------------------|------------------------|------------------------------|
| read_file            | archivos       | filesystem_read_file                                       | []                     | content                      |
| write_file           | archivos       | filesystem_write_file                                      | []                     | status                       |
| edit_file            | archivos       | filesystem_edit_file                                       | []                     | status                       |
| list_directory       | archivos       | filesystem_list_directory                                  | []                     | items                        |
| copy_file            | archivos       | filesystem_copy_file                                       | []                     | status                       |
| move_file            | archivos       | filesystem_move_file                                       | []                     | status                       |
| delete_file          | archivos       | filesystem_delete_file                                     | []                     | status                       |
| execute_command      | ejecucion      | execution_run_command                                      | []                     | stdout, exit_code            |
| execute_script       | ejecucion      | execution_run_script                                       | []                     | stdout, exit_code            |
| list_processes       | ejecucion      | execution_list_processes                                   | []                     | processes                    |
| stop_process         | ejecucion      | execution_terminate_process                                | []                     | status                       |
| fetch_url            | web            | network_http_get                                           | []                     | body, status_code            |
| parse_html           | web            | []                                                         | [fetch_url]            | document                     |
| extract_links        | web            | []                                                         | [parse_html]           | links                        |
| extract_text         | web            | []                                                         | [parse_html]           | text                         |
| create_project       | desarrollo     | execution_run_command, filesystem_list_directory           | []                     | project_path                 |
| analyze_project      | desarrollo     | filesystem_list_directory, filesystem_read_file            | []                     | analysis_report              |
| modify_code          | desarrollo     | filesystem_read_file, filesystem_edit_file                 | []                     | status                       |
| run_build            | desarrollo     | execution_run_command                                      | []                     | stdout, exit_code            |
| run_tests            | desarrollo     | execution_run_command                                      | []                     | stdout, exit_code            |
| diagnose_error       | desarrollo     | []                                                         | [analyze_project]      | diagnosis                    |
| list_integrations    | integraciones  | system_get_workspace_info, filesystem_read_file            | []                     | integrations                 |
| inspect_integration  | integraciones  | filesystem_read_file                                       | []                     | integration_details          |
| validate_integration | integraciones  | filesystem_read_file                                       | []                     | validation_result            |
| install_integration  | integraciones  | filesystem_write_file, filesystem_list_directory           | []                     | status                       |
| uninstall_integration| integraciones  | filesystem_delete_file                                     | []                     | status                       |
| run_sequence         | automatizacion | []                                                         | [load_sequence]        | final_output                 |
| save_sequence        | automatizacion | filesystem_write_file                                      | []                     | status                       |
| load_sequence        | automatizacion | filesystem_read_file                                       | []                     | sequence_definition          |
| get_system_status    | observacion    | system_get_os_info, system_get_workspace_info              | []                     | system_status                |
| get_capability_status| observacion    | filesystem_read_file                                       | []                     | capability_status            |
| get_execution_trace  | observacion    | filesystem_read_file                                       | []                     | execution_trace              |
| get_error_report     | observacion    | filesystem_read_file                                       | []                     | error_report                 |

Regla: toda capability debe declarar explícitamente sus tools directas y/o dependent capabilities, además de sus outputs.

---

### 29.1 Capability Input/Output Matrix (v1.1)
| capability            | inputs mínimos                                      | outputs clave                 |
|----------------------|-----------------------------------------------------|------------------------------|
| create_project       | project_name, target_dir?                           | project_path, status         |
| analyze_project      | project_path                                        | analysis_report              |
| modify_code          | file_path, modification                             | status                       |
| run_build            | project_path, build_command?                        | stdout, exit_code            |
| run_tests            | project_path, test_command?                         | stdout, exit_code            |
| diagnose_error       | project_path, error_context?                        | diagnosis                    |
| read_file            | path                                                | content                      |
| write_file           | path, content                                       | status                       |
| edit_file            | path, patch_or_replacement                          | status                       |
| list_directory       | path                                                | items                        |
| copy_file            | source_path, destination_path                       | status                       |
| move_file            | source_path, destination_path                       | status                       |
| delete_file          | path                                                | status                       |
| execute_command      | command, cwd?                                       | stdout, stderr, exit_code    |
| execute_script       | script_path, args?                                  | stdout, stderr, exit_code    |
| list_processes       | filter?                                             | processes                    |
| stop_process         | process_id                                          | status                       |
| fetch_url            | url, headers?                                       | body, status_code            |
| parse_html           | html                                                | document                     |
| extract_links        | document                                            | links                        |
| extract_text         | document                                            | text                         |
| list_integrations    | none                                                | integrations                 |
| inspect_integration  | integration_id                                      | integration_details          |
| validate_integration | integration_id                                      | validation_result            |
| install_integration  | integration_source, config?                         | status                       |
| uninstall_integration| integration_id                                      | status                       |
| run_sequence         | sequence_id_or_definition                           | final_output                 |
| save_sequence        | sequence_definition, name                           | status                       |
| load_sequence        | sequence_id_or_name                                 | sequence_definition          |
| get_system_status    | none                                                | system_status                |
| get_capability_status| capability_id?                                      | capability_status            |
| get_execution_trace  | execution_id                                        | execution_trace              |
| get_error_report     | execution_id?, capability_id?                       | error_report                 |

## 30. Runtime Model extendido (v1.1)
Ver sección 12.2. Ese modelo es el canónico y no debe duplicarse en otras variantes dentro del spec.

### 30.1 Reglas
1. ended_at se completa siempre.
2. duration_ms = ended_at - started_at.
3. error_code es obligatorio si status=error.
4. final_output siempre presente (aunque sea vacío).

## 31. Métricas operativas v1 (v1.1)
Objetivos mínimos:
- 100% de capabilities con contract válido.
- 100% de tools con constraints y safety definidos.
- ≥ 90% de éxito en ejecuciones secuenciales simples en entorno controlado.
- Latencia media de resolución de capacidad < 2000 ms (sin ejecución de tools externas largas).
- Cobertura de tests unitarios del core ≥ 80%.

### 31.1 Métricas a registrar
- execution_success_rate
- avg_execution_time_ms
- error_rate_by_capability
- tool_failure_rate

---

## 32. Correcciones de consistencia (v1.1)
1. En strategies, toda referencia explícita como `{{state.project_path}}` debe provenir de:
   - inputs.project_path, o
   - steps.<id>.outputs.project_path, o
   - state.project_path
2. Eliminar tools en requirements que no se utilicen en steps.
3. Sincronizar descripción de dominios con Capability Map (agregar copy/move donde corresponda).

---

## 33. Criterios de aceptación del spec v1.1
El spec está listo para implementación cuando:
1. No existen variables sin origen definido.
2. No existen nombres duplicados o inconsistentes entre capas.
3. Todas las capabilities del mapa tienen tools directas y/o dependent capabilities mapeadas.
4. El runtime model cubre éxito y error.
5. Existen métricas operativas mínimas.

## 34. Instrucción para Codex (actualizada)
Codex debe:
1. Implementar exactamente este spec sin redefinir nombres.
2. Validar contracts contra schemas antes de ejecutar.
3. No introducir nuevos estados, dominios ni naming sin aprobación.
4. Generar tests para cada componente base.
5. Mantener separación estricta: capability / tool / integration.
