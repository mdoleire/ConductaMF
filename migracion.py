# migracion.py
import sqlite3
import pandas as pd
import gspread
import time
import json
import streamlit as st
from google.oauth2.service_account import Credentials

from config import (
    FILE_SEGURIDAD, 
    FILE_ALUMNOS, 
    FILE_ASIGNACIONES, 
    FILE_REGISTROS, 
    FILE_ASISTENCIA, 
    FILE_CALIFICACIONES
)

# 🌐 CONEXIÓN DIRECTA Y REAL A GOOGLE SHEETS (SIN DEPENDER DE DATABASE.PY)
def conectar_google_sheets_real():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gcp_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def ejecutar_con_reintento(accion_lambda, descripcion=""):
    """Pausa preventiva de 1.2s y auto-recuperación si Google activa el límite 429"""
    time.sleep(1.2)
    max_intentos = 4
    tiempo_espera = 15
    
    for intento in range(max_intentos):
        try:
            return accion_lambda()
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "Quota exceeded" in error_msg:
                print(f"      ⏳ Cuota alcanzada en {descripcion}. Pausando {tiempo_espera}s...")
                time.sleep(tiempo_espera)
                tiempo_espera += 10
            else:
                raise e
    return None

def migrar_a_sql():
    print("=" * 60)
    print("🚀 INICIANDO MIGRACIÓN REAL A SQL (DESDE GOOGLE DRIVE OFICIAL)")
    print("=" * 60)
    
    gc = conectar_google_sheets_real()
    conexion_sql = sqlite3.connect('miraflores.db')
    print("✅ Conectado a Google Sheets y a 'miraflores.db' local.\n")

    # ==========================================
    # 1. Migrar Seguridad / Usuarios
    # ==========================================
    try:
        print(f"1️⃣ Descargando {FILE_SEGURIDAD}...")
        ws_seg = gc.open(FILE_SEGURIDAD).sheet1
        datos_seg = ejecutar_con_reintento(lambda: ws_seg.get_all_records(), "Seguridad")
        df_seguridad = pd.DataFrame(datos_seg)
        if not df_seguridad.empty:
            df_seguridad.columns = df_seguridad.columns.str.strip()
            df_seguridad.to_sql('usuarios', conexion_sql, if_exists='replace', index=False)
            print(f"   ✅ Tabla 'usuarios' creada ({len(df_seguridad)} usuarios).")
    except Exception as e:
        print(f"   ❌ Error en Seguridad: {e}")

    # ==========================================
    # 2. Migrar Asignaciones
    # ==========================================
    try:
        print(f"2️⃣ Descargando {FILE_ASIGNACIONES}...")
        doc_asig = gc.open(FILE_ASIGNACIONES)
        lista_asig = []
        for hoja in doc_asig.worksheets():
            datos = ejecutar_con_reintento(lambda: hoja.get_all_values(), f"Asignaciones {hoja.title}")
            if datos and len(datos) > 1:
                df_temp = pd.DataFrame(datos[1:], columns=[str(c).strip() for c in datos[0]])
                df_temp['Nivel'] = hoja.title.strip()
                lista_asig.append(df_temp)
                
        if lista_asig:
            df_asig_total = pd.concat(lista_asig, ignore_index=True)
            df_asig_total.to_sql('asignaciones', conexion_sql, if_exists='replace', index=False)
            print(f"   ✅ Tabla 'asignaciones' creada ({len(df_asig_total)} clases/niveles).")
    except Exception as e:
        print(f"   ❌ Error en Asignaciones: {e}")

    # ==========================================
    # 3. Migrar Registros de Conducta
    # ==========================================
    try:
        print(f"3️⃣ Descargando {FILE_REGISTROS}...")
        doc_registros = gc.open(FILE_REGISTROS)
        hojas_conducta = doc_registros.worksheets()
        
        df_conducta_total = pd.DataFrame()
        for hoja in hojas_conducta:
            datos = ejecutar_con_reintento(lambda: hoja.get_all_records(), f"Conducta {hoja.title}")
            if datos:
                df_temp = pd.DataFrame(datos)
                df_temp.columns = df_temp.columns.str.strip()
                df_temp['Origen_Pestana'] = hoja.title.strip()
                df_conducta_total = pd.concat([df_conducta_total, df_temp], ignore_index=True)
                
        if not df_conducta_total.empty:
            df_conducta_total.to_sql('conducta_registros', conexion_sql, if_exists='replace', index=False)
            print(f"   ✅ Tabla 'conducta_registros' creada ({len(df_conducta_total)} incidentes históricos).")
    except Exception as e:
        print(f"   ❌ Error en Registros de Conducta: {e}")

    # ==========================================
    # 4. Migrar Alumnos
    # ==========================================
    try:
        print(f"4️⃣ Descargando {FILE_ALUMNOS}...")
        doc_alumnos = gc.open(FILE_ALUMNOS)
        hojas_alumnos = doc_alumnos.worksheets()
        
        df_alumnos_total = pd.DataFrame()
        for hoja in hojas_alumnos:
            try:
                valores = ejecutar_con_reintento(lambda: hoja.get_all_values(), f"Alumnos {hoja.title}")
                if valores and len(valores) > 1:
                    encabezados_limpios = []
                    for i, col in enumerate(valores[0]):
                        nombre = str(col).strip()
                        if not nombre:
                            nombre = f"Columna_{i}"
                        while nombre in encabezados_limpios:
                            nombre = f"{nombre}_{i}"
                        encabezados_limpios.append(nombre)

                    df_temp = pd.DataFrame(valores[1:], columns=encabezados_limpios)
                    df_temp['Grupo_Base'] = hoja.title.strip()
                    df_alumnos_total = pd.concat([df_alumnos_total, df_temp], ignore_index=True)
            except Exception as e_hoja:
                print(f"   ⚠️ Pestaña omitida '{hoja.title}': {e_hoja}")
                
        if not df_alumnos_total.empty:
            df_alumnos_total.to_sql('alumnos', conexion_sql, if_exists='replace', index=False)
            print(f"   ✅ Tabla 'alumnos' creada ({len(df_alumnos_total)} estudiantes).")
    except Exception as e:
        print(f"   ❌ Error en Alumnos: {e}")

    # ==========================================
    # 5. Migrar Asistencia (CON BLINDAJE ANTI-COLISIÓN DE ESTATUS)
    # ==========================================
    try:
        print(f"5️⃣ Descargando {FILE_ASISTENCIA}...")
        doc_asist = gc.open(FILE_ASISTENCIA)
        hojas_asist = doc_asist.worksheets()
        
        # 5.1 Configuración de horarios
        try:
            ws_conf = doc_asist.worksheet("Configuracion")
            datos_conf = ejecutar_con_reintento(lambda: ws_conf.get_all_records(), "Conf Horarios")
            df_conf = pd.DataFrame(datos_conf)
            if not df_conf.empty:
                df_conf.columns = df_conf.columns.str.strip()
                df_conf.to_sql('asistencia_config', conexion_sql, if_exists='replace', index=False)
                print("   ✅ Tabla 'asistencia_config' creada en SQL.")
        except Exception:
            print("   ⚠️ Pestaña 'Configuracion' no encontrada o vacía.")

        # 5.2 Registros de asistencia
        df_asistencia_total = pd.DataFrame()
        for hoja in hojas_asist:
            if hoja.title.strip() == "Configuracion":
                continue
            
            try:
                valores = ejecutar_con_reintento(lambda: hoja.get_all_values(), f"Asistencia {hoja.title}")
                if valores and len(valores) > 1:
                    encabezados = [str(c).strip() for c in valores[0]]
                    df_temp = pd.DataFrame(valores[1:], columns=encabezados)
                    
                    if 'Alumno' in df_temp.columns:
                        # 🛡️ FIX COLISIÓN: Extraemos únicamente columnas que no sean 'Alumno' ni 'Estatus'
                        cols_fechas = [c for c in df_temp.columns if str(c).strip().lower() not in ['alumno', 'estatus']]
                        
                        # Si ya existía una columna llamada 'Estatus', la eliminamos del DataFrame original
                        cols_a_conservar = ['Alumno'] + cols_fechas
                        df_limpio = df_temp[cols_a_conservar]
                        
                        df_melted = df_limpio.melt(
                            id_vars=['Alumno'], 
                            value_vars=cols_fechas, 
                            var_name='Fecha', 
                            value_name='Estatus'
                        )
                        df_melted['Clase'] = hoja.title.strip()
                        df_asistencia_total = pd.concat([df_asistencia_total, df_melted], ignore_index=True)
            except Exception as e_hoja:
                print(f"   ⚠️ Error en asistencia de {hoja.title}: {e_hoja}")
                
        if not df_asistencia_total.empty:
            df_asistencia_total = df_asistencia_total[df_asistencia_total['Estatus'] != ""]
            df_asistencia_total = df_asistencia_total[['Clase', 'Alumno', 'Fecha', 'Estatus']]
            df_asistencia_total.to_sql('asistencia_registros', conexion_sql, if_exists='replace', index=False)
            print(f"   ✅ Tabla 'asistencia_registros' creada con {len(df_asistencia_total)} asistencias.")
    except Exception as e:
        print(f"   ❌ Error en Asistencia: {e}")

    # ==========================================
    # 6. Migrar Calificaciones
    # ==========================================
    try:
        print(f"6️⃣ Descargando {FILE_CALIFICACIONES}...")
        doc_calif = gc.open(FILE_CALIFICACIONES)
        
        # 6.1 Ponderaciones
        try:
            ws_pond = doc_calif.worksheet("Ponderaciones")
            vals_pond = ejecutar_con_reintento(lambda: ws_pond.get_all_values(), "Ponderaciones")
            if vals_pond and len(vals_pond) > 1:
                df_p = pd.DataFrame(vals_pond[1:], columns=[str(c).strip() for c in vals_pond[0]])
                df_p.to_sql('calif_ponderaciones', conexion_sql, if_exists='replace', index=False)
                print(f"   ✅ Tabla 'calif_ponderaciones' creada ({len(df_p)} reglas).")
        except Exception as e:
            print(f"   ⚠️ Error en Ponderaciones: {e}")
            
        # 6.2 Actividades
        try:
            ws_act = doc_calif.worksheet("Actividades")
            vals_act = ejecutar_con_reintento(lambda: ws_act.get_all_values(), "Actividades")
            if vals_act and len(vals_act) > 1:
                df_act = pd.DataFrame(vals_act[1:], columns=[str(c).strip() for c in vals_act[0]])
                df_act.to_sql('calif_actividades', conexion_sql, if_exists='replace', index=False)
                print(f"   ✅ Tabla 'calif_actividades' creada ({len(df_act)} actividades).")
        except Exception as e:
            print(f"   ⚠️ Error en Actividades: {e}")
            
        # 6.3 Notas
        try:
            ws_notas = doc_calif.worksheet("Calificaciones")
            vals_notas = ejecutar_con_reintento(lambda: ws_notas.get_all_values(), "Calificaciones")
            if vals_notas and len(vals_notas) > 1:
                df_n = pd.DataFrame(vals_notas[1:], columns=[str(c).strip() for c in vals_notas[0]])
                df_n.to_sql('calif_notas', conexion_sql, if_exists='replace', index=False)
                print(f"   ✅ Tabla 'calif_notas' creada ({len(df_n)} notas capturadas).")
        except Exception as e:
            print(f"   ⚠️ Error en Calificaciones: {e}")
            
    except Exception as e:
        print(f"   ❌ Error en Calificaciones: {e}")

    conexion_sql.close()
    print("\n" + "=" * 60)
    print("🎉 MIGRACIÓN COMPLETA: Toda la escuela vive ahora en 'miraflores.db'")
    print("=" * 60)

if __name__ == "__main__":
    migrar_a_sql()