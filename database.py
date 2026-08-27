# ==========================================
# 2. MOTOR DE DATOS (CACHÉ Y OPTIMIZACIÓN)
# ==========================================

# database.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from config import FILE_REGISTROS # Importamos desde el archivo config
import pandas as pd 

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

def obtener_lista_alumnos(gc, archivo, pestaña):
    """
    Lee las columnas de alumnos por posición para evitar errores tipográficos
    en los encabezados del Excel y genera un solo nombre limpio.
    """
    try:
        df = leer_datos(gc, archivo, pestaña)
        if df.empty: return []
        
        # Si por alguna razón la columna 'Nombre' ya existe, la usamos
        if 'Nombre' in df.columns:
            nombres = df['Nombre'].fillna('').astype(str)
        else:
            # iloc lee por número de columna (0 es ID, 1 es Paterno, 2 es Materno, 3 es Nombres)
            paterno = df.iloc[:, 1].fillna('').astype(str)
            materno = df.iloc[:, 2].fillna('').astype(str)
            nombres_pila = df.iloc[:, 3].fillna('').astype(str)
            
            # Concatenamos las tres columnas
            nombres = paterno + " " + materno + " " + nombres_pila
            
        # MAGIA DE LIMPIEZA: 
        # Si alguien no tiene materno, quedarían dos espacios en blanco. Esto lo reduce a 1 solo espacio.
        nombres = nombres.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        # Filtramos las filas que quedaron completamente vacías
        nombres = nombres[nombres != '']
        
        # Devolvemos la lista ordenada de la A a la Z
        return sorted(nombres.unique().tolist())
    except Exception as e:
        return []

def leer_todas_las_asignaciones(gc, nombre_archivo):
    """
    Lee las pestañas de Secundaria y Preparatoria y las une en un solo DataFrame
    para que el resto del sistema las procese como una sola lista maestra.
    """
    try:
        df_secundaria = leer_datos(gc, nombre_archivo, "Secundaria")
    except Exception:
        df_secundaria = pd.DataFrame()
        
    try:
        df_prepa = leer_datos(gc, nombre_archivo, "Preparatoria")
    except Exception:
        df_prepa = pd.DataFrame()
        
    # Si ambas están vacías, regresamos un DataFrame vacío para no romper el sistema
    if df_secundaria.empty and df_prepa.empty:
        return pd.DataFrame()
        
    # Fusionamos ambas listas
    df_unificado = pd.concat([df_secundaria, df_prepa], ignore_index=True)
    return df_unificado
