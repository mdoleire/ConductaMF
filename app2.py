"""
Sistema Integral de Gestión Conductual - Colegio Miraflores
----------------------------------------------------------
Versión: 3.3 (Tema Autoadaptable Inteligente)
Funcionalidades: RBAC, Filtros Multidimensionales, Conectividad GSheets,
Semáforo Visual, Reportes de Pasillo Multígrado y Doble Candado de Seguridad.
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
import os  
import time  
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.parse
import requests
import google.generativeai as genai

# ==========================================
# 1. CONFIGURACIÓN Y CATÁLOGO
# ==========================================
FILE_ALUMNOS = "1_Alumnos_por_Grupo"
FILE_ASIGNACIONES = "2_Asignaciones_Profesores"
FILE_SEGURIDAD = "3_Usuarios_Seguridad"
FILE_REGISTROS = "4_Base_Conducta_Registros"

CATALOGO_SANCIONES = {
    "Asistencia": {
        "Llegar tarde": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Salida sin autorización": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Inasistencia injustificada": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Salir sin permiso / no entrar": {"puntos": -10, "semaforo": "🔴 Grave"}
    },
    "Presentación": {
        "Apariencia inadecuada": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Uniforme incorrecto/incompleto": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Prendas no autorizadas": {"puntos": -1, "semaforo": "🟡 Leve"}
    },
    "Tecnología": {
        "Chromebook descargada/olvidada": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Uso de celular/audífonos": {"puntos": -3, "semaforo": "🟡 Medio"},
        "App no autorizada": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Maltrato de equipo": {"puntos": -10, "semaforo": "🔴 Grave"}
    },
    "Integridad": {
        "Plagio o copia": {"puntos": -10, "semaforo": "🔴 Grave"},
        "Uso de IA no autorizado": {"puntos": -10, "semaforo": "🔴 Grave"}
    },
    "Comportamiento": {
        "Consumo de alimentos": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Mascar chicle": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Distracción en clase": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Interrupción": {"puntos": -1, "semaforo": "🟡 Leve"},
        "Material incompleto": {"puntos": -1, "semaforo": "🟡 Leve"},
        "No trabaja en clase": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Groserías": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Falta al respeto": {"puntos": -3, "semaforo": "🟡 Medio"},
        "Daños a instalaciones": {"puntos": -10, "semaforo": "🔴 Grave"},
        "Agresión verbal al profesor": {"puntos": -10, "semaforo": "🔴 Grave"},
        "Agresión física (compañero/profesor)": {"puntos": -10, "semaforo": "🔴 Grave"},
        "Señas/Acercamientos inapropiados": {"puntos": -10, "semaforo": "🔴 Grave"},
        "Violencia de género": {"puntos": -10, "semaforo": "🟣 Crítica"}
    }
}

PERIODOS_LECTIVOS = [
    {"nombre": "Periodo 1", "inicio": "2025-08-18", "fin": "2025-09-30"},
    {"nombre": "Periodo 2", "inicio": "2025-10-01", "fin": "2025-11-15"},
    {"nombre": "Periodo 3", "inicio": "2025-11-16", "fin": "2026-02-28"},
    {"nombre": "Periodo 4", "inicio": "2026-03-01", "fin": "2026-06-30"}
]

# ==========================================
# 2. MOTOR DE DATOS (CACHÉ Y OPTIMIZACIÓN)
# ==========================================
@st.cache_resource
def conectar_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_json" not in st.secrets:
        st.error("🚨 ERROR CRÍTICO: La llave 'gcp_json' no existe en los secretos de Streamlit.")
        st.stop()
    try:
        creds_dict = json.loads(st.secrets["gcp_json"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 La llave 'gcp_json' está mal formada: {e}")
        st.stop()

@st.cache_data(ttl=300)
def leer_datos(_client, nombre_archivo, nombre_pestaña=None):
    doc = _client.open(nombre_archivo)
    ws = doc.worksheet(nombre_pestaña) if nombre_pestaña else doc.sheet1
    return pd.DataFrame(ws.get_all_records())

@st.cache_data(ttl=300)
def leer_todos_los_registros(_client):
    try:
        doc = _client.open(FILE_REGISTROS)
        hojas = [pd.DataFrame(h.get_all_records()) for h in doc.worksheets() if h.get_all_records()]
        if not hojas: return pd.DataFrame()
        df = pd.concat(hojas, ignore_index=True)
        if 'Grupo' in df.columns:
            df['Grado'] = df['Grupo'].astype(str).str.extract(r'(\d+)')[0].fillna('N/A')
        return df
    except:
        return pd.DataFrame()

def format_calif(val):
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

# ==========================================
# 3. DISEÑO CORPORATIVO AUTOADAPTABLE (THEME-AWARE)
# ==========================================
def aplicar_diseno_institucional(compacto=False):
    # Ajuste dinámico de dimensiones para evitar scroll en el login
    padding_banner = "1.1rem 1rem" if compacto else "2.2rem 1.5rem"
    margin_banner = "1rem" if compacto else "2rem"

    st.markdown(
        f"""
        <style>
            /* --- DEFINICIÓN DE PALETA ADAPTABLE DE ACUERDO AL TEMA DEL NAVEGADOR --- */
            @media (prefers-color-scheme: light) {{
                :root {{
                    --bg-principal: #F4F6F9;
                    --texto-principal: #0B1B3D;
                    --texto-secundario: #2C3E50;
                    --card-bg: #FFFFFF;
                    --chip-bg: #0B1B3D;
                    --chip-text: #FFFFFF;
                    --tab-active: #0B1B3D;
                    --tab-inactive: #7F8C8D;
                    --dorado-miraflores: #C5A059;
                }}
            }}

            @media (prefers-color-scheme: dark) {{
                :root {{
                    --bg-principal: #0F172A;
                    --texto-principal: #F8FAFC;
                    --texto-secundario: #CBD5E1;
                    --card-bg: #1E293B;
                    --chip-bg: #334155;
                    --chip-text: #F1F5F9;
                    --tab-active: #C5A059;
                    --tab-inactive: #94A3B8;
                    --dorado-miraflores: #C5A059;
                }}
            }}

            #MainMenu {{visibility: hidden;}}
            footer {{visibility: hidden;}}
            
            /* Ajuste del canvas de la app */
            .stApp {{
                background-color: var(--bg-principal) !important;
            }}

            /* --- 🎨 BARRA LATERAL (SIDEBAR) --- */
            [data-testid="stSidebar"] {{
                background-color: #0B1B3D !important;
                border-right: 3px solid var(--dorado-miraflores);
            }}
            
            [data-testid="stSidebar"] h1, 
            [data-testid="stSidebar"] h2, 
            [data-testid="stSidebar"] h3, 
            [data-testid="stSidebar"] p, 
            [data-testid="stSidebar"] label, 
            [data-testid="stSidebar"] span,
            [data-testid="stSidebar"] div {{
                color: #FFFFFF !important;
            }}
            
            [data-testid="stSidebar"] div[data-testid="stRadio"] label p {{
                color: #FFFFFF !important;
                font-weight: 500 !important;
            }}

            /* --- 🛡️ TEXTOS Y ENCABEZADOS DEL CONTENEDOR CENTRAL --- */
            h1, h2, h3, h4, h5, h6, 
            div[data-testid="stAppViewBlockContainer"] h1,
            div[data-testid="stAppViewBlockContainer"] h2,
            div[data-testid="stAppViewBlockContainer"] h3 {{
                color: var(--texto-principal) !important;
                font-weight: bold !important;
            }}

            /* Etiquetas generales e inputs */
            div[data-testid="stWidgetLabel"] p, 
            label[data-testid="stWidgetLabel"] p,
            .stWidgetLabel p,
            .stMarkdown p {{
                color: var(--texto-secundario) !important;
                font-weight: 600 !important;
            }}
            
            div[data-testid="stCheckbox"] label span p {{
                color: var(--texto-secundario) !important;
                font-weight: 600 !important;
            }}

            /* --- 🏷️ CHIPS (MULTIPLE SELECT) --- */
            div[data-baseweb="tag"] {{
                background-color: var(--chip-bg) !important;
                border: 1px solid var(--dorado-miraflores) !important;
                border-radius: 6px !important;
                padding: 4px 8px !important;
            }}
            
            div[data-baseweb="tag"] span {{
                color: var(--chip-text) !important;
                font-weight: 500 !important;
            }}
            
            div[data-baseweb="tag"] svg {{
                fill: var(--chip-text) !important;
            }}

            /* --- 🎓 TABS --- */
            button[data-baseweb="tab"] {{
                color: var(--tab-inactive) !important;
                border-bottom: 2px solid transparent !important;
                background-color: transparent !important;
                font-weight: 500 !important;
            }}
            
            button[data-baseweb="tab"][aria-selected="true"] {{
                color: var(--tab-active) !important;
                border-bottom-color: var(--dorado-miraflores) !important;
                font-weight: bold !important;
            }}
            
            button[data-baseweb="tab"][aria-selected="true"] p {{
                color: var(--tab-active) !important;
            }}

            /* Banner Superior Institucional */
            .header-banner {{
                background-color: #0B1B3D;
                color: white !important;
                padding: {padding_banner};
                border-radius: 8px;
                margin-bottom: {margin_banner};
                text-align: center;
                border-bottom: 4px solid var(--dorado-miraflores);
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
            }}
            
            .header-banner * {{
                color: white !important;
            }}
            
            .banner-titulo {{
                font-family: 'Cinzel', 'Times New Roman', serif;
                font-size: 2.1rem;
                font-weight: bold;
                letter-spacing: 2px;
                margin: 0;
            }}
            
            .banner-sub {{
                font-size: 1rem;
                margin-top: 0.5rem;
                font-weight: 300;
                letter-spacing: 1px;
            }}

            /* Tarjetas de Información */
            .card-conducta {{
                background-color: var(--card-bg) !important;
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                border-left: 5px solid var(--dorado-miraflores);
                margin-bottom: 1rem;
            }}

            /* Estilización de Botones de Streamlit */
            div.stButton > button:first-child {{
                background-color: #0B1B3D;
                color: white !important;
                border: 1px solid var(--dorado-miraflores);
                border-radius: 4px;
                padding: 0.5rem 1.5rem;
                font-weight: 600;
                transition: all 0.3s ease;
                width: 100%;
            }}
            
            div.stButton > button:first-child:hover {{
                background-color: var(--dorado-miraflores);
                border-color: var(--dorado-miraflores);
                color: white !important;
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }}

            /* --- 🔑 BOTÓN DE ACCESO INTEGRADO EN TARJETA --- */
            .custom-google-btn {{
                display: inline-block;
                background-color: #0B1B3D;
                color: white !important;
                border: 2px solid var(--dorado-miraflores);
                border-radius: 4px;
                padding: 0.65rem 2rem;
                font-weight: 600;
                text-decoration: none !important;
                transition: all 0.3s ease;
                margin-top: 1rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.15);
            }}
            
            .custom-google-btn:hover {{
                background-color: var(--dorado-miraflores);
                border-color: var(--dorado-miraflores);
                color: white !important;
                box-shadow: 0 4px 8px rgba(0,0,0,0.25);
                text-decoration: none !important;
            }}
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="header-banner">
            <div class="banner-titulo">COLEGIO MIRAFLORES</div>
            <div class="banner-sub">SISTEMA INTEGRAL DE GESTIÓN CONDUCTUAL</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================================
# 4. COMPONENTE ANALÍTICO MULTI-FILTRO
# ==========================================
def mostrar_tablero_analitico(df, titulo_contexto, modo_descarga=True):
    if df.empty:
        st.info("No hay datos registrados con los filtros seleccionados.")
        return

    df['Fecha'] = pd.to_datetime(df['Fecha'])
    t_sem, t_mes, t_per = st.tabs(["📅 Semanal", "🗓️ Mensual", "🎓 Periodo Lectivo"])

    with t_sem:
        df_s = df[df['Fecha'] >= (datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(days=7))].copy()
        if not df_s.empty:
            st.dataframe(df_s.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else:
            st.success("Sin reportes esta semana.")

    with t_mes:
        df_m = df[df['Fecha'].dt.month == datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None).month].copy()
        if not df_m.empty:
            res = df_m.groupby(['Grupo', 'Alumno', 'Falta']).size().reset_index(name='Veces')
            st.dataframe(res.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros este mes.")

    with t_per:
        hoy = datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None)
        pers = [p for p in PERIODOS_LECTIVOS if datetime.strptime(p['inicio'], '%Y-%m-%d') <= hoy]
        sel_p = st.selectbox(f"Periodo ({titulo_contexto}):", [p['nombre'] for p in pers], index=len(pers)-1, key=f"per_{titulo_contexto}")
        p_inf = next(p for p in pers if p['nombre'] == sel_p)
        
        df_p = df[(df['Fecha'] >= p_inf['inicio']) & (df['Fecha'] <= p_inf['fin'])].copy()
        if not df_p.empty:
            df_p['Puntos_Descontados'] = pd.to_numeric(df_p['Puntos_Descontados'], errors='coerce').fillna(0)
            boleta = df_p.groupby(['Grupo', 'Alumno'])['Puntos_Descontados'].sum().reset_index()
            boleta['Promedio'] = (10 + (boleta['Puntos_Descontados'] / 5)).clip(0, 10)
            boleta['Calificación'] = boleta['Promedio'].apply(format_calif)
            
            st.dataframe(boleta[['Grupo', 'Alumno', 'Calificación']].sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
            if modo_descarga:
                st.download_button("📥 Descargar Excel", boleta.to_csv(index=False).encode('utf-8'), f"Reporte_{sel_p}.csv")
        else:
            st.success("Sin incidencias en el periodo.")

# ==========================================
# 5. PANELES POR ROL
# ==========================================
def renderizar_panel_docente(gc, usuario, nombre_prof):
    st.header(f"🛡️ Panel Docente: {nombre_prof}")
    
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
        
    with st.expander("📝 Registro de Incidencia", expanded=True):
        reporte_pasillo = st.checkbox("🚨 ¿Es un reporte de pasillo / fuera de clase?", key=f"pasillo_{st.session_state.form_reset}")
        st.markdown("---")
        
        materia = "Pasillo / Inst. General"
        grupo_final = []
        alumnos_final = ["General (Ver observaciones)"] 
        
        # --- SELECCIÓN DE ALUMNOS (PASILLO O GRUPO CLASE) ---
        if reporte_pasillo:
            c1, c2, c3 = st.columns(3)
            nivel = c1.selectbox("Nivel:", ["Secundaria", "Preparatoria"], key=f"niv_{st.session_state.form_reset}")
            opciones_grados = ["1°", "2°", "3°"] if nivel == "Secundaria" else ["4°", "5°", "6°"]
            
            grados_sel = c2.multiselect("Grado(s):", opciones_grados, key=f"grad_{st.session_state.form_reset}")
            
            grupos_disponibles = []
            df_asig_global = leer_datos(gc, FILE_ASIGNACIONES)
            
            if not df_asig_global.empty and 'Grupo' in df_asig_global.columns:
                todos_los_grupos = df_asig_global['Grupo'].dropna().astype(str).unique().tolist()
                if grados_sel:
                    for grad_individual in grados_sel:
                        numero_grado = grad_individual.replace("°", "") 
                        grupos_del_grado = [g for g in todos_los_grupos if g.startswith(f"{numero_grado}°")]
                        grupos_disponibles.extend(grupos_del_grado)
                    grupos_disponibles = sorted(list(set(grupos_disponibles)))
            else:
                if grados_sel:
                    for grad_individual in grados_sel:
                        grupos_disponibles.extend([f"{grad_individual}A", f"{grad_individual}B"])
                    grupos_disponibles = sorted(grupos_disponibles)
            
            grupos_sel = c3.multiselect("Grupo(s) implicado(s):", grupos_disponibles, key=f"grups_p_{st.session_state.form_reset}")
            grupo_final = grupos_sel
            
            alumnos_por_grupo_seleccionados = []
            if grupos_sel:
                st.markdown("**Selecciona a los alumnos involucrados por salón:**")
                pestañas = st.tabs(grupos_sel) 
                
                for idx, g_sel in enumerate(grupos_sel):
                    with pestañas[idx]:
                        try:
                            df_al = leer_datos(gc, FILE_ALUMNOS, g_sel)
                            if not df_al.empty and 'Nombre' in df_al.columns:
                                lista_grupo = sorted(df_al['Nombre'].dropna().unique().tolist())
                                sel_alumnos = st.multiselect(
                                    f"Implicados de {g_sel}:", 
                                    lista_grupo, 
                                    key=f"al_{g_sel}_{st.session_state.form_reset}"
                                )
                                if sel_alumnos:
                                    for nombre in sel_alumnos:
                                        alumnos_por_grupo_seleccionados.append((g_sel, nombre))
                        except Exception:
                            st.warning(f"⚠️ No se encontró la base de datos para {g_sel}")
                
                if alumnos_por_grupo_seleccionados:
                    alumnos_final = [nombre for _, nombre in alumnos_por_grupo_seleccionados]
        else:
            df_asig = leer_datos(gc, FILE_ASIGNACIONES)
            mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
            if mis_asig.empty: 
                st.warning("Sin materias asignadas.")
                return
            
            c1, c2 = st.columns(2)
            materia = c1.selectbox("Materia:", mis_asig['Materia'].unique())
            grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique())
            grupo_final = [grupo]
            
            captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
            
            try:
                opc = leer_datos(gc, FILE_ALUMNOS, grupo)['Nombre'].tolist()
            except Exception:
                opc = []
                st.error(f"Falta la pestaña '{grupo}' en el archivo 1_Alumnos_por_Grupo")
            
            if not captura_multiple:
                alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
                alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
            else:
                alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")

        st.markdown("---")
        
        # =================================================================
        # 🪄 CLASIFICADOR AUTOMÁTICO DE FALTAS CON GEMINI AI
        # =================================================================
        st.markdown("#### 🪄 Asistente de Clasificación con IA")
        relato_incidencia = st.text_area(
            "Describe lo sucedido con tus propias palabras:",
            placeholder="Ejemplo: El alumno llegó 15 minutos tarde a clase de Historia sin justificante y comenzó a distraer a sus compañeros.",
            key=f"relato_ia_{st.session_state.form_reset}",
            help="Escribe detalladamente los hechos y haz clic en el botón de abajo para clasificar la categoría y la falta automáticamente."
        )

        # Claves de control de estado dinámico ligadas al ciclo del formulario activo
        key_cat_recomendada = f"ia_cat_{st.session_state.form_reset}"
        key_fal_recomendada = f"ia_fal_{st.session_state.form_reset}"

        if key_cat_recomendada not in st.session_state:
            st.session_state[key_cat_recomendada] = list(CATALOGO_SANCIONES.keys())[0]
        if key_fal_recomendada not in st.session_state:
            st.session_state[key_fal_recomendada] = None

        if st.button("🪄 Clasificar con IA", type="secondary", key=f"btn_ia_{st.session_state.form_reset}"):
            if not relato_incidencia.strip():
                st.warning("⚠️ Por favor, redacta los hechos antes de solicitar la clasificación con IA.")
            else:
                try:
                    # 🔍 ALGORITMO DE BÚSQUEDA PROFUNDA DE LA LLAVE GEMINI
                    api_key_gemini = None
                    
                    # 1. Intentamos buscar la llave en la raíz del archivo (mayúsculas o minúsculas)
                    api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                    
                    # 2. Si no está en la raíz, recorremos de forma inteligente cada subsección de los secretos
                    if not api_key_gemini:
                        for seccion_key in st.secrets.keys():
                            contenido_seccion = st.secrets[seccion_key]
                            # Verificamos si la sección es un diccionario (como [auth] o [smtp])
                            if isinstance(contenido_seccion, dict) or hasattr(contenido_seccion, "get"):
                                api_key_gemini = contenido_seccion.get("GEMINI_API_KEY") or contenido_seccion.get("gemini_api_key")
                                if api_key_gemini:
                                    break # Encontrada, salimos del ciclo
                    
                    # 3. Si tras la búsqueda profunda sigue sin aparecer, mostramos diagnóstico claro
                    if not api_key_gemini:
                        st.error("🔑 Error de Configuración: La llave 'GEMINI_API_KEY' no se encuentra registrada en los secretos de Streamlit.")
                        st.info("💡 **Diagnóstico de Soporte:**")
                        st.write("Las secciones que tu servidor de Streamlit SÍ está detectando actualmente en tu consola son:", list(st.secrets.keys()))
                    else:
                        # Configuración segura del SDK de Google con la clave localizada
                        genai.configure(api_key=api_key_gemini)
                        modelo_gemini = genai.GenerativeModel('gemini-3.5-flash')
                        
                        prompt_sistema = f"""
                        Eres un asistente de disciplina del Colegio Miraflores. Analiza la siguiente descripción de incidencia y clasifícala estrictamente dentro de las opciones de nuestro catálogo oficial.
                        
                        CATÁLOGO DE INCIDENCIAS:
                        {json.dumps(CATALOGO_SANCIONES, ensure_ascii=False, indent=2)}
                        
                        INCIDENCIA REPORTADA:
                        "{relato_incidencia}"
                        
                        INSTRUCCIONES:
                        1. Identifica qué "Categoría" y qué "Falta" específica del catálogo se asocian mejor al relato.
                        2. Debes responder EXCLUSIVAMENTE en formato JSON plano con la siguiente estructura exacta:
                        {{
                            "categoria": "Nombre Exacto de la Categoría",
                            "falta": "Nombre Exacto de la Falta"
                        }}
                        
                        Asegúrate de respetar de forma estricta los acentos, mayúsculas y la ortografía del catálogo oficial provisto. No agregues bloques de código como ```json ni texto adicional.
                        """
                        
                        with st.spinner("🪄 Analizando hechos con Inteligencia Artificial..."):
                            respuesta_api = modelo_gemini.generate_content(
                                prompt_sistema,
                                generation_config={"response_mime_type": "application/json"}
                            )
                            
                            datos_clasificados = json.loads(respuesta_api.text.strip())
                            cat_ia = datos_clasificados.get("categoria")
                            fal_ia = datos_clasificados.get("falta")
                            
                            # Validación de integridad de la respuesta contra nuestro catálogo estructurado
                            if cat_ia in CATALOGO_SANCIONES:
                                st.session_state[key_cat_recomendada] = cat_ia
                                if fal_ia in CATALOGO_SANCIONES[cat_ia]:
                                    st.session_state[key_fal_recomendada] = fal_ia
                                    st.success(f"✅ IA sugirió: **{cat_ia}** ➔ **{fal_ia}**")
                                else:
                                    st.session_state[key_fal_recomendada] = None
                                    st.success(f"✅ IA sugirió la categoría **{cat_ia}**. Por favor, selecciona la falta manualmente.")
                            else:
                                st.warning("⚠️ La sugerencia de la IA no coincidió exactamente con el catálogo. Proceda de manera manual.")
                
                except Exception as e:
                    st.error(f"⚠️ El clasificador automático no se encuentra disponible en este momento.")
                    st.warning(f"🔍 Detalle técnico real devuelto por Google: {e}")
        
        st.markdown("---")
        
        # --- MENÚS EN CASCADA DE FALTAS (VINCULADOS AL ESTADO DE LA IA) ---
        c_cat, c_fal = st.columns(2)
        
        # 1. Selector de Categorías con índice autoadaptable
        lista_categorias = list(CATALOGO_SANCIONES.keys())
        try:
            indice_categoria_defecto = lista_categorias.index(st.session_state[key_cat_recomendada])
        except ValueError:
            indice_categoria_defecto = 0
            
        with c_cat:
            categoria = st.selectbox(
                "Categoría:", 
                lista_categorias, 
                index=indice_categoria_defecto, 
                key=f"cat_{st.session_state.form_reset}"
            )
            
        # 2. Selector de Falta cometida con índice autoadaptable
        dict_faltas = CATALOGO_SANCIONES[categoria]
        opciones_visuales = [f"{nombre} ({datos['puntos']} pt)" for nombre, datos in dict_faltas.items()]
        
        indice_falta_defecto = 0
        if st.session_state[key_fal_recomendada]:
            for index_opcion, texto_opcion in enumerate(opciones_visuales):
                if texto_opcion.startswith(st.session_state[key_fal_recomendada]):
                    indice_falta_defecto = index_opcion
                    break
                    
        with c_fal:
            falta_seleccionada_visual = st.selectbox(
                "Falta cometida:", 
                opciones_visuales, 
                index=indice_falta_defecto, 
                key=f"falta_{st.session_state.form_reset}"
            )
            
        falta_original = falta_seleccionada_visual.split(" (")[0]
        
        # Pre-llenamos el área de observaciones final con la descripción redactada arriba
        obs = st.text_area(
            "Redacción final de lo sucedido (Observaciones):", 
            value=relato_incidencia,
            key=f"obs_{st.session_state.form_reset}"
        )

        # --- PROCESAMIENTO DEL GUARDADO ---
        if st.button("Guardar Registro", type="primary"):
            if reporte_pasillo and not grupo_final:
                st.error("⚠️ Por favor, seleccione al menos un grupo implicado en el reporte de pasillo.")
                st.stop()
            elif not reporte_pasillo and not alumnos_final:
                st.error("⚠️ Por favor, seleccione al menos un alumno.")
                st.stop()
                
            info_falta = dict_faltas.get(falta_original)
            p = info_falta["puntos"] if info_falta else 0
            s = info_falta["semaforo"] if info_falta else "Gris"
            
            f = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
            lote = []
            
            if reporte_pasillo:
                if alumnos_por_grupo_seleccionados:
                    for g_real, al_limpio in alumnos_por_grupo_seleccionados:
                        lote.append([f, nombre_prof, materia, g_real, al_limpio, categoria, falta_original, obs, p, s])
                else:
                    for g in grupo_final:
                        lote.append([f, nombre_prof, materia, g, "General (Ver observaciones)", categoria, falta_original, obs, p, s])
            else:
                for g in grupo_final:
                    for al in alumnos_final:
                        lote.append([f, nombre_prof, materia, g, al, categoria, falta_original, obs, p, s])
            
            doc = gc.open(FILE_REGISTROS)
            clase_id = "Reportes_Pasillo" if reporte_pasillo else f"{materia} - {grupo_final[0]}"
            
            try:
                ws = doc.worksheet(clase_id)
            except gspread.exceptions.WorksheetNotFound:
                ws = doc.add_worksheet(title=clase_id, rows="1000", cols="10")
                ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Categoría", "Falta", "Observaciones", "Puntos_Descontados", "Es_Grave"])
            
            ws.append_rows(lote)
            leer_todos_los_registros.clear()
            
            st.session_state.form_reset += 1
            st.success("✅ Incidencia registrada exitosamente en la base de datos.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.subheader("📈 Mi Analítica")
    df_full = leer_todos_los_registros(gc)
    df_doc = df_full[df_full['Profesor'] == nombre_prof] if not df_full.empty else df_full
    mostrar_tablero_analitico(df_doc, "Mis Reportes", modo_descarga=False)

def renderizar_panel_coordinador(gc, area_coordinador):
    st.subheader(f"📋 Monitoreo de Coordinación: Área de {area_coordinador}")
    
    df_incidencias = leer_todos_los_registros(gc)
    df_asig = leer_datos(gc, FILE_ASIGNACIONES)
    
    if df_asig.empty:
        st.error("No se pudo cargar el archivo de asignaciones docentes.")
        return

    if 'Area' in df_asig.columns and 'Materia' in df_asig.columns:
        materias_del_area = df_asig[df_asig['Area'] == area_coordinador]['Materia'].unique().tolist()
    else:
        st.error("Estructura de columnas incorrecta en la plantilla docente.")
        return

    if df_incidencias.empty:
        st.info("No se han reportado incidencias en el sistema de forma global.")
    else:
        df_coordinacion = df_incidencias[df_incidencias['Materia'].isin(materias_del_area)]
        if df_coordinacion.empty:
            st.warning(f"Sin incidencias registradas en el área de {area_coordinador}.")
        else:
            st.write(f"Incidencias encontradas en tu coordinación: **{len(df_coordinacion)}**")
            columnas_coordinador = [col for col in ['Fecha', 'Profesor', 'Materia', 'Grupo', 'Alumno', 'Categoría', 'Falta', 'Observaciones', 'Puntos_Descontados'] if col in df_coordinacion.columns]
            
            if 'Fecha' in df_coordinacion.columns:
                df_coordinacion = df_coordinacion.sort_values(by='Fecha', ascending=False)
                
            st.dataframe(df_coordinacion[columnas_coordinador], use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("📊 Analítica del Departamento")
            mostrar_tablero_analitico(df_coordinacion, f"Coordinación {area_coordinador}", modo_descarga=True)


def renderizar_panel_directivo(gc):
    st.header("📊 Inteligencia Institucional (Directivo)")
    df_full = leer_todos_los_registros(gc)
    
    if df_full.empty:
        st.info("Base de datos de registros vacía.")
        return

    df_pasillo = df_full[df_full['Materia'] == "Pasillo / Inst. General"]
    if not df_pasillo.empty:
        df_pasillo['Fecha_DT'] = pd.to_datetime(df_pasillo['Fecha'], errors='coerce')
        hoy = datetime.now(ZoneInfo("America/Mexico_City"))
        limite_tiempo = hoy - timedelta(days=1)
        alertas_recientes = df_pasillo[df_pasillo['Fecha_DT'] >= limite_tiempo.replace(tzinfo=None)]
        
        if not alertas_recientes.empty:
            num_alertas = len(alertas_recientes)
            if st.session_state.get("memoria_alertas_pasillo") != num_alertas:
                st.toast(f"🚨 Tienes {num_alertas} reporte(s) de pasillo reciente(s).", icon="🚨")
                st.session_state["memoria_alertas_pasillo"] = num_alertas
            
            st.warning(f"🔔 **ALERTAS PRIORITARIAS:** Se han registrado {num_alertas} incidencias fuera de clase en las últimas 24 horas.")
            with st.expander("👀 Ver Detalles de Reportes de Pasillo", expanded=True):
                cols_alerta = ["Fecha", "Profesor", "Grupo", "Alumno", "Falta", "Observaciones"]
                cols_validas = [c for c in cols_alerta if c in alertas_recientes.columns]
                st.dataframe(alertas_recientes[cols_validas].sort_values(by="Fecha", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.session_state["memoria_alertas_pasillo"] = 0

    with st.expander("🔍 Filtros de Búsqueda Avanzada", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        df_f = df_full.copy()
        
        grados = ["Todos"] + sorted(df_f['Grado'].astype(str).unique().tolist())
        sel_grado = f1.selectbox("Filtrar Grado:", grados)
        if sel_grado != "Todos":
            df_f = df_f[df_f['Grado'].astype(str) == sel_grado]
            
        grupos = ["Todos"] + sorted(df_f['Grupo'].astype(str).unique().tolist())
        sel_grupo = f2.selectbox("Filtrar Grupo:", grupos)
        if sel_grupo != "Todos":
            df_f = df_f[df_f['Grupo'].astype(str) == sel_grupo]
            
        profs = ["Todos"] + sorted(df_f['Profesor'].astype(str).unique().tolist())
        sel_prof = f3.selectbox("Filtrar Profesor:", profs)
        if sel_prof != "Todos":
            df_f = df_f[df_f['Profesor'].astype(str) == sel_prof]
            
        mats = ["Todos"] + sorted(df_f['Materia'].astype(str).unique().tolist())
        idx_mat = 1 if (len(mats) == 2 and sel_prof != "Todos") else 0
        sel_mat = f4.selectbox("Filtrar Materia:", mats, index=idx_mat)
        if sel_mat != "Todos":
            df_f = df_f[df_f['Materia'].astype(str) == sel_mat]

    mostrar_tablero_analitico(df_f, "Institucional")


# ==========================================
# 6. LANZAMIENTO Y AUTENTICACIÓN (FLUJO SEGURO CON FIRMA DIGITAL)
# ==========================================
import hmac
import hashlib

CLIENT_ID = st.secrets["auth"]["google_client_id"]
CLIENT_SECRET = st.secrets["auth"]["google_client_secret"]
REDIRECT_URI = st.secrets["auth"]["redirect_uri"]

if "auth_email" not in st.session_state:
    st.session_state["auth_email"] = None
if "auth_name" not in st.session_state:
    st.session_state["auth_name"] = None

parametros_url = st.query_params.to_dict()

# --- FUNCIONES AUXILIARES DE SEGURIDAD (HMAC) ---
def generar_firma_segura(correo_usuario):
    """Genera un hash criptográfico único basado en el correo y la clave secreta del servidor."""
    clave_privada = CLIENT_SECRET.encode('utf-8')
    mensaje = correo_usuario.encode('utf-8')
    return hmac.new(clave_privada, mensaje, hashlib.sha256).hexdigest()

def verificar_firma_segura(correo_usuario, firma_recibida):
    """Compara de manera segura si la firma recibida corresponde al correo proporcionado."""
    if not correo_usuario or not firma_recibida:
        return False
    firma_real = generar_firma_segura(correo_usuario)
    return hmac.compare_digest(firma_real, firma_recibida)


# --- 🔄 VALIDACIÓN DE PERSISTENCIA (F5 RESILIENTE) ---
# Si la sesión en memoria se borró, pero tenemos el correo firmado en la URL, restauramos con seguridad
if not st.session_state["auth_email"] and "_p_email" in parametros_url and "_p_sig" in parametros_url:
    correo_candidato = parametros_url["_p_email"].lower().strip()
    firma_candidata = parametros_url["_p_sig"]
    
    if verificar_firma_segura(correo_candidato, firma_candidata):
        st.session_state["auth_email"] = correo_candidato
        st.session_state["auth_name"] = parametros_url.get("_p_name", "Docente Miraflores")
    else:
        st.query_params.clear()


# --- 🔑 PROCESAMIENTO DEL RETORNO DE GOOGLE (HANDSHAKE OAUTH) ---
if "code" in parametros_url and not st.session_state["auth_email"]:
    codigo_autorizacion = parametros_url["code"]
    
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": codigo_autorizacion,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    try:
        response = requests.post(token_url, data=token_data).json()
        access_token = response.get("access_token")
        
        if access_token:
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info = requests.get(userinfo_url, headers=headers).json()
            
            email_capturado = user_info.get("email", "").lower().strip()
            name_capturado = user_info.get("name", "Docente Miraflores")
            
            # Generamos la firma criptográfica para este inicio de sesión verificado por Google
            firma_criptografica = generar_firma_segura(email_capturado)
            
            st.session_state["auth_email"] = email_capturado
            st.session_state["auth_name"] = name_capturado
            
            # Escribimos los parámetros firmados en la URL para sobrevivir a la recarga
            st.query_params["_p_email"] = email_capturado
            st.query_params["_p_sig"] = firma_criptografica
            st.query_params["_p_name"] = name_capturado
            
            st.rerun()
            
    except Exception as e:
        st.error(f"Error en la conexión de seguridad: {e}")


# ==========================================
# FLUJO DE RENDERIZADO DE PANTALLA
# ==========================================

# ESCENARIO A: No hay sesión activa -> Mostrar login corporativo limpio
if not st.session_state.get("auth_email"):
    # Activamos la vista compacta para recortar espacios verticales y evitar scroll
    aplicar_diseno_institucional(compacto=True)
    
    # Generación segura de la URL del flujo OAuth de Google
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online"
    }
    url_google_auth = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    # Renderizado de la tarjeta con el botón configurado en target="_blank" para cumplir con Google
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; align-items: center; padding-top: 0.5rem;">
            <div class="card-conducta" style="text-align: center; max-width: 480px; width: 100%; padding: 2rem 1.5rem; margin: 0 auto;">
                <h3 style="color: var(--texto-principal) !important; margin-bottom: 0.8rem; font-size: 1.5rem;">Acceso de Personal</h3>
                <p style="color: var(--texto-secundario); font-size: 0.92rem; margin-bottom: 1.2rem; line-height: 1.5;">
                    Por favor, inicia sesión con tu cuenta de correo institucional para acceder al panel que te corresponde de manera automática.
                </p>
                <a href="{url_google_auth}" target="_blank" class="custom-google-btn">🔑 Iniciar Sesión con Google</a>
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    st.stop()
    
# ESCENARIO B: Usuario autenticado correctamente con Google
else:
    aplicar_diseno_institucional()
    
    correo_google = st.session_state["auth_email"].lower().strip()
    nombre_google = st.session_state["auth_name"]
    
    # Candado estricto de dominio institucional
    correo_admin = "marcodoleire@gmail.com"  
    if not (correo_google.endswith("@miraflores.edu.mx") or correo_google == correo_admin):
        st.error("⛔ Acceso denegado. Este sistema está restringido exclusivamente para cuentas institucionales @miraflores.edu.mx.")
        
        if st.button("🔑 Cambiar a cuenta del Colegio", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            if hasattr(st, "logout"):
                st.logout()
            st.rerun()
        st.stop()

    try:
        gc = conectar_gsheets()
        df_s = leer_datos(gc, FILE_SEGURIDAD)
        
        if not df_s.empty:
            df_s.columns = df_s.columns.str.strip()
            df_s['Usuario'] = df_s['Usuario'].astype(str).str.lower().str.strip()
            usuario_registrado = df_s[df_s['Usuario'] == correo_google]
        else:
            usuario_registrado = pd.DataFrame()
        
        # --- 🛑 INTERCEPCIÓN DE USUARIOS NUEVOS ---
        if usuario_registrado.empty:
            df_asig_verif = leer_datos(gc, FILE_ASIGNACIONES)
            es_profesor_oficial = False
            
            if not df_asig_verif.empty and 'Usuario_Profesor' in df_asig_verif.columns:
                profesores_validos = [str(email).lower().strip() for email in df_asig_verif['Usuario_Profesor'].dropna().unique()]
                if correo_google in profesores_validos:
                    es_profesor_oficial = True
            
            if correo_google == correo_admin:
                es_profesor_oficial = True

            if not es_profesor_oficial:
                st.error("⛔ Tu correo no forma parte de la plantilla docente del ciclo escolar activo.")
                st.info("Por favor, contacta a tu departamento de Coordinación Académica para ser dado de alta en las asignaciones.")
                
                if st.button("🔑 Intentar con otra cuenta", type="secondary"):
                    st.session_state.clear()
                    st.query_params.clear()
                    if hasattr(st, "logout"):
                        st.logout()
                    st.rerun()
                st.stop()

            # Formulario de autoregistro inicial
            st.title("👋 Registro de Perfil Docente")
            st.info(f"Hola **{nombre_google}**, detectamos tu primer ingreso. Configura tu departamento para activar tus permisos.")
            
            with st.form("form_registro_nuevo"):
                area_seleccionada = st.selectbox("Área / Departamento:", ["Ciencias", "Humanidades", "Matemáticas", "Idiomas", "Tecnología", "Deportes", "Artes", "Otra"])
                
                if st.form_submit_button("Completar Registro y Entrar", type="primary"):
                    ws_seg = gc.open(FILE_SEGURIDAD).sheet1
                    todos_los_usuarios = [str(u).lower().strip() for u in ws_seg.col_values(1)]
                    
                    if correo_google not in todos_los_usuarios:
                        ws_seg.append_row([correo_google, nombre_google, "Docente", area_seleccionada])
                        st.success("✅ Perfil creado exitosamente.")
                    
                    leer_datos.clear()
                    time.sleep(1)
                    st.rerun()
            st.stop()
        
        # --- USUARIO CORRECTAMENTE VALIDADO ---
        rol_assigned = usuario_registrado['Rol'].iloc[0]
        nombre_mostrar = usuario_registrado['Nombre_Profesor'].iloc[0]
        area_usuario = usuario_registrado['Area'].iloc[0] if 'Area' in usuario_registrado.columns else "Ninguna"

        # Barra lateral y selector de vistas
        st.sidebar.title("Configuración de Vista")
        
        # Botón para cerrar sesión dentro del menú lateral
        if st.sidebar.button("🔒 Cerrar Sesión", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            if hasattr(st, "logout"):
                st.logout()
            st.rerun()

        vista_actual = rol_assigned
        if rol_assigned in ['Director', 'Coordinador', 'Directivo']:
            opciones_vista = [f"Ver como {rol_assigned}", "Ver como Docente de Asignatura"]
            seleccion = st.sidebar.radio("Selecciona tu rol para esta sesión:", opciones_vista)
            if seleccion == "Ver como Docente de Asignatura":
                vista_actual = 'Docente'

        # Renderizado de los paneles
        if vista_actual == 'Director' or vista_actual == 'Directivo':
            renderizar_panel_directivo(gc)
        elif vista_actual == 'Coordinador':
            renderizar_panel_coordinador(gc, area_usuario)
        elif vista_actual == 'Docente':
            renderizar_panel_docente(gc, correo_google, nombre_mostrar)

    except Exception as e:
        st.error("🚨 Ocurrió un error al cargar tus permisos del panel.")
        st.write(f"Detalle de la anomalía técnica: {e}")
