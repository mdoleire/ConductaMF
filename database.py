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
        creds_dict = json.loads(st.secrets["gcp_json"])
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

@st.cache_data(ttl=300)
def leer_todos_los_registros(_client):
    """
    ⚡ ULTRA-OPTIMIZADO: Lee todas las pestañas del colegio en 1 SOLA PETICIÓN MASIVA (Batch Get),
    reduciendo el tiempo de carga de 2 minutos a menos de 2 segundos.
    """
    try:
        doc = _client.open(FILE_REGISTROS)
        hojas = doc.worksheets()
        if not hojas: 
            return pd.DataFrame()
            
        # 1. Preparamos los rangos de todas las pestañas del documento
        rangos_todas_hojas = [f"'{h.title}'!A:J" for h in hojas]
        
        # 2. Hacemos UNA ÚNICA petición masiva a la API de Google
        batch_resultado = doc.values_batch_get(rangos_todas_hojas)
        
        hojas_dfs = []
        # 3. Procesamos los datos en la memoria RAM ultra-rápida de Python
        for val_range in batch_resultado.get('valueRanges', []):
            filas = val_range.get('values', [])
            if len(filas) > 1:
                # La primera fila son los encabezados
                headers = [str(c).strip() for c in filas[0]]
                df_temp = pd.DataFrame(filas[1:], columns=headers)
                hojas_dfs.append(df_temp)
                
        if not hojas_dfs: 
            return pd.DataFrame()
            
        # Unificamos todo en un único DataFrame instantáneo
        df = pd.concat(hojas_dfs, ignore_index=True)
        if not df.empty:
            df.columns = df.columns.str.strip()
            if 'Grupo' in df.columns:
                df['Grado'] = df['Grupo'].astype(str).str.extract(r'(\d+)')[0].fillna('N/A')
        return df
        
    except Exception as e:
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

@st.cache_data(ttl=600)  # Caché de 10 minutos para la plantilla docente
def leer_todas_las_asignaciones(_gc, nombre_archivo):
    try:
        doc = _gc.open(nombre_archivo)
        lista_dfs = []
        for hoja in doc.worksheets():
            time.sleep(0.05)
            datos = hoja.get_all_values()
            if len(datos) > 1:
                df = pd.DataFrame(datos[1:], columns=[str(c).strip() for c in datos[0]])
                df.columns = df.columns.str.strip()
                df['Nivel'] = hoja.title.strip()
                lista_dfs.append(df)
        
        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def obtener_info_alumno_por_correo(_gc, archivo_alumnos, correo_buscar):
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

# 🛡️ MEJORA CRÍTICA DE CUOTA DE API: Cacheado estricto por alumno
@st.cache_data(ttl=180)
def obtener_resumen_asistencia_alumno(_gc, nombre_alumno, grupo_alumno):
    """Calcula las inasistencias de un alumno de forma optimizada utilizando caché de corta duración."""
    try:
        doc = _gc.open(FILE_ASISTENCIA)
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

# 🛡️ NUEVO: Cacheado para compilación de tutorías masivas
@st.cache_data(ttl=180)
def compilar_asistencias_grupo_tutor(_gc, grupo_sel):
    """Agrupa de manera ultra rápida las inasistencias históricas de un salón entero en un dataframe único."""
    try:
        doc_asist = _gc.open(FILE_ASISTENCIA)
        hojas = doc_asist.worksheets()
        sufijo_grupo = f" - {grupo_sel.strip()}"
        hojas_grupo = [h for h in hojas if h.title.strip().endswith(sufijo_grupo)]
        
        list_melted = []
        for h in hojas_grupo:
            try:
                datos = h.get_all_values()
                if len(datos) > 1:
                    cols = [c.strip() for c in datos[0]]
                    df_temp = pd.DataFrame(datos[1:], columns=cols)
                    materia = h.title.replace(sufijo_grupo, "").strip()
                    
                    fechas_cols = [c for c in cols if c != 'Alumno']
                    if fechas_cols:
                        df_melt = df_temp.melt(id_vars=['Alumno'], value_vars=fechas_cols, var_name='Fecha', value_name='Falta')
                        df_melt['Materia'] = materia
                        df_melt['Categoría'] = 'Asistencia'
                        df_melt['Profesor'] = 'Control de Asistencia'
                        df_melt['Puntos_Descontados'] = 0
                        df_melt['Observaciones'] = ''
                        list_melted.append(df_melt)
            except Exception:
                continue
        
        if list_melted:
            df_asist_plana = pd.concat(list_melted, ignore_index=True)
            df_asist_plana = df_asist_plana[df_asist_plana['Falta'].isin(['🔴 Falta', '🟡 Retardo'])]
            if not df_asist_plana.empty:
                df_asist_plana['Fecha_DT'] = pd.to_datetime(df_asist_plana['Fecha'], format='%d-%m-%Y', errors='coerce')
                df_asist_plana['Fecha'] = df_asist_plana['Fecha_DT'].dt.strftime("%Y-%m-%d %H:%M:%S")
                return df_asist_plana
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()