# ==========================================
# 1. CONFIGURACIÓN Y CATÁLOGO
# ==========================================
FILE_ALUMNOS = "1_Alumnos_por_Grupo"
FILE_ASIGNACIONES = "2_Asignaciones_Profesores"
FILE_SEGURIDAD = "3_Usuarios_Seguridad"
FILE_REGISTROS = "4_Base_Conducta_Registros"
FILE_ASISTENCIA = "5_Registro_Asistencia"

# config.py

CATALOGO_SANCIONES = {
    "Comportamiento y Disciplina": {
        "Consumir alimentos y bebidas en el aula": {"puntos": 0.2, "semaforo": "Leve"},
        "Masticar chicle": {"puntos": 0.2, "semaforo": "Leve"},
        "Conductas afectivas inapropiadas": {"puntos": 0.5, "semaforo": "Medio"},
        "Uso de groserías o palabras altisonantes": {"puntos": 0.5, "semaforo": "Medio"},
        "Interrumpir o distraer el desarrollo de la clase": {"puntos": 0.5, "semaforo": "Medio"},
        "Faltar al respeto a cualquier miembro de la comunidad": {"puntos": 1.0, "semaforo": "Grave"},
        "Agredir física, verbal o psicológicamente": {"puntos": 5.0, "semaforo": "Crítica"},
        "Fomentar o consumir sustancias nocivas (vapes, alcohol)": {"puntos": 5.0, "semaforo": "Crítica"},
        "Portar armas u objetos punzocortantes": {"puntos": 5.0, "semaforo": "Crítica"}
    },
    "Responsabilidad y Honestidad Académica": {
        "No traer libros de texto y/o material": {"puntos": 0.2, "semaforo": "Leve"},
        "Copiar o plagiar total o parcialmente": {"puntos": 1.0, "semaforo": "Grave"},
        "Falsificar firmas, justificantes o documentos": {"puntos": 1.0, "semaforo": "Grave"},
        "Suplantar en actividades académicas": {"puntos": 5.0, "semaforo": "Crítica"}
    },
    "Uso de Tecnología e Instalaciones": {
        "Uso de celulares, audífonos o relojes inteligentes": {"puntos": 0.5, "semaforo": "Medio"},
        "Prestar Chromebook o instalar apps no autorizadas": {"puntos": 1.0, "semaforo": "Grave"},
        "Provocar daños intencionales o vandalismo": {"puntos": 5.0, "semaforo": "Crítica"}
    },
    "Uniforme y Presentación": {
        "Apariencia contraria a las normas (cabello, arreglo)": {"puntos": 0.2, "semaforo": "Leve"},
        "No portar el uniforme correcto y completo": {"puntos": 0.2, "semaforo": "Leve"},
        "Uso de prendas o accesorios no autorizados": {"puntos": 0.2, "semaforo": "Leve"}
    }
}

PERIODOS_LECTIVOS = {
    "Secundaria": [
        {"nombre": "1er Trimestre", "inicio": "2026-09-01", "fin": "2026-10-29"},
        {"nombre": "2° Trimestre", "inicio": "2026-10-30", "fin": "2027-02-12"},
        {"nombre": "3er Trimestre", "inicio": "2027-02-13", "fin": "2027-07-09"}
    ],
    "Preparatoria": [
    {"nombre": "Periodo 1", "inicio": "2026-08-17", "fin": "2026-10-16"},
    {"nombre": "Periodo 2", "inicio": "2026-10-19", "fin": "2026-12-18"},
    {"nombre": "Periodo 3", "inicio": "2027-01-07", "fin": "2027-02-26"},
    {"nombre": "Periodo 4", "inicio": "2027-03-01", "fin": "2027-04-30"},
    {"nombre": "Periodo 5", "inicio": "2027-05-03", "fin": "2027-05-14"}
    ]
}

REGLAMENTO_INSTITUCIONAL = """
ACUERDO DE CONVIVENCIA ESCOLAR COLEGIO MIRAFLORES MÉXICO (CICLO 2025-2026)

Capítulo II. Admisión y Permanencia de alumnos
Artículo 5. Reserva del derecho de admisión: El Colegio no admite a alumnos repetidores o de sistemas no escolarizados.
Artículo 6. Requisitos de reinscripción / permanencia:
a. Cumplir con el 80% de asistencia.
b. No tener más de 2 reportes de suspensión a lo largo del curso escolar vigente.
c. Cumplir con la Carta Condicionamiento (si aplica).
d. No haber reprobado el promedio final en más de 3 materias.
e. En Secundaria (SEP): si reprueba materias, haber aprobado el extraordinario correspondiente.
f. En Preparatoria (UNAM): si reprueba materias, haber aprobado el extraordinario o extemporáneo.
g. Los padres de familia deberán asistir a por lo menos 2 conferencias obligatorias y juntas de tutores durante el año.

Capítulo III. Derechos de los alumnos
Artículo 9: Ser tratados con respeto y preservar su dignidad personal, evitando cualquier tipo de sanción o trato que atente contra la integridad humana.
Artículo 11: Obtener retroalimentación oportuna, clara y constructiva sobre los resultados de las evaluaciones parciales.
Artículo 13: Conocer las calificaciones de los exámenes finales y/o extraordinarios dentro de los tres días posteriores a su aplicación, junto con la fecha y horario asignados para su revisión.
Artículo 14: Exentar exámenes finales como reconocimiento al esfuerzo académico, cumpliendo los requisitos del Colegio.
Artículo 16: Acceder a un punto adicional en el promedio final de la materia que elijan en caso de no registrar ninguna falta durante el curso (no cuentan las faltas justificadas), siempre que la materia esté aprobada.

Capítulo IV. Obligaciones de los alumnos y Normativa Disciplinaria (Capítulo X)
Artículo 19. Horarios de entrada y salida oficiales:
- Preescolar (Beginners): 9:00 a.m. - 1:00 p.m.
- Preescolar (Maternal y Especial de Inglés): 7:50 a.m. - 2:30 p.m.
- Primaria y Secundaria: 7:50 a.m. - 2:30 p.m.
- Preparatoria (Variado según grado): 4° Bachillerato (7:50 a.m. - 2:30 p.m.), 5° y 6° Bachillerato (con días de entrada a las 7:00 a.m. o salida a las 14:20 p.m.).

NORMAS DE PUNTUALIDAD Y RETARDOS (Capítulo X):
- Llegar al Colegio después de la hora establecida: No se permitirá el acceso una vez cerrados los accesos.
- Retardos en clase: Se considera retardo si el alumno ingresa dentro de los primeros 5 minutos de la clase. Tres retardos equivalen a 1 falta. A partir del sexto minuto, se registra directamente como falta, pero el alumno tiene la obligación de entrar al aula y trabajar.
- No ingresar a clase o salirse sin autorización: 1ª ocasión el alumno permanecerá el viernes de 3:00 a 5:00 p.m. en actividades académicas. Reincidencia amerita suspensión de uno o más días.

NORMAS DE UNIFORME Y PRESENTACIÓN PERSONAL (Artículo 22 y Capítulo X):
- El uniforme de diario, gala, deportes, natación o huerta debe portarse completo, pulcro y limpio conforme a las especificaciones oficiales por sección.
- Apariencia contraria a las normas (Varones): Deben presentarse debidamente rasurados; en caso contrario, deberán rasurarse en el colegio y reponer el rastrillo al día siguiente. El corte de cabello debe cumplir con lo establecido; si no cumple, se dará aviso a casa y deberá presentarse recortado al día siguiente.
- Apariencia contraria a las normas (Mujeres): Si se presentan con las uñas pintadas o decoraciones llamativas, deberán retirarlas de inmediato.
- Reincidencias en presentación/uñas/rasurado: A la segunda vez se enviará a casa suspendido por el día.
- No portar el uniforme correcto/completo: 1ª ocasión se da aviso a casa, permanece en clases pero se le registra falta de todo el día. Ocasiones posteriores se envía a casa para corregirse y poder regresar.
- Uso de prendas no autorizadas: 1ª ocasión se retira la prenda y queda bajo resguardo en Coordinación hasta el final del día. 2ª ocasión se retira y se dona a las misiones del Colegio.

NORMAS DE DISPOSITIVOS ELECTRÓNICOS Y CELULARES (Capítulo X):
- Uso de celulares, audífonos, tabletas, relojes inteligentes u otros dispositivos personales durante el horario escolar (sin autorización académica expresa):
  - Primera ocasión: El dispositivo será retirado y permanecerá resguardado bajo llave durante 3 días hábiles.
  - Segunda ocasión: El dispositivo será retirado por un periodo de 2 semanas.
  - Tercera ocasión: El dispositivo será retenido por la institución hasta el final del ciclo escolar en curso.
  * Nota: En todos los casos se envía reporte/aviso a casa. El dispositivo se entrega únicamente a los padres de familia previa identificación y firma de recibido en Coordinación.

NORMAS DE CHROMEBOOKS (Artículos 23 a 26 y Capítulo X):
- Obligatorio presentarse diariamente con la Chromebook completamente cargada y su carcasa protectora en buen estado.
- No traer la Chromebook o traerla descargada: El alumno permanecerá todo el día trabajando bajo supervisión en la biblioteca. Se notifica a los padres. Reincidencia continua amerita envío a casa.
- Prestar la Chromebook, instalar apps no autorizadas o alterar su sistema de seguridad: Suspensión de 1 a 2 días y turno al Comité de Disciplina.
- Daño físico a la Chromebook: Si tiene seguro, los padres pagan el deducible. Si no está cubierto por el seguro, deben cubrir el costo total de la reparación o reposición.

INTEGRIDAD ACADÉMICA Y USO DE INTELIGENCIA ARTIFICIAL (Artículos 27, 28, 41, 42 y Capítulo X):
- Se prohíbe el plagio, copia (parcial o total) en exámenes, tareas o proyectos, así como compartir/recibir respuestas durante evaluaciones, o el uso no autorizado de Inteligencia Artificial (IA) para resolver tareas o exámenes.
- Consecuencias de deshonestidad académica o uso no autorizado de IA:
  1. Calificación automática de cero (0) en la actividad o examen sin derecho a recuperación.
  2. Levantamiento de Reporte Disciplinario en el sistema del colegio.
  3. Notificación formal por escrito a los padres o tutores.
  4. Obligación del alumno de realizar una actividad formativa obligatoria.
  5. Reincidencias consecutivas ameritan la aplicación de suspensiones o sanciones adicionales determinada por el Comité.

COMPORTAMIENTO, CONVIVENCIA Y OTRAS SANCIONES:
- Consumir alimentos o mascar chicle en el aula: Bajar la calificación de conducta del alumno en el día correspondiente.
- Interrumpir, distraer o dificultar el desarrollo de la clase por desobediencia: Se refleja en la calificación de disciplina y evaluación continua de la materia. Reincidencia amerita envío del caso al Comité de Disciplina (puede incluir suspensión temporal).
- Faltar al respeto a miembros de la comunidad escolar (palabras, gestos, mensajes, redes sociales): Suspensión temporal determinada por el Comité de Disciplina según la gravedad. En casos muy graves, se evalúa exclusión temporal o permanente.
- Daños intencionales o vandalismo: Pagar la reparación/reposición completa. Segunda ocasión implica suspensión de 1 a 2 días.
- Faltas graves (Fomentar/poseer/consumir sustancias nocivas, cigarros, vapes, alcohol, drogas; portar armas; agredir física/verbalmente; falsificar firmas o sellos; apropiación ilícita de exámenes; conductas inmorales/connotación sexual): Turno de inmediato al Comité de Disciplina. Sanciones aplicables:
  - Suspensión temporal de 3 a 15 días.
  - Calificación disciplinaria y conductual reprobatoria obligatoria de 5.0 (cinco).
  - Condicionamiento de reinscripción o la separación definitiva del Colegio.

Capítulo VI. Uso de cámaras de videovigilancia
- Las cámaras instaladas en áreas comunes son de uso exclusivamente interno para seguridad.
- La revisión de grabaciones es de facultad exclusiva de las Coordinaciones o Dirección.
- Por confidencialidad de menores, el material captado jamás podrá ser mostrado a los estudiantes ni a los padres de familia.

Capítulo VII. Evaluaciones y Ausencias Justificadas
Artículo 38. Ausencias justificadas: En caso de faltas por motivos médicos o fuerza mayor, se deben entregar los justificantes ante la Coordinación de Etapa en un plazo máximo de 2 días hábiles tras la reincorporación para poder reponer trabajos o evaluaciones (máximo 2 asignaturas).
Artículo 40. Exámenes de periodo: No se pueden reprogramar salvo autorización expresa de Coordinación por causas plenamente justificadas. Inasistencia injustificada equivale a calificación de cero (0).
Artículo 43. Suspensión de clases (Efectos): El alumno suspendido pierde derecho a evaluación continua del periodo de suspensión (calificación cero en tareas/trabajos de aula realizados esos días). Solo se le permite entregar tareas de casa si las envía en tiempo y forma.
"""
