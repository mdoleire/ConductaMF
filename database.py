# database.py

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import time
from config import FILE_REGISTROS, FILE_ALUMNOS, FILE_ASISTENCIA

@st.cache_resource
def conectar_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_json" not in st.secrets:
        st.error("🚨 ERROR CRÍTICO: La llave 'gcp_json' no existe en los secretos de Streamlit.")
        st.stop()
    try:
        # Permite formato diccionario nativo o cadena JSON
        creds_raw = st.secrets["gcp_json"]
        creds_dict = json.loads(creds_raw) if isinstance(creds_raw, str) else dict(creds_raw)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🚨 Configuración de credenciales inválida: {e}")
        st.stop()

@st.cache_data(ttl=120)
def leer_datos(_client, nombre_archivo, nombre_pestana=None):
    try:
        doc = _client.open(nombre_archivo)
        ws = doc.worksheet(nombre_pestana) if nombre_pestana else doc.sheet1
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.str.strip()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def leer_todos_los_registros(_client):
    try:
        doc = _client.open(FILE_REGISTROS)
        hojas = [pd.DataFrame(h.get_all_records()) for h in doc.worksheets() if h.get_all_records()]
        if not hojas: 
            return pd.DataFrame()
        df = pd.concat(hojas, ignore_index=True)
        if not df.empty:
            df.columns = df.columns.str.strip()
            if 'Grupo' in df.columns:
                df['Grado'] = df['Grupo'].astype(str).str.extract(r'(\d+)')[0].fillna('N/A')
        return df
    except Exception:
        return pd.DataFrame()

def format_calif(val):
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def obtener_lista_alumnos(gc, archivo, pestana):
    try:
        df = leer_datos(gc, archivo, pestana.strip())
        if df.empty: 
            return []
        
        if 'Nombre Completo' in df.columns:
            nombres = df['Nombre Completo'].fillna('').astype(str)
        elif 'Nombre' in df.columns:
            nombres = df['Nombre'].fillna('').astype(str)
        else:
            paterno = df.iloc[:, 1].fillna('').astype(str)
            materno = df.iloc[:, 2].fillna('').astype(str)
            nombres_pila = df.iloc[:, 3].fillna('').astype(str)
            nombres = paterno + " " + materno + " " + nombres_pila
            
        nombres = nombres.str.replace(r'\s+', ' ', regex=True).str.strip()
        nombres = nombres[nombres != '']
        return sorted(nombres.unique().tolist())
    except Exception:
        return []

def obtener_dataframe_alumnos(gc, archivo, pestana):
    try:
        df = leer_datos(gc, archivo, pestana.strip())
        if df.empty: 
            return None
        
        df.columns = df.columns.str.strip()
        
        if 'Nombre Completo' not in df.columns:
            if 'Nombre' in df.columns:
                df['Nombre Completo'] = df['Nombre'].fillna('').astype(str)
            else:
                paterno = df.iloc[:, 1].fillna('').astype(str)
                materno = df.iloc[:, 2].fillna('').astype(str)
                nombres_pila = df.iloc[:, 3].fillna('').astype(str)
                df['Nombre Completo'] = (paterno + " " + materno + " " + nombres_pila).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        return df
    except Exception:
        return None

@st.cache_data(ttl=300)
def leer_todas_las_asignaciones(_gc, nombre_archivo):
    try:
        doc = _gc.open(nombre_archivo)
        lista_dfs = []
        for hoja in doc.worksheets():
            datos = hoja.get_all_values()
            if len(datos) > 1:
                df = pd.DataFrame(datos[1:], columns=datos[0])
                df.columns = df.columns.str.strip()
                df['Nivel'] = hoja.title.strip()
                lista_dfs.append(df)
        
        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer asignaciones: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def obtener_info_alumno_por_correo(_gc, archivo_alumnos, correo_buscar):
    """Busca en todas las pestañas de alumnos y retorna un diccionario con su información."""
    correo_limpio = str(correo_buscar).lower().strip()
    try:
        doc = _gc.open(archivo_alumnos)
        for hoja in doc.worksheets():
            datos = hoja.get_all_records()
            if not datos:
                continue
            df = pd.DataFrame(datos)
            df.columns = df.columns.str.strip()
            
            if 'Correo' in df.columns:
                df['Correo_Normalizado'] = df['Correo'].astype(str).str.strip().str.lower()
                coincidencia = df[df['Correo_Normalizado'] == correo_limpio]
                
                if not coincidencia.empty:
                    fila = coincidencia.iloc[0]
                    if 'Nombre Completo' in coincidencia.columns and pd.notna(fila['Nombre Completo']) and fila['Nombre Completo'] != "":
                        nombre_completo = str(fila['Nombre Completo']).strip()
                    else:
                        p = str(fila.iloc[1]).strip()
                        m = str(fila.iloc[2]).strip()
                        n = str(fila.iloc[3]).strip()
                        nombre_completo = f"{p} {m} {n}".strip().replace("  ", " ")
                        
                    return {
                        "Nombre": nombre_completo,
                        "Grupo": hoja.title.strip(),
                        "ID": str(fila.get("ID", "")),
                        "Correo_Padres": str(fila.get("Correo_Tutor_Legal", "")).strip()
                    }
        return None
    except Exception:
        return None

def obtener_resumen_asistencia_alumno(gc, nombre_alumno, grupo_alumno):
    """Calcula las inasistencias y derecho a examen del alumno en cada materia activa."""
    try:
        doc = gc.open(FILE_ASISTENCIA)
        hojas = doc.worksheets()
        
        try:
            ws_conf = doc.worksheet("Configuracion")
            df_conf = pd.DataFrame(ws_conf.get_all_records())
            df_conf.columns = df_conf.columns.str.strip()
        except Exception:
            df_conf = pd.DataFrame()

        resultados = []
        sufijo_grupo = f"- {grupo_alumno.strip()}"
        limite_faltas_dict = {0: 99, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9}

        for h in hojas:
            if h.title.endswith(sufijo_grupo):
                materia_nombre = h.title.replace(sufijo_grupo, "").strip()
                data = h.get_all_records()
                if not data:
                    continue
                df_m = pd.DataFrame(data)
                df_m.columns = df_m.columns.str.strip()
                
                if 'Alumno' not in df_m.columns:
                    continue
                    
                df_m['Alumno_Norm'] = df_m['Alumno'].astype(str).str.strip().str.lower()
                fila = df_m[df_m['Alumno_Norm'] == nombre_alumno.lower().strip()]
                
                if fila.empty:
                    continue
                
                conf_materia = df_conf[df_conf['Clase'] == h.title] if not df_conf.empty and 'Clase' in df_conf.columns else pd.DataFrame()
                dias_semana_clase = 0
                if not conf_materia.empty:
                    dias_semana_clase = sum(1 for c in ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes'] if int(conf_materia.iloc[0].get(c, 0)) > 0)
                
                limite = limite_faltas_dict.get(dias_semana_clase, 7)
                
                cols_fechas = [c for c in df_m.columns if c not in ['Alumno', 'Alumno_Norm']]
                faltas_reales = 0
                retardos = 0
                
                fila_val = fila.iloc[0]
                for c in cols_fechas:
                    val = str(fila_val[c])
                    if "Falta" in val:
                        faltas_reales += 1
                    elif "Retardo" in val:
                        retardos += 1
                        
                faltas_efectivas = faltas_reales + (retardos // 3)
                derecho = "✅ SÍ" if faltas_efectivas <= limite else "❌ NO"
                
                resultados.append({
                    "Materia": materia_nombre,
                    "Frecuencia Semanal": f"{dias_semana_clase} días" if dias_semana_clase > 0 else "N/D",
                    "Faltas Reales": faltas_reales,
                    "Retardos": retardos,
                    "Faltas Efectivas": faltas_efectivas,
                    "Límite Permitido": limite,
                    "Derecho Examen": derecho
                })
                
        return pd.DataFrame(resultados)
    except Exception:
        return pd.DataFrame()