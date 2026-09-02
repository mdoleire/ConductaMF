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
from config import FILE_ALUMNOS, FILE_ASIGNACIONES, FILE_SEGURIDAD, FILE_REGISTROS, CATALOGO_SANCIONES, PERIODOS_LECTIVOS
from database import conectar_gsheets, leer_datos, leer_todos_los_registros, leer_todas_las_asignaciones
from paneles.tutor import renderizar_panel_tutor
from paneles.directivo import renderizar_panel_directivo
from paneles.coordinador import renderizar_panel_coordinador
from paneles.docente import renderizar_panel_docente
from paneles.asistencia import renderizar_panel_asistencia
from reglamento import TEXTO_ACUERDO

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
            es_profesor_oficial = False
            
            # Usamos la función en caché para no agotar la cuota de Google
            df_asig_verif = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
            
            if not df_asig_verif.empty and 'Usuario_Profesor' in df_asig_verif.columns:
                profesores_validos = [str(email).lower().strip() for email in df_asig_verif['Usuario_Profesor'].dropna().unique()]
                if correo_google in profesores_validos or correo_google == correo_admin:
                    es_profesor_oficial = True

            if not es_profesor_oficial:
                st.error("⛔ Tu correo no forma parte de la plantilla docente activa (ni en Prepa ni en Secundaria).")
                st.warning(f"🔍 El correo detectado es: **'{correo_google}'**")
                
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
        st.sidebar.title("⚙️ Configuración de Vista")
        
        if st.sidebar.button("🔒 Cerrar Sesión", type="secondary"):
            st.session_state.clear()
            st.query_params.clear()
            if hasattr(st, "logout"):
                st.logout()
            st.rerun()

        # 🔍 DETECCIÓN AUTOMÁTICA DE TUTORÍA (Optimizado con caché)
        df_asig_check = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
        mis_materias_check = []
        
        if not df_asig_check.empty and 'Usuario_Profesor' in df_asig_check.columns and 'Materia' in df_asig_check.columns:
            df_asig_check['Usuario_Profesor'] = df_asig_check['Usuario_Profesor'].astype(str).str.lower().str.strip()
            mis_materias_check = df_asig_check[df_asig_check['Usuario_Profesor'] == correo_google]['Materia'].tolist()
            
        es_tutor = "Tutor" in mis_materias_check

        # Construcción dinámica del menú lateral
        vista_actual = rol_assigned
        
        # Si es docente, sus herramientas principales son Conducta y Asistencia
        if rol_assigned == 'Docente':
            opciones_vista = ["📝 Reportar Conducta", "📅 Pasar Lista"]
        else:
            # Si es Director/Coordinador, ve su panel administrativo MÁS las herramientas docentes
            opciones_vista = [f"Ver como {rol_assigned}", "📝 Reportar Conducta", "📅 Pasar Lista"]
            
        if es_tutor:
            opciones_vista.append("👤 Ver como Tutor")

        # Mostramos el menú siempre, ya que todos tendrán al menos 2 opciones
        seleccion = st.sidebar.radio("Navegación del Sistema:", opciones_vista)
            
        # Mapeamos lo que el usuario eligió con el módulo que debe arrancar
        if seleccion == "📝 Reportar Conducta":
            vista_actual = 'Docente'
        elif seleccion == "📅 Pasar Lista":
            vista_actual = 'Asistencia'
        elif seleccion == "👤 Ver como Tutor":
            vista_actual = 'Tutor'
        else:
            vista_actual = rol_assigned

        # --- RENDERIZADO DE LOS PANELES SEGÚN LA VISTA ---
        if vista_actual == 'Director' or vista_actual == 'Directivo':
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
        # 💬 BOTÓN FLOTANTE DE AYUDA (ASISTENTE IA)
        # ==========================================
        st.sidebar.markdown("---") 
        
        # Forzamos la creación dentro del sidebar
        with st.sidebar.popover("💬 Ayuda / Asistente", use_container_width=True):
            st.markdown("### 🤖 Soporte Técnico")
            
            if "chat_ayuda" not in st.session_state:
                st.session_state.chat_ayuda = []
                
            contenedor_chat = st.container(height=350)
            
            with contenedor_chat:
                if not st.session_state.chat_ayuda:
                    st.info("👋 Hola, soy el bot de soporte del Colegio. ¿Tienes dudas sobre cómo pasar lista o usar la plataforma?")
                
                for msg in st.session_state.chat_ayuda:
                    st.chat_message(msg["role"]).write(msg["content"])
                    
            c_input, c_btn = st.columns([4, 1])
            duda = c_input.text_input("Escribe tu duda...", label_visibility="collapsed", key="input_duda")
            
            if c_btn.button("Enviar", use_container_width=True):
                if duda.strip():
                    st.session_state.chat_ayuda.append({"role": "user", "content": duda})
                    
                    with st.spinner("Pensando..."):
                        try:
                            import google.generativeai as genai
                            
                            api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                            if not api_key_gemini:
                                for seccion_key in st.secrets.keys():
                                    contenido = st.secrets[seccion_key]
                                    if isinstance(contenido, dict) or hasattr(contenido, "get"):
                                        api_key_gemini = contenido.get("GEMINI_API_KEY") or contenido.get("gemini_api_key")
                                        if api_key_gemini: break
                            
                            genai.configure(api_key=api_key_gemini)
                            modelo = genai.GenerativeModel('gemini-3.5-flash')
                            
                            prompt_sistema = f"""
                            Eres el asistente virtual experto del Colegio Miraflores. Tu objetivo es orientar a los profesores sobre la plataforma y el Acuerdo de Convivencia Escolar.
                            
                            Aquí tienes el documento oficial completo del ciclo 2026-2027:
                            
                            {TEXTO_ACUERDO}
                            
                            INSTRUCCIONES DE RESPUESTA:
                            1. Responde basándote ÚNICA Y EXCLUSIVAMENTE en el texto del acuerdo proporcionado.
                            2. Si la respuesta requiere citar una sanción o regla, menciona el número de Artículo o el Capítulo exacto.
                            3. Recuerda adicionalmente que en la plataforma del colegio: 3 retardos equivalen a 1 falta efectiva.
                            4. Sé amable, directo y muy conciso. No des respuestas largas a menos que te pidan un listado.
                            
                            Duda del profesor: {duda}
                            """
                            respuesta = modelo.generate_content(prompt_sistema)
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": respuesta.text})
                            
                        except Exception as e:
                            st.session_state.chat_ayuda.append({"role": "assistant", "content": "⚠️ Hubo un error de conexión. Intenta de nuevo más tarde."})
                    
                    st.rerun()
                    
    except Exception as e:
        st.error("🚨 Ocurrió un error al cargar tus permisos del panel.")
        st.write(f"Detalle de la anomalía técnica: {e}")
