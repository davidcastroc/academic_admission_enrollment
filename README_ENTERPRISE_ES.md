# Academic 360 Enterprise — Odoo 18

Plataforma SIS/ERP educativa integral sobre Odoo 18.

## Procesos cubiertos
- CRM y captación, admisión, expedientes, documentos, revisión y matrícula.
- Programas, periodos, oferta, planes de estudio versionados y malla curricular.
- Materias, prerrequisitos, correquisitos, créditos, secciones, cupos y lista de espera.
- Profesores, evaluaciones, ponderaciones, notas, retroalimentación, asistencia, tareas y anuncios.
- Expediente académico, intentos/repetición, promedio, créditos aprobados e indicador de avance.
- Bloqueos académicos, financieros, documentales y disciplinarios.
- Trámites: certificaciones, expediente, retiro, cambio de carrera, congelamiento, reingreso, graduación, apelaciones y extraordinarios.
- Finanzas estudiantiles: aranceles, cargos, descuentos/becas, planes de pago, vencimientos, saldo y morosidad.
- Integración contable: los cargos pueden generar facturas de cliente reales en Odoo Accounting.
- Portal estudiantil y estructura LMS existente para cursos, matrícula, tareas y calificaciones.
- Conectores configurables existentes para LMS/colaboración; las APIs reales requieren credenciales del proveedor.

## Seguridad
Roles separados para admisiones, caja, profesor, registro académico, dirección y administración, con reglas de acceso para profesores por sección.

## Nota de integraciones
Moodle, Canvas, Microsoft Teams/Education y otros servicios requieren configurar sus APIs/OAuth en cada institución. El módulo no incluye credenciales ni simula sincronizaciones externas.
