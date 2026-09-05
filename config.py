# ==========================================
# 1. CONFIGURACIÓN Y CATÁLOGO
# ==========================================
FILE_ALUMNOS = "TEST_1_Alumnos_por_Grupo"
FILE_ASIGNACIONES = "TEST_2_Asignaciones_Profesores"
FILE_SEGURIDAD = "TEST_3_Usuarios_Seguridad"
FILE_REGISTROS = "TEST_4_Base_Conducta_Registros"
FILE_ASISTENCIA = "TEST_5_Registro_Asistencia"

# config.py

# Patrón institucional de cuentas estudiantiles
REGEX_CORREO_ALUMNO = r'\.alm\d+@miraflores\.edu\.mx$'

# Cuentas con privilegios de administración y superusuario
SUPER_USUARIOS_WHITELIST = [
    "marcodoleire@gmail.com",
    "mhaces78@gmail.com"
]

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