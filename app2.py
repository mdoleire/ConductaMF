# app2.py


import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
import os  
import time  
import re
import urllib.parse
import requests
import secrets
import google.generativeai as genai
import hmac
import hashlib
import base64
import json
import logging

from config import (
    FILE_ALUMNOS, 
    FILE_ASIGNACIONES, 
    FILE_SEGURIDAD, 
    FILE_REGISTROS, 
    CATALOGO_SANCIONES, 
    PERIODOS_LECTIVOS,
    REGEX_CORREO_ALUMNO,
    SUPER_USUARIOS_WHITELIST
)
# from database import (
#     conectar_gsheets, 
#     leer_datos, 
#     leer_todos_los_registros, 
#     leer_todas_las_asignaciones
# )
# ✅ AHORA (SQL Instantáneo):
from database import (
    conectar_gsheets, 
    leer_datos, 
    leer_todos_los_registros, 
    leer_todas_las_asignaciones
)

from paneles.tutor import renderizar_panel_tutor
from paneles.directivo import renderizar_panel_directivo
from paneles.coordinador import renderizar_panel_coordinador
from paneles.docente import renderizar_panel_docente
from paneles.asistencia import renderizar_panel_asistencia
from paneles.alumno import renderizar_panel_alumno
from reglamento import TEXTO_ACUERDO
from paneles.calificaciones import renderizar_panel_calificaciones
from streamlit_option_menu import option_menu

# ==========================================
# CONFIGURACIÓN VISUAL (ESTILO AULA MÁGICA + DARK MODE)
# ==========================================
def aplicar_diseno_institucional(compacto=False):
    padding_banner = "1.1rem 1rem" if compacto else "1.5rem 2rem"
    margin_banner = "1rem" if compacto else "2rem"

    st.markdown(
        f"""
        <style>
            /* =========================================
               1. VARIABLES MODO CLARO (Default)
               ========================================= */
            :root {{
                --bg-app: #F8FAFC;
                --bg-sidebar: #FFFFFF;
                --bg-card: #FFFFFF;
                --primario-turquesa: #0DA28D;
                --primario-hover: #0B8A78;
                --azul-noche: #1E2B38;
                --texto-oscuro: #1E293B;
                --texto-gris: #64748B;
                --borde-suave: #E2E8F0;
                --bg-secundario: #F1F5F9;
            }}

            /* =========================================
               2. VARIABLES MODO OSCURO (Automático)
               ========================================= */
            @media (prefers-color-scheme: dark) {{
                :root {{
                    --bg-app: #0F172A;
                    --bg-sidebar: #1E293B;
                    --bg-card: #1E293B;
                    --primario-turquesa: #0DA28D; /* El turquesa brilla hermoso en oscuro */
                    --primario-hover: #14B8A6;
                    --azul-noche: #0B1120; /* Banner casi negro */
                    --texto-oscuro: #F8FAFC; /* Texto blanco brillante */
                    --texto-gris: #94A3B8; /* Texto gris suave */
                    --borde-suave: #334155;
                    --bg-secundario: #334155;
                }}
            }}

            /* =========================================
               3. REGLAS GENERALES APLICADAS
               ========================================= */
            #MainMenu {{visibility: hidden;}}
            footer {{visibility: hidden;}}
            
            /* Fondo general de la App */
            .stApp {{
                background-color: var(--bg-app) !important;
            }}

            /* Menú Lateral */
            [data-testid="stSidebar"] {{
                background-color: var(--bg-sidebar) !important;
                border-right: 1px solid var(--borde-suave);
            }}
            
            [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
            [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, 
            [data-testid="stSidebar"] label {{
                color: var(--texto-oscuro) !important;
            }}

            /* Títulos Generales */
            h1, h2, h3, h4, h5, h6 {{
                color: var(--texto-oscuro) !important;
                font-weight: 700 !important;
            }}

            /* Etiquetas de Texto */
            div[data-testid="stWidgetLabel"] p, label[data-testid="stWidgetLabel"] p {{
                color: var(--texto-gris) !important;
                font-weight: 600 !important;
            }}

            /* Tarjetas Suaves (Glassmorphism ligero) */
            .card-conducta {{
                background-color: var(--bg-card) !important;
                padding: 2rem;
                border-radius: 16px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                border: 1px solid var(--borde-suave);
                margin-bottom: 1.5rem;
            }}

            /* Botones Principales (Turquesa) */
            div.stButton > button:first-child {{
                background-color: var(--primario-turquesa) !important;
                color: white !important;
                border: none !important;
                border-radius: 8px;
                padding: 0.5rem 1.5rem;
                font-weight: 600;
                transition: all 0.2s ease;
                width: 100%;
                box-shadow: 0 2px 4px rgba(13, 162, 141, 0.2);
            }}
            
            div.stButton > button:first-child:hover {{
                background-color: var(--primario-hover) !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(13, 162, 141, 0.3);
            }}

            /* Botones Secundarios */
            button[kind="secondary"] {{
                background-color: var(--bg-secundario) !important;
                color: var(--texto-oscuro) !important;
                border: 1px solid var(--borde-suave) !important;
            }}

            button[kind="secondary"]:hover {{
                border-color: var(--primario-turquesa) !important;
            }}

            /* Banner Superior */
            .header-banner {{
                background-color: var(--azul-noche);
                color: white !important;
                padding: {padding_banner};
                border-radius: 12px;
                margin-bottom: {margin_banner};
                display: flex;
                align-items: center;
                justify-content: space-between;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
            }}
            
            .banner-titulo {{
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 1.6rem;
                font-weight: 700;
                letter-spacing: 0.5px;
                margin: 0;
            }}
            
            .banner-sub {{
                font-size: 0.9rem;
                font-weight: 400;
                color: #94A3B8;
                margin-top: 0.2rem;
            }}

            /* Metricas y Acentos */
            [data-testid="stMetricValue"] {{
                color: var(--primario-turquesa) !important;
            }}

            /* =========================================
               4. SUBMENÚ LATERAL (Radio Buttons convertidos)
               ========================================= */
            /* Ocultar el título "Acción de Conducta:" */
            [data-testid="stSidebar"] div[data-testid="stRadio"] > label {{
                display: none !important;
            }}

            /* Contenedor principal del submenú (Le damos sangría y línea lateral) */
            [data-testid="stSidebar"] div[role="radiogroup"] {{
                margin-left: 2rem !important; /* Sangría alineada al icono principal */
                border-left: 2px solid var(--borde-suave) !important;
                padding-left: 0.5rem !important;
                margin-top: -1rem !important; /* Lo pegamos hacia arriba */
                margin-bottom: 1.5rem !important;
                gap: 0.2rem !important;
            }}

            /* Diseño de cada opción del submenú */
            [data-testid="stSidebar"] label[data-baseweb="radio"] {{
                background-color: transparent !important;
                padding: 0.4rem 0.5rem !important;
                border-radius: 6px !important;
                cursor: pointer;
                transition: background-color 0.2s ease;
                margin: 0 !important;
            }}

            /* Hover (pasar el mouse) */
            [data-testid="stSidebar"] label[data-baseweb="radio"]:hover {{
                background-color: var(--bg-secundario) !important;
            }}

            /* 🚫 DESTRUIR LOS CÍRCULOS FEOS DEL RADIO BUTTON */
            [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {{
                display: none !important;
            }}

            /* Letra del submenú apagada por defecto */
            [data-testid="stSidebar"] label[data-baseweb="radio"] p {{
                color: var(--texto-gris) !important;
                font-size: 0.9rem !important;
                font-weight: 500 !important;
                margin: 0 !important;
            }}

            /* ✨ MAGIA: Cuando la opción está seleccionada */
            [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {{
                background-color: #E6F5F3 !important; /* Fondo turquesa clarito */
                border-left: 3px solid var(--primario-turquesa) !important;
                border-radius: 0 6px 6px 0 !important;
            }}

            /* Letra del submenú encendida (Turquesa oscuro) */
            [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p {{
                color: var(--primario-hover) !important;
                font-weight: 700 !important;
            }}
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="header-banner">
            <div>
                <div class="banner-titulo">Colegio Miraflores</div>
                <div class="banner-sub">Sistema Integral de Gestión Escolar</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =================================================================
# GESTIÓN DE SESIÓN Y OAUTH SEGURO (CON TOKEN CLASSROOM PERSISTENTE)
# =================================================================
import hmac
import hashlib
import json
import zlib
import base64
import requests

CLIENT_ID = st.secrets["auth"]["google_client_id"]
CLIENT_SECRET = st.secrets["auth"]["google_client_secret"]
REDIRECT_URI = st.secrets["auth"]["redirect_uri"]

if "auth_email" not in st.session_state:
    st.session_state["auth_email"] = None
if "auth_name" not in st.session_state:
    st.session_state["auth_name"] = None
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None

parametros_url = st.query_params.to_dict()

# --- 🛡️ MOTOR CRIPTOGRÁFICO: AHORA GUARDA TAMBIÉN EL TOKEN DE CLASSROOM ---
def _cifrar_xor_hmac(datos_bytes, clave_secreta):
    flujo_llave = b""
    contador = 0
    while len(flujo_llave) < len(datos_bytes):
        flujo_llave += hashlib.sha256(f"{clave_secreta}:{contador}".encode('utf-8')).digest()
        contador += 1
    return bytes(a ^ b for a, b in zip(datos_bytes, flujo_llave[:len(datos_bytes)]))

def empaquetar_token_opaco(email, nombre, token_classroom=""):
    """Comprime, cifra y firma la sesión con expiración de 12 horas"""
    payload = json.dumps({
        "e": str(email).lower().strip(), 
        "n": str(nombre).strip(),
        "t": str(token_classroom or "").strip(),
        "exp": int(time.time()) + 43200  # 🛡️ Expira en 12 horas
    }).encode('utf-8')
    comprimido = zlib.compress(payload)
    cifrado = _cifrar_xor_hmac(comprimido, CLIENT_SECRET)
    firma = hmac.new(CLIENT_SECRET.encode('utf-8'), cifrado, hashlib.sha256).digest()[:12]
    return base64.urlsafe_b64encode(firma + cifrado).decode('utf-8')

def desempaquetar_token_opaco(token_str):
    """Verifica firma, descifra y comprueba que la sesión no haya expirado"""
    try:
        raw_bytes = base64.urlsafe_b64decode(token_str.encode('utf-8'))
        firma_recibida = raw_bytes[:12]
        cifrado = raw_bytes[12:]
        firma_calculada = hmac.new(CLIENT_SECRET.encode('utf-8'), cifrado, hashlib.sha256).digest()[:12]
        
        if not hmac.compare_digest(firma_recibida, firma_calculada):
            return None, None, None
            
        comprimido = _cifrar_xor_hmac(cifrado, CLIENT_SECRET)
        datos = json.loads(zlib.decompress(comprimido).decode('utf-8'))
        if int(time.time()) > datos.get("exp", 0):
            return None, None, None
        return datos.get("e"), datos.get("n"), datos.get("t")
    except Exception:
        return None, None, None

# 1. 🔑 RETORNO DESDE GOOGLE OAUTH
if "code" in parametros_url:
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
        res_raw = requests.post(token_url, data=token_data, timeout=10)
        response = res_raw.json()
        
        if "error" in response:
            st.error(f"🚨 Error en Google OAuth: {response.get('error')} - {response.get('error_description')}")
            st.stop()
            
        access_token = response.get("access_token")
        
        if access_token:
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info = requests.get(userinfo_url, headers=headers, timeout=10).json()
            
            email_verificado = user_info.get("email", "").lower().strip()
            nombre_verificado = user_info.get("name", "Docente Miraflores")
            
            st.session_state["auth_email"] = email_verificado
            st.session_state["auth_name"] = nombre_verificado
            st.session_state["access_token"] = access_token
            
            # 🛡️ Empacamos todo cifrado (incluyendo Classroom) para sobrevivir al F5
            token_seguro = empaquetar_token_opaco(email_verificado, nombre_verificado, access_token)
            
            st.query_params.clear()
            st.query_params["session"] = token_seguro
            st.rerun()
            
    except Exception as e:
        st.error(f"Error en la conexión con Google: {e}")
        st.stop()

# 2. 🔄 RESILIENCIA A F5: Restauramos Sesión + Token de Classroom automáticamente
elif not st.session_state.get("auth_email") and "session" in parametros_url:
    token_recibido = parametros_url["session"]
    correo_rec, nombre_rec, token_cr_rec = desempaquetar_token_opaco(token_recibido)
    
    if correo_rec and nombre_rec:
        st.session_state["auth_email"] = correo_rec
        st.session_state["auth_name"] = nombre_rec
        # ✅ RESTAURACIÓN AUTOMÁTICA DEL TOKEN DE CLASSROOM:
        if token_cr_rec:
            st.session_state["access_token"] = token_cr_rec
    else:
        st.query_params.clear()
        
# ==========================================
# CONTROL DE PANTALLA PRINCIPAL
# ==========================================

# ESCENARIO A: No hay sesión activa
if not st.session_state.get("auth_email"):
    aplicar_diseno_institucional(compacto=True)

     # ⚠️ MENSAJE PARA LA VERSIÓN DE PRUEBAS (NO OFICIAL)
    st.info("🧪 Servidor de Pruebas: Esta versión es de evaluación y no altera los registros oficiales del colegio.")
    
    # ✅ FIX: Definimos la función de firma HMAC con la clave secreta del servidor
    def firmar_estado(texto):
        return hmac.new(CLIENT_SECRET.encode('utf-8'), str(texto).encode('utf-8'), hashlib.sha256).hexdigest()

    # Generamos el state firmado con la marca de tiempo actual
    ahora_ts = str(int(time.time()))
    state_token = f"{ahora_ts}:{firmar_estado(ahora_ts)}"

    if "oauth_state" not in st.session_state:
        st.session_state["oauth_state"] = state_token

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.students.readonly https://www.googleapis.com/auth/classroom.rosters.readonly",
        "access_type": "online",
        "state": st.session_state.get("oauth_state", secrets.token_urlsafe(16)),    
        }

    url_google_auth = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    # IMPORTANTE: target="_self" para que navegue en la misma pestaña y no rompa la sesión
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; align-items: center; padding-top: 0.5rem;">
            <div class="card-conducta" style="text-align: center; max-width: 480px; width: 100%; padding: 2rem 1.5rem; margin: 0 auto;">
                <h3 style="color: var(--texto-principal) !important; margin-bottom: 0.8rem; font-size: 1.5rem;">Portal de Acceso</h3>
                <p style="color: var(--texto-secundario); font-size: 0.92rem; margin-bottom: 1.2rem; line-height: 1.5;">
                    Ingresa con tu cuenta institucional para dirigirte a tu panel asignado.
                </p>
                <a href="{url_google_auth}" target="_blank" class="custom-google-btn">🔑 Iniciar Sesión con Google</a>
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    st.stop()

# ESCENARIO B: Sesión autenticada
else:
    aplicar_diseno_institucional()

    #Mensaje de advertencia para la versión de prueba (NO OFICIAL)!!!!!
    st.warning("🧪 **AVISO:** Esta es una versión de prueba. Los registros y cambios que se realizan aquí no son oficiales.")

    # 1. Guardamos tu identidad original intocable
    correo_real = st.session_state["auth_email"].lower().strip()
    nombre_real = st.session_state["auth_name"]

    # 2. Candado estricto de dominio institucional
    dominio_valido = correo_real.endswith("@miraflores.edu.mx")
    es_admin_externo = correo_real in SUPER_USUARIOS_WHITELIST
    
    if not (dominio_valido or es_admin_externo):
        st.error("⛔ Acceso denegado. Este sistema está restringido a cuentas autorizadas del Colegio Miraflores.")
        if st.button("🔑 Iniciar con otra cuenta", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        st.stop()

    gc = conectar_gsheets()

    # --- 👑 MODO SUPERUSUARIO (SIMULACIÓN DE IDENTIDAD) ---
    correo_google = correo_real
    nombre_google = nombre_real

    if es_admin_externo:
        # Extraemos la lista de todos los profesores registrados
        df_s_all = leer_datos(gc, FILE_SEGURIDAD)
        
        if not df_s_all.empty and 'Usuario' in df_s_all.columns:
            usuarios_bd = sorted(df_s_all['Usuario'].dropna().astype(str).str.lower().str.strip().unique().tolist())
            lista_usuarios = ["(Mi cuenta real)"] + usuarios_bd
            
            if "impersonated_email" not in st.session_state:
                st.session_state["impersonated_email"] = "(Mi cuenta real)"
                
            st.sidebar.markdown("### 👑 Modo Dios (Admin)")
            usuario_simulado = st.sidebar.selectbox(
                "Simular vista como:",
                lista_usuarios,
                index=lista_usuarios.index(st.session_state["impersonated_email"]) if st.session_state["impersonated_email"] in lista_usuarios else 0
            )
            
            # Si cambias el selector, recargamos la app con la nueva identidad
            if usuario_simulado != st.session_state["impersonated_email"]:
                st.session_state["impersonated_email"] = usuario_simulado
                st.rerun()
                
            # Si estás simulando, sobreescribimos las variables de trabajo
            if st.session_state["impersonated_email"] != "(Mi cuenta real)":
                correo_google = st.session_state["impersonated_email"]
                try:
                    nombre_google = df_s_all[df_s_all['Usuario'].str.lower().str.strip() == correo_google]['Nombre_Profesor'].iloc[0]
                except:
                    nombre_google = "Usuario Simulado"
                
                st.sidebar.success(f"👁️ Viendo sistema como:\n**{nombre_google}**")
                st.sidebar.markdown("---")

    # 3. ENRUTAMIENTO ESTUDIANTIL
    es_alumno = bool(re.search(REGEX_CORREO_ALUMNO, correo_google))
    
    # 🚨 =========================================================
    # 🧪 INYECCIÓN DIRECTA DE ALUMNO (BYPASS TOTAL)
    # =========================================================
    # Para probar como alumno, descomenta estas dos líneas:
    #correo_google = "bgonzalez.alm9170@miraflores.edu.mx"
    #es_alumno = True
    # ─────────────────────────────────────────────────────────

    if es_alumno:
        renderizar_panel_alumno(gc, correo_google)
        st.stop()

    # 4. ENRUTAMIENTO DE PERSONAL (DOCENTES, COORDINADORES Y DIRECTIVOS)
    try:
        df_s = leer_datos(gc, FILE_SEGURIDAD)
        
        if not df_s.empty:
            df_s.columns = df_s.columns.str.strip()
            df_s['Usuario'] = df_s['Usuario'].astype(str).str.lower().str.strip()
            usuario_registrado = df_s[df_s['Usuario'] == correo_google]
        else:
            usuario_registrado = pd.DataFrame()
        
        # Intercepción de personal nuevo no registrado en archivo 3_Usuarios_Seguridad
        if usuario_registrado.empty:
            es_profesor_oficial = False
            
            # 🛡️ FIX VIP: Si es Modo Dios, entra sin hacer filas ni revisar excels
            if es_admin_externo:
                es_profesor_oficial = True
            else:
                # Si es un simple mortal, que haga fila y revise el Excel
                df_asig_verif = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
                if not df_asig_verif.empty and 'Usuario_Profesor' in df_asig_verif.columns:
                    profesores_validos = [str(email).lower().strip() for email in df_asig_verif['Usuario_Profesor'].dropna().unique()]
                    if correo_google in profesores_validos:
                        es_profesor_oficial = True

            if not es_profesor_oficial:
                st.error("⛔ Tu cuenta no se encuentra en la plantilla del personal activo del Colegio.")
                st.warning(f"🔍 Cuenta detectada: **'{correo_google}'**")
                if st.button("🔑 Intentar con otra cuenta", type="secondary"):
                    st.session_state.clear()
                    st.query_params.clear()
                    st.rerun()
                st.stop()

            # Autoregistro inicial
            st.title("👋 Registro de Perfil Docente")
            st.info(f"Hola **{nombre_google}**, detectamos tu primer ingreso. Configura tu departamento para activar tus permisos.")
            
            with st.form("form_registro_nuevo"):
                area_seleccionada = st.selectbox(
                    "Área / Departamento:", 
                    ["Ciencias", "Humanidades", "Matemáticas", "Idiomas", "Tecnología", "Deportes", "Artes", "Otra"]
                )
                
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
        
        # Extracción de roles oficiales
        rol_assigned = str(usuario_registrado['Rol'].iloc[0]).strip().capitalize()
        nombre_mostrar = usuario_registrado['Nombre_Profesor'].iloc[0]
        area_usuario = usuario_registrado['Area'].iloc[0] if 'Area' in usuario_registrado.columns else "Ninguna"

        # Barra lateral de navegación
        st.sidebar.title("⚙️ Navegación")

        # ⚠️ Mensaje de advertencia para la versión de prueba!!!!!!!!!!!!
        st.sidebar.caption("⚠️ *Versión de prueba (Cambios no oficiales)*")

        if st.sidebar.button("🔒 Cerrar Sesión", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

        # Detección de tutoría
        df_asig_check = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
        mis_materias_check = []
        if not df_asig_check.empty and 'Usuario_Profesor' in df_asig_check.columns and 'Materia' in df_asig_check.columns:
            df_asig_check['Usuario_Profesor'] = df_asig_check['Usuario_Profesor'].astype(str).str.lower().str.strip()
            mis_materias_check = df_asig_check[df_asig_check['Usuario_Profesor'] == correo_google]['Materia'].tolist()
            
        es_tutor = "Tutor" in mis_materias_check

        # Validación insensible a mayúsculas
        if rol_assigned.lower() == 'docente':
            opciones_vista = ["📅 Pasar Lista", "📝 Reportar Conducta", "📊 Calificaciones"]
        else:
            opciones_vista = ["📅 Pasar Lista", f"Ver como {rol_assigned}", "📝 Reportar Conducta", "📊 Calificaciones"]
            
        if es_tutor:
            opciones_vista.append("👤 Ver como Tutor")

    # 🌟 EL NUEVO MENÚ LATERAL TIPO AULA MÁGICA
        iconos = []
        for opc in opciones_vista:
            if "Lista" in opc: iconos.append("calendar2-check")
            elif "Conducta" in opc: iconos.append("shield-exclamation")
            elif "Calificaciones" in opc: iconos.append("journal-bookmark-fill")
            elif "Tutor" in opc: iconos.append("person-vcard")
            else: iconos.append("grid")

        with st.sidebar:
            st.markdown("<br>", unsafe_allow_html=True) # Espacio visual
            seleccion = option_menu(
                menu_title="Menú Principal",
                options=opciones_vista,
                icons=iconos,
                menu_icon="cast",
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "transparent"},
                    "icon": {"color": "#64748B", "font-size": "18px"}, 
                    "nav-link": {
                        "font-size": "15px", 
                        "text-align": "left", 
                        "margin":"4px 0", 
                        "color": "#475569", 
                        "font-weight": "600",
                        "border-radius": "8px"
                    },
                    "nav-link-selected": {
                        "background-color": "#0DA28D", # Turquesa
                        "color": "white", 
                        "icon-color": "white"
                    },
                }
            )            
        if seleccion == "📝 Reportar Conducta":
            vista_actual = 'Docente'
        elif seleccion == "📅 Pasar Lista":
            vista_actual = 'Asistencia'
        elif seleccion == "👤 Ver como Tutor":
            vista_actual = 'Tutor'
        elif seleccion == "📊 Calificaciones":
            vista_actual = 'Calificaciones'
        else:
            vista_actual = rol_assigned

       # Despacho de paneles
        if vista_actual in ['Director', 'Directivo']:
            renderizar_panel_directivo(gc, area_usuario)
            
        elif vista_actual == 'Coordinador':
            renderizar_panel_coordinador(gc, area_usuario)
            
        elif vista_actual == 'Tutor':
            renderizar_panel_tutor(gc, correo_google, nombre_mostrar)
            
        elif vista_actual == 'Docente':
            renderizar_panel_docente(gc, correo_google, nombre_mostrar)
            
        elif vista_actual == 'Asistencia':
            renderizar_panel_asistencia(gc, correo_google, nombre_mostrar)
            
        elif vista_actual == 'Calificaciones':
            renderizar_panel_calificaciones(gc, correo_google, nombre_mostrar)
            
        # ==========================================
        # ASISTENTE DE NORMATIVA (LLM AISLADO CON CACHÉ)
        # ==========================================
        st.sidebar.markdown("---") 
        with st.sidebar.popover("💬 Ayuda / Asistente", use_container_width=True):
            st.markdown("### 🤖 Soporte del Reglamento")
            
            if "chat_ayuda" not in st.session_state:
                st.session_state.chat_ayuda = []
                
            contenedor_chat = st.container(height=350)
            with contenedor_chat:
                if not st.session_state.chat_ayuda:
                    st.info("👋 Asistente oficial del Acuerdo de Convivencia Escolar 2026-2027.")
                for msg in st.session_state.chat_ayuda:
                    st.chat_message(msg["role"]).write(msg["content"])
                    
            c_input, c_btn = st.columns([4, 1])
            duda = c_input.text_input("Escribe tu duda...", label_visibility="collapsed", key="input_duda")
            
            if c_btn.button("Enviar", use_container_width=True):
                if duda.strip():
                    st.session_state.chat_ayuda.append({"role": "user", "content": duda})
                    with st.spinner("Consultando acuerdo..."):
                        try:
                            # 🛡️ Búsqueda segura en segundo plano para la clave de API
                            api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                            if not api_key_gemini:
                                for k in st.secrets.keys():
                                    sec = st.secrets[k]
                                    if isinstance(sec, dict):
                                        api_key_gemini = sec.get("GEMINI_API_KEY") or sec.get("gemini_api_key")
                                        if api_key_gemini: break
                            
                            genai.configure(api_key=api_key_gemini)
                            
                            instrucciones = f"""
                            Eres el asistente normativo oficial del Colegio Miraflores.
                            Tu única fuente de verdad es el Acuerdo de Convivencia Escolar 2026-2027:
                            {TEXTO_ACUERDO}

                            Reglas obligatorias:
                            1. Cita siempre el número de Artículo, Capítulo o Tabla correspondiente.
                            2. Considera que 3 retardos equivalen a 1 falta efectiva.
                            3. Mantén respuestas concisas, amables y estrictamente apegadas al texto.
                            """
                            
                            modelo = genai.GenerativeModel(
                                model_name='gemini-1.5-flash',
                                system_instruction=instrucciones
                            )
                            
                            respuesta = modelo.generate_content(duda)
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": respuesta.text})
                        except Exception:
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": "⚠️ El asistente no se encuentra disponible temporalmente."})
                    
                    st.rerun()

        st.sidebar.markdown("---")
        with st.sidebar.expander("⚙️ Opciones de Sistema"):
            st.caption("Usa esta opción solo si notas un desfase en los registros recientes.")
            if st.button("🔄 Sincronizar Datos", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
                    
    except Exception as e:
        st.error("🚨 Ocurrió un error al cargar los permisos del panel.")
        logging.error(e)
