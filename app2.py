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

# ==========================================
# 1. CONFIGURACIÓN Y CATÁLOGO
# ==========================================
FILE_ALUMNOS = "1_Alumnos_por_Grupo"
FILE_ASIGNACIONES = "2_Asignaciones_Profesores"
FILE_SEGURIDAD = "3_Usuarios_Seguridad"
FILE_REGISTROS = "4_Base_Conducta_Registros"

CATALOGO_SANCIONES = {
    "Mascar chicle": {"puntos": -1, "semaforo": "🟡 Leve"},
    "Comer en clase": {"puntos": -1, "semaforo": "🟡 Leve"},
    "Distracción en clase": {"puntos": -1, "semaforo": "🟡 Leve"},
    "Material incompleto": {"puntos": -1, "semaforo": "🟡 Leve"},
    "No trabaja en clase": {"puntos": -3, "semaforo": "🟡 Medio"},
    "Salir sin permiso / no entrar": {"puntos": -10, "semaforo": "🔴 Grave"},
    "Agresión verbal al profesor": {"puntos": -10, "semaforo": "🔴 Grave"},
    "Agresión física (compañero/profesor)": {"puntos": -10, "semaforo": "🔴 Grave"},
    "Señas/Acercamientos inapropiados": {"puntos": -10, "semaforo": "🔴 Grave"},
    "Violencia de género": {"puntos": -10, "semaforo": "🟣 Crítica"}
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
@st.cache_resource
def conectar_gsheets():
    """Conexión a Google Cloud usando Streamlit Secrets (Bóveda Segura)"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Intenta leer desde la bóveda de Streamlit Cloud primero
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Si no encuentra la bóveda (porque estás haciendo pruebas en tu PC local), usa el archivo
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    return gspread.authorize(creds)

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
        df_s = df[df['Fecha'] >= (datetime.now() - timedelta(days=7))].copy()
        if not df_s.empty:
            st.dataframe(df_s.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else: st.success("Sin reportes esta semana.")

    with t_mes:
        df_m = df[df['Fecha'].dt.month == datetime.now().month].copy()
        if not df_m.empty:
            res = df_m.groupby(['Grupo', 'Alumno', 'Falta']).size().reset_index(name='Veces')
            st.dataframe(res.sort_values(['Grupo', 'Alumno']), use_container_width=True, hide_index=True)
        else: st.info("Sin registros este mes.")

    with t_per:
        hoy = datetime.now()
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
    
    # 1. Inicializamos el contador de reseteo si no existe en la sesión
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
        
    with st.expander("📝 Registro de Incidencia", expanded=True):
        df_asig = leer_datos(gc, FILE_ASIGNACIONES)
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
        if mis_asig.empty: 
            st.warning("Sin materias asignadas.")
            return
        
        c1, c2 = st.columns(2)
        # Materia y Grupo NO llevan key dinámico para que conserven la selección del profesor
        materia = c1.selectbox("Materia:", mis_asig['Materia'].unique())
        grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia]['Grupo'].unique())
        
        # A los demás controles les concatenamos el contador actual
        captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
        opc = leer_datos(gc, FILE_ALUMNOS, grupo)['Nombre'].tolist()
        
        if not captura_multiple:
            alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
            alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
        else:
            alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")

        falta = st.selectbox("Falta:", list(CATALOGO_SANCIONES.keys()), key=f"falta_{st.session_state.form_reset}")
        obs = st.text_area("Observaciones:", key=f"obs_{st.session_state.form_reset}")

        if st.button("Guardar Registro", type="primary"):
            if alumnos_final:
                p, s = CATALOGO_SANCIONES[falta]["puntos"], CATALOGO_SANCIONES[falta]["semaforo"]
                f = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                lote = [[f, nombre_prof, materia, grupo, al, "Disciplina", falta, obs, p, s] for al in alumnos_final]
                
                doc = gc.open(FILE_REGISTROS)
                clase_id = f"{materia} - {grupo}"
                try:
                    ws = doc.worksheet(clase_id)
                except gspread.exceptions.WorksheetNotFound:
                    ws = doc.add_worksheet(title=clase_id, rows="1000", cols="10")
                    ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Categoría", "Falta", "Observaciones", "Puntos_Descontados", "Semaforo"])
                
                ws.append_rows(lote)
                leer_todos_los_registros.clear()
                
                # --- MAGIA DE LIMPIEZA ---
                # Sumamos 1 al contador. En el st.rerun(), los inputs tendrán
                # nuevos "keys" y se dibujarán en blanco automáticamente.
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
# 5. LANZAMIENTO
# ==========================================
st.set_page_config(page_title="Conducta Miraflores", layout="wide")
if 'autenticado' not in st.session_state: st.session_state['autenticado'] = False

@st.cache_resource
def conectar_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # 1. Verificamos si la bóveda existe y tiene nuestra llave
    if "gcp_json" in st.secrets:
        try:
            # 2. Intentamos traducir el texto a diccionario
            creds_dict = json.loads(st.secrets["gcp_json"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"⚠️ La bóveda existe, pero el texto JSON tiene un error de formato: {e}")
            st.stop()
    else:
        # 3. Si no encuentra la llave, detenemos todo y mostramos qué hay en la bóveda
        st.error("❌ El servidor no encuentra la variable 'gcp_json' en los secretos.")
        try:
            st.write("Llaves que el servidor SÍ está viendo:", list(st.secrets.keys()))
        except:
            st.write("La bóveda está completamente vacía o tiene un error de sintaxis TOML.")
        st.stop()

gc = conectar_gsheets()

if not st.session_state['autenticado']:
    st.title("🔒 Acceso Colegio Miraflores")
    with st.form("login"):
        u, p = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar"):
            df_s = leer_datos(gc, FILE_SEGURIDAD)
            val = df_s[(df_s['Usuario'] == u) & (df_s['Password'] == str(p))]
            if not val.empty:
                st.session_state.update({'autenticado': True, 'usuario_actual': u, 'nombre_profesor': val['Nombre_Profesor'].iloc[0], 'rol': val['Rol'].iloc[0]})
                st.rerun()
            else: st.error("Error de acceso.")
else:
    with st.sidebar:
        st.write(f"👤 **{st.session_state['nombre_profesor']}**")
        st.caption(f"Rol: {st.session_state['rol']}")
        if st.button("Salir"): st.session_state['autenticado'] = False; st.rerun()

    if st.session_state['rol'] in ["Director", "Coordinador"]:
        renderizar_panel_directivo(gc)
    else:
        renderizar_panel_docente(gc, st.session_state['usuario_actual'], st.session_state['nombre_profesor'])
