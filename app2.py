# app2.py

from turtle import color

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

# ==========================================
# CONFIGURACIÓN VISUAL
# ==========================================
def aplicar_diseno_institucional(compacto=False):
    padding_banner = "1.1rem 1rem" if compacto else "2.2rem 1.5rem"
    margin_banner = "1rem" if compacto else "2rem"

    st.markdown(
        f"""
        <style>
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
                
                /* MODO OSCURO: Botón del Asistente en blanco */
                [data-testid="stSidebar"] button[kind="secondary"],
                [data-testid="stSidebar"] button[kind="secondary"] *,
                [data-testid="stSidebar"] [data-testid="stPopover"] button,
                [data-testid="stSidebar"] [data-testid="stPopover"] button *,
                [data-testid="stSidebar"] [data-testid="stExpander"] summary,
                [data-testid="stSidebar"] [data-testid="stExpander"] summary * {{
                    color: #FFFFFF !important;
                    fill: #FFFFFF !important;
                    background-color: #1E293B !important;
                }}
            }}

            #MainMenu {{visibility: hidden;}}
            footer {{visibility: hidden;}}
            
            .stApp {{
                background-color: var(--bg-principal) !important;
            }}

            [data-testid="stSidebar"] {{
                background-color: #0B1B3D !important;
                border-right: 3px solid var(--dorado-miraflores);
            }}
            
            /* Regla global: Textos de la barra lateral en blanco */
            [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
            [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, 
            [data-testid="stSidebar"] label, [data-testid="stSidebar"] span,
            [data-testid="stSidebar"] div {{
                color: #FFFFFF !important;
            }}
            
            [data-testid="stSidebar"] div[data-testid="stRadio"] label p {{
                color: #FFFFFF !important;
                font-weight: 500 !important;
            }}

            /* EXCEPCIÓN BARRERA: Botón del Asistente (Modo Claro/Default) */
            /* El asterisco (*) fuerza que todo el contenido interno (iconos, textos) obedezca */
            [data-testid="stSidebar"] button[kind="secondary"],
            [data-testid="stSidebar"] button[kind="secondary"] *,
            [data-testid="stSidebar"] [data-testid="stPopover"] button,
            [data-testid="stSidebar"] [data-testid="stPopover"] button *,
            [data-testid="stSidebar"] [data-testid="stExpander"] summary,
            [data-testid="stSidebar"] [data-testid="stExpander"] summary * {{
                color: #001A3D !important;
                fill: #001A3D !important;
                font-weight: 600 !important;
            }}

            /* Fondo gris claro para el contenedor del botón */
            [data-testid="stSidebar"] button[kind="secondary"],
            [data-testid="stSidebar"] [data-testid="stPopover"] button,
            [data-testid="stSidebar"] [data-testid="stExpander"] {{
                background-color: #F0F4F8 !important; 
                border: none !important;
                border-radius: 6px !important;
            }}

            h1, h2, h3, h4, h5, h6, 
            div[data-testid="stAppViewBlockContainer"] h1,
            div[data-testid="stAppViewBlockContainer"] h2,
            div[data-testid="stAppViewBlockContainer"] h3 {{
                color: var(--texto-principal) !important;
                font-weight: bold !important;
            }}

            div[data-testid="stWidgetLabel"] p, label[data-testid="stWidgetLabel"] p,
            .stWidgetLabel p, .stMarkdown p {{
                color: var(--texto-secundario) !important;
                font-weight: 600 !important;
            }}
            
            div[data-testid="stCheckbox"] label span p {{
                color: var(--texto-secundario) !important;
                font-weight: 600 !important;
            }}

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

            button[data-baseweb="tab"] {{
                color: var(--tab-inactive) !important;
                background-color: transparent !important;
                font-weight: 500 !important;
            }}
            
            button[data-baseweb="tab"][aria-selected="true"] {{
                color: var(--tab-active) !important;
                border-bottom-color: var(--dorado-miraflores) !important;
                font-weight: bold !important;
            }}

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

            .card-conducta {{
                background-color: var(--card-bg) !important;
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                border-left: 5px solid var(--dorado-miraflores);
                margin-bottom: 1rem;
            }}

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
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }}

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
                box-shadow: 0 4px 8px rgba(0,0,0,0.25);
            }}

            /* Forzar visibilidad del texto escrito en el chat de la barra lateral */
            [data-testid="stSidebar"] [data-testid="stChatInput"] textarea {{
                color: #0B1B3D !important;
                -webkit-text-fill-color: #0B1B3D !important;
            }}
            [data-testid="stSidebar"] [data-testid="stChatInput"] textarea::placeholder {{
                color: #7F8C8D !important;
                -webkit-text-fill-color: #7F8C8D !important;
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
# GESTIÓN DE SESIÓN Y OAUTH SEGURO (F5-PROOF)
# ==========================================
CLIENT_ID = st.secrets["auth"]["google_client_id"]
CLIENT_SECRET = st.secrets["auth"]["google_client_secret"]
REDIRECT_URI = st.secrets["auth"]["redirect_uri"]

def firmar_estado(timestamp_str):
    """Firma un timestamp con el Client Secret para validar que el retorno OAuth sea legítimo."""
    return hmac.new(CLIENT_SECRET.encode('utf-8'), timestamp_str.encode('utf-8'), hashlib.sha256).hexdigest()

def crear_token_sesion(correo, nombre):
    """Genera un token opaco y firmado para mantener la sesión viva tras F5 sin exponer datos sensibles."""
    datos = json.dumps({"u": correo, "n": nombre, "t": time.time()})
    payload = base64.urlsafe_b64encode(datos.encode()).decode()
    firma = hmac.new(CLIENT_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}.{firma}"

def resolver_token_sesion(token):
    """Verifica la integridad del token de sesión y recupera la identidad del usuario."""
    try:
        payload, firma = token.split(".", 1)
        firma_esperada = hmac.new(CLIENT_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, firma_esperada):
            return None, None
        
        datos = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        # El token es válido durante 12 horas consecutivas
        if time.time() - datos.get("t", 0) > 43200:
            return None, None
            
        return datos.get("u"), datos.get("n")
    except Exception:
        return None, None

if "auth_email" not in st.session_state:
    st.session_state["auth_email"] = None
if "auth_name" not in st.session_state:
    st.session_state["auth_name"] = None

parametros_url = st.query_params.to_dict()

# --- 1. RESTAURACIÓN AUTOMÁTICA TRAS F5 ---
if not st.session_state["auth_email"] and "_s" in parametros_url:
    u_recup, n_recup = resolver_token_sesion(parametros_url["_s"])
    if u_recup:
        st.session_state["auth_email"] = u_recup
        st.session_state["auth_name"] = n_recup
    else:
        st.query_params.clear()

# --- 2. PROCESAMIENTO DEL RETORNO OAUTH ---
if "code" in parametros_url and not st.session_state["auth_email"]:
    state_recibido = parametros_url.get("state", "")
    
    valido = False
    if ":" in state_recibido:
        ts, sig = state_recibido.split(":", 1)
        firma_esperada = firmar_estado(ts)
        if hmac.compare_digest(sig, firma_esperada):
            try:
                if time.time() - float(ts) < 600:
                    valido = True
            except ValueError:
                pass

    if not valido:
        st.query_params.clear()
        st.rerun()
        
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
        response = requests.post(token_url, data=token_data, timeout=10).json()
        access_token = response.get("access_token")
        
        if access_token:
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info = requests.get(userinfo_url, headers=headers, timeout=10).json()
            
            email_obtenido = user_info.get("email", "").lower().strip()

            ## --- SIMULACIÓN DE ALUMNO (BORRAR DESPUÉS DE LA PRUEBA) ---!!!!!!!!!!!!!
            #email_obtenido = "acruz@miraflores.edu.mx" 
            ## ---------------------------------------------------------!!!!!!!!!!!!!!
            
            name_obtenido = user_info.get("name", "Usuario Miraflores")
            
            st.session_state["auth_email"] = email_obtenido
            st.session_state["auth_name"] = name_obtenido
            
            # Dejamos un token criptográfico opaco en la URL (sin exponer correos)
            st.query_params.clear()
            st.query_params["_s"] = crear_token_sesion(email_obtenido, name_obtenido)
            st.rerun()
            
    except Exception as e:
        st.error(f"Error en la autenticación: {e}")
        st.query_params.clear()
        st.stop()

# ==========================================
# CONTROL DE PANTALLA PRINCIPAL
# ==========================================

# ESCENARIO A: No hay sesión activa
if not st.session_state.get("auth_email"):
    aplicar_diseno_institucional(compacto=True)
    
    # Generamos el state firmado con la marca de tiempo actual
    ahora_ts = str(time.time())
    state_token = f"{ahora_ts}:{firmar_estado(ahora_ts)}"
    
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state_token,
        "prompt": "select_account"
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
                <a href="{url_google_auth}" target="_self" class="custom-google-btn">🔑 Iniciar Sesión con Google</a>
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    st.stop()

# ESCENARIO B: Sesión autenticada
else:
    aplicar_diseno_institucional()
    
    correo_google = st.session_state["auth_email"].lower().strip()
    nombre_google = st.session_state["auth_name"]
    
    # 1. Candado estricto de dominio institucional
    dominio_valido = correo_google.endswith("@miraflores.edu.mx")
    es_admin_externo = correo_google in SUPER_USUARIOS_WHITELIST
    
    if not (dominio_valido or es_admin_externo):
        st.error("⛔ Acceso denegado. Este sistema está restringido a cuentas autorizadas del Colegio Miraflores.")
        if st.button("🔑 Iniciar con otra cuenta", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        st.stop()

    gc = conectar_gsheets()

    # 2. ENRUTAMIENTO ESTUDIANTIL
    es_alumno = bool(re.search(REGEX_CORREO_ALUMNO, correo_google))
    if es_alumno:
        renderizar_panel_alumno(gc, correo_google)
        st.stop()

    # 3. ENRUTAMIENTO DE PERSONAL (DOCENTES, COORDINADORES Y DIRECTIVOS)
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
            df_asig_verif = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if not df_asig_verif.empty and 'Usuario_Profesor' in df_asig_verif.columns:
                profesores_validos = [str(email).lower().strip() for email in df_asig_verif['Usuario_Profesor'].dropna().unique()]
                if correo_google in profesores_validos or es_admin_externo:
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
        
        # Extracción de roles oficiales (Limpiando espacios y forzando mayúscula inicial)
        rol_assigned = str(usuario_registrado['Rol'].iloc[0]).strip().capitalize()
        nombre_mostrar = usuario_registrado['Nombre_Profesor'].iloc[0]
        area_usuario = usuario_registrado['Area'].iloc[0] if 'Area' in usuario_registrado.columns else "Ninguna"

        # Barra lateral de navegación
        st.sidebar.title("⚙️ Navegación")
        
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
            opciones_vista = ["📝 Reportar Conducta", "📅 Pasar Lista"]
        else:
            opciones_vista = [f"Ver como {rol_assigned}", "📝 Reportar Conducta", "📅 Pasar Lista"]
            
        if es_tutor:
            opciones_vista.append("👤 Ver como Tutor")

        seleccion = st.sidebar.radio("Módulo:", opciones_vista)
            
        if seleccion == "📝 Reportar Conducta":
            vista_actual = 'Docente'
        elif seleccion == "📅 Pasar Lista":
            vista_actual = 'Asistencia'
        elif seleccion == "👤 Ver como Tutor":
            vista_actual = 'Tutor'
        else:
            vista_actual = rol_assigned

        # Despacho de paneles
        if vista_actual in ['Director', 'Directivo']:
            renderizar_panel_directivo(gc)
        elif vista_actual == 'Coordinador':
            renderizar_panel_coordinador(gc, area_usuario)
        elif vista_actual == 'Tutor':
            renderizar_panel_tutor(gc, correo_google, nombre_mostrar)
        elif vista_actual == 'Docente':
            renderizar_panel_docente(gc, correo_google, nombre_mostrar)
        elif vista_actual == 'Asistencia':
            renderizar_panel_asistencia(gc, correo_google, nombre_mostrar)

      # ==========================================
        # ASISTENTE DE NORMATIVA (LLM AISLADO)
        # ==========================================
        st.sidebar.markdown("---") 
        with st.sidebar.expander("💬 Ayuda / Asistente"):
            
            # Inicializar historial del chat si no existe
            if "chat_ayuda" not in st.session_state:
                st.session_state.chat_ayuda = []

            # Contenedor con altura fija para evitar desbordes
            contenedor_chat = st.container(height=230)
            
            with contenedor_chat:
                for msg in st.session_state.chat_ayuda:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
            
            # Entrada de chat nativa (queda siempre fija abajo dentro del expander)
            pregunta = st.chat_input("Escribe tu consulta...", key="sidebar_chat_input")
            
            if pregunta:
                if pregunta.strip():
                    st.session_state.chat_ayuda.append({"role": "user", "content": pregunta})
                    
                    with st.spinner("Consultando acuerdo..."):
                        try:
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
                                model_name='gemini-3.6-flash',
                                system_instruction=instrucciones
                            )
                            
                            # Consulta aislada
                            respuesta = modelo.generate_content(pregunta)
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": respuesta.text})
                        except Exception:
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": "⚠️ El asistente no se encuentra disponible temporalmente."})
                    
                    st.rerun()
                    
    except Exception as e:
        st.error("🚨 Ocurrió un error al cargar los permisos del panel.")
        st.caption(f"Detalle técnico: {e}")