"""
Sistema Integral de Gestión Conductual - Colegio Miraflores
----------------------------------------------------------
Versión: 3.1 (Filtros en Cascada y Auto-selección)
Funcionalidades: RBAC, Filtros Multidimensionales Dinámicos, Caché,
Semáforo Visual Institucional y Reportes por Periodo.
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
import os  # <--- Agrega esta línea para poder crear archivos temporales

# ==========================================
# 1. CONFIGURACIÓN Y CATÁLOGO
# ==========================================

# ---> ESTAS 4 LÍNEAS SON LAS QUE FALTAN <---
FILE_ALUMNOS = "1_Alumnos_por_Grupo"
FILE_ASIGNACIONES = "2_Asignaciones_Profesores"
FILE_SEGURIDAD = "3_Usuarios_Seguridad"
FILE_REGISTROS = "4_Base_Conducta_Registros"

CATALOGO_SANCIONES = {
    "Asistencia": {
        "Llegar tarde (Retardo)": {"puntos": -1, "semaforo": "🟡 Leve"},
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
    
    # 1. Si no encuentra la llave en la bóveda, detenemos todo y mostramos el diagnóstico
    if "gcp_json" not in st.secrets:
        st.error("🚨 ERROR CRÍTICO: La llave 'gcp_json' no existe en los secretos de Streamlit.")
        st.write("Lo que Streamlit SÍ está viendo actualmente en tu bóveda es:", list(st.secrets.keys()))
        st.stop()
        
    # 2. Si la encuentra, intentamos leerla
    try:
        creds_dict = json.loads(st.secrets["gcp_json"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 La llave 'gcp_json' existe, pero el texto JSON está mal formado o incompleto: {e}")
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
            # Extracción inteligente del grado usando Regex (ej. "4°A" -> "4")
            df['Grado'] = df['Grupo'].astype(str).str.extract(r'(\d+)')[0].fillna('N/A')
        return df
    except:
        return pd.DataFrame()

def format_calif(val):
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

# ==========================================
# 3. COMPONENTE ANALÍTICO MULTI-FILTRO
# ==========================================
def mostrar_tablero_analitico(df, titulo_contexto, modo_descarga=True):
    if df.empty:
        st.info(f"No hay datos registrados con los filtros seleccionados."); return

    df['Fecha'] = pd.to_datetime(df['Fecha'])
    t_sem, t_mes, t_per = st.tabs(["📅 Semanal", "🗓️ Mensual", "🎓 Periodo Lectivo"])

    with t_sem:
        df_s = df[df['Fecha'] >= (datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(days=7))].copy()
        if not df_s.empty:
            st.dataframe(df_s.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else: st.success("Sin reportes esta semana.")

    with t_mes:
        df_m = df[df['Fecha'].dt.month == datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None).month].copy()
        if not df_m.empty:
            res = df_m.groupby(['Grupo', 'Alumno', 'Falta']).size().reset_index(name='Veces')
            st.dataframe(res.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else: st.info("Sin registros este mes.")

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
        else: st.success("Sin incidencias en el periodo.")

# ==========================================
# 4. PANELES POR ROL
# ==========================================
def renderizar_panel_docente(gc, usuario, nombre_prof):
    st.header(f"🛡️ Panel Docente: {nombre_prof}")
    
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
        
    with st.expander("📝 Registro de Incidencia", expanded=True):
        df_asig = leer_datos(gc, FILE_ASIGNACIONES)
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
        if mis_asig.empty: 
            st.warning("Sin materias asignadas.")
            return
        
        c1, c2 = st.columns(2)
        materia = c1.selectbox("Materia:", mis_asig['Materia'].unique())
        grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique())
        
        captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
        opc = leer_datos(gc, FILE_ALUMNOS, grupo)['Nombre'].tolist()
        
        if not captura_multiple:
            alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
            alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
        else:
            alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")

        st.markdown("---")
        
        # --- NUEVA LÓGICA DE MENÚS EN CASCADA ---
        c_cat, c_fal = st.columns(2)
        
        with c_cat:
            categoria = st.selectbox(
                "Categoría:", 
                list(CATALOGO_SANCIONES.keys()), 
                key=f"cat_{st.session_state.form_reset}"
            )
            
        with c_fal:
            # Obtenemos solo el sub-diccionario de la categoría seleccionada
            dict_faltas = CATALOGO_SANCIONES[categoria]
            # Creamos las etiquetas dinámicas con los puntos incluidos
            opciones_visuales = [f"{nombre} ({datos['puntos']} pt)" for nombre, datos in dict_faltas.items()]
            
            falta_seleccionada_visual = st.selectbox(
                "Falta cometida:", 
                opciones_visuales, 
                key=f"falta_{st.session_state.form_reset}"
            )
            
        # Extraemos el nombre original cortando antes del paréntesis
        falta_original = falta_seleccionada_visual.split(" (")[0]
        
        obs = st.text_area("Observaciones adicionales:", key=f"obs_{st.session_state.form_reset}")

        if st.button("Guardar Registro", type="primary"):
            if alumnos_final:
                # Extraemos datos del sub-diccionario
                p = dict_faltas[falta_original]["puntos"]
                s = dict_faltas[falta_original]["semaforo"]
                
                f = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
                
                # Inyectamos la variable "categoria" real en lugar del texto fijo "Disciplina"
                lote = [[f, nombre_prof, materia, grupo, al, categoria, falta_original, obs, p, s] for al in alumnos_final]
                
                doc = gc.open(FILE_REGISTROS)
                clase_id = f"{materia} - {grupo}"
                try:
                    ws = doc.worksheet(clase_id)
                except gspread.exceptions.WorksheetNotFound:
                    ws = doc.add_worksheet(title=clase_id, rows="1000", cols="10")
                    ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Categoría", "Falta", "Observaciones", "Puntos_Descontados", "Semaforo"])
                
                ws.append_rows(lote)
                leer_todos_los_registros.clear()
                
                st.session_state.form_reset += 1
                
                st.success("✅ Registro institucional completado. Menú listo para nueva captura.")
                st.rerun()
            else:
                st.error("⚠️ Por favor, seleccione al menos un alumno.")

    st.markdown("---")
    st.subheader("📈 Mi Analítica")
    df_full = leer_todos_los_registros(gc)
    df_doc = df_full[df_full['Profesor'] == nombre_prof] if not df_full.empty else df_full
    mostrar_tablero_analitico(df_doc, "Mis Reportes", modo_descarga=False)
    
def renderizar_panel_directivo(gc):
    st.header("📊 Inteligencia Institucional (Directivo)")
    df_full = leer_todos_los_registros(gc)
    
    if df_full.empty:
        st.info("Base de datos vacía."); return

    # --- FILTROS DINÁMICOS EN CASCADA ---
    with st.expander("🔍 Filtros de Búsqueda Avanzada", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        
        # Inicializamos el DataFrame que se irá recortando paso a paso
        df_f = df_full.copy()
        
        # 1. Filtro Grado
        grados = ["Todos"] + sorted(df_f['Grado'].astype(str).unique().tolist())
        sel_grado = f1.selectbox("Filtrar Grado:", grados)
        if sel_grado != "Todos":
            df_f = df_f[df_f['Grado'].astype(str) == sel_grado]
            
        # 2. Filtro Grupo (Depende de Grado)
        grupos = ["Todos"] + sorted(df_f['Grupo'].astype(str).unique().tolist())
        sel_grupo = f2.selectbox("Filtrar Grupo:", grupos)
        if sel_grupo != "Todos":
            df_f = df_f[df_f['Grupo'].astype(str) == sel_grupo]
            
        # 3. Filtro Profesor (Depende de Grupo)
        profs = ["Todos"] + sorted(df_f['Profesor'].astype(str).unique().tolist())
        sel_prof = f3.selectbox("Filtrar Profesor:", profs)
        if sel_prof != "Todos":
            df_f = df_f[df_f['Profesor'].astype(str) == sel_prof]
            
        # 4. Filtro Materia (Depende de Profesor y Grupo - Autoselección si es única)
        mats = ["Todos"] + sorted(df_f['Materia'].astype(str).unique().tolist())
        # Lógica de autoselección: si hay solo 1 materia (ej. ["Todos", "Física"]), selecciona el índice 1 ("Física")
        idx_mat = 1 if (len(mats) == 2 and sel_prof != "Todos") else 0
        sel_mat = f4.selectbox("Filtrar Materia:", mats, index=idx_mat)
        if sel_mat != "Todos":
            df_f = df_f[df_f['Materia'].astype(str) == sel_mat]

    mostrar_tablero_analitico(df_f, "Institucional")

# ==========================================
# 5. LANZAMIENTO Y AUTENTICACIÓN (PASARELA MANUAL COLEGIO MIRAFLORES)
# ==========================================
import urllib.parse
import requests

# 1. Configuración de credenciales desde los Secrets
CLIENT_ID = st.secrets["auth"]["google_client_id"]
CLIENT_SECRET = st.secrets["auth"]["google_client_secret"]
REDIRECT_URI = st.secrets["auth"]["redirect_uri"]

# Inicializamos estados de sesión si no existen
if "auth_email" not in st.session_state:
    st.session_state["auth_email"] = None
if "auth_name" not in st.session_state:
    st.session_state["auth_name"] = None

# 2. CAPTURA DEL RETORNO DE GOOGLE: Verificar si Google nos está regresando un código en la URL
query_params = st.query_params

if "code" in query_params and not st.session_state["auth_email"]:
    codigo_autorizacion = query_params["code"]
    
    # Intercambiamos el código por un token de acceso de forma manual
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
            # Consultamos los datos del usuario usando el token obtenido
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info = requests.get(userinfo_url, headers=headers).json()
            
            # Guardamos la información en el estado de Streamlit
            st.session_state["auth_email"] = user_info.get("email", "")
            st.session_state["auth_name"] = user_info.get("name", "Profesor Miraflores")
            
            # Limpiamos el código de la URL para dejar la dirección limpia
            st.query_params.clear()
            st.rerun()
    except Exception as e:
        st.error(f"Error en la conexión de seguridad: {e}")

# ==========================================
# FLUJO DE RENDERIZADO DE PANTALLA
# ==========================================

# ESCENARIO A: El usuario no ha iniciado sesión -> Mostramos botón de acceso manual
if not st.session_state["auth_email"]:
    st.title("🔒 Acceso Seguro - Colegio Miraflores")
    st.write("Para ingresar al panel de conducta, por favor inicia sesión con tu cuenta institucional.")
    
    # Construimos la URL de Google a mano con los alcances correctos
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online"
    }
    url_google_auth = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    # Renderizamos un enlace elegante en forma de botón principal
    st.markdown(
        f'<a href="{url_google_auth}" target="_self" style="text-decoration:none;">'
        f'<div style="background-color:#FF4B4B;color:white;padding:10px 20px;text-align:center;'
        f'border-radius:5px;font-weight:bold;display:inline-block;cursor:pointer;">'
        f'🔑 Iniciar Sesión con Google'
        f'</div></a>', 
        unsafe_allow_html=True
    )
    st.stop()

# ESCENARIO B: El usuario ya está autenticado de forma manual
else:
    correo_google = st.session_state["auth_email"]
    nombre_google = st.session_state["auth_name"]
    
    # --- EL CANDADO DE DOMINIO ---
    if not correo_google.endswith("@miraflores.edu.mx"):
        st.error("❌ Acceso denegado. Solo se permiten cuentas del dominio @miraflores.edu.mx")
        if st.button("Regresar / Salir"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        st.stop()
        
    else:
        # Conectamos a la base de datos de Google Sheets
        gc = conectar_gsheets()
        df_s = leer_datos(gc, FILE_SEGURIDAD)
        usuario_registrado = df_s[df_s['Usuario'] == correo_google]
        
        if not usuario_registrado.empty:
            rol_asignado = usuario_registrado['Rol'].iloc[0]
            nombre_mostrar = usuario_registrado['Nombre_Profesor'].iloc[0]
        else:
            # Auto-registro en la base de datos si es personal del colegio válido
            ws_seg = gc.open(FILE_SEGURIDAD).sheet1
            ws_seg.append_row([correo_google, "OAuth_Manual", nombre_google, "Docente"])
            rol_asignado = "Docente"
            nombre_mostrar = nombre_google

        # --- PANEL PRINCIPAL DE LA APLICACIÓN ---
        col1, col2 = st.columns([8, 2])
        col1.title("Panel de Conducta Institucional")
        
        if col2.button("Cerrar Sesión", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

        # Despliegue de paneles según el rol asignado
        if rol_asignado == 'Director':
            renderizar_panel_director(gc)
        elif rol_asignado == 'Docente':
            renderizar_panel_docente(gc, correo_google, nombre_mostrar)
        else:
            st.error("Rol no reconocido. Contacte al administrador.")
