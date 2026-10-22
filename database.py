# database.py
import pandas as pd
import streamlit as st
import time
import html
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SeguridadMF")

# =================================================================
# 1. CONEXIÓN CENTRAL A SUPABASE (COMPATIBLE CON POOLER)
# =================================================================
@st.cache_resource
def obtener_engine_sql():
    url_db = (
        st.secrets.get("DATABASE_URL") or 
        st.secrets.get("database_url") or 
        st.secrets.get("URL_SUPABASE") or 
        st.secrets.get("SUPABASE_URL")
    )
    
    if not url_db:
        st.error("🚨 ERROR: No se encontró la configuración de conexión en los secretos.")
        st.stop()
        
    if url_db.startswith("postgres://"):
        url_db = url_db.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url_db.startswith("postgresql://") and not url_db.startswith("postgresql+psycopg2://"):
        url_db = url_db.replace("postgresql://", "postgresql+psycopg2://", 1)
        
    return create_engine(
        url_db, 
        poolclass=NullPool,
        connect_args={"sslmode": "require"}
    )

TABLAS_PERMITIDAS = {
    "usuarios", "asignaciones", "alumnos", "conducta_registros",
    "asistencia_registros", "asistencia_config", "calif_ponderaciones",
    "calif_actividades", "calif_notas"
}

def resolver_nombre_tabla(nombre_archivo, nombre_pestana=None):
    # 🛡️ Primero se decide por ARCHIVO y solo después por pestaña, dentro de ese archivo.
    # Antes una clase cuyo nombre contuviera "actividad", "nota" o "config" se enviaba
    # a una tabla de calificaciones/configuración, y un nombre desconocido caía en
    # conducta_registros en silencio.
    f_str = str(nombre_archivo).lower()
    p_str = str(nombre_pestana).strip().lower() if nombre_pestana else ""

    if "asistencia" in f_str:
        return "asistencia_config" if p_str in ("configuracion", "configuración") else "asistencia_registros"
    if "calificaci" in f_str:
        if "ponderaci" in p_str: return "calif_ponderaciones"
        if "actividad" in p_str: return "calif_actividades"
        return "calif_notas"
    if "conducta" in f_str or "incidencia" in f_str or "registro" in f_str: return "conducta_registros"
    if "seguridad" in f_str or "usuario" in f_str: return "usuarios"
    if "asignaci" in f_str or "profesor" in f_str: return "asignaciones"
    if "alumno" in f_str: return "alumnos"

    candidato = str(nombre_archivo).strip()
    if candidato in TABLAS_PERMITIDAS:
        return candidato
    raise ValueError(f"Tabla no reconocida: {nombre_archivo!r} / {nombre_pestana!r}")

# =================================================================
# 2. PUENTE DE COMPATIBILIDAD ASISTENCIA (SQLITE ➔ SUPABASE)
# =================================================================
class PostgreSqlCursorWrapper:
    def __init__(self, raw_cursor):
        self.cursor = raw_cursor

    def execute(self, sql, params=None):
        sql_pg = sql.replace("[", '"').replace("]", '"').replace("?", "%s")
        if params:
            return self.cursor.execute(sql_pg, params)
        return self.cursor.execute(sql_pg)

    def executemany(self, sql, seq_of_params):
        sql_pg = sql.replace("[", '"').replace("]", '"').replace("?", "%s")
        return self.cursor.executemany(sql_pg, seq_of_params)

class PostgreSqlConnectionWrapper:
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn

    def cursor(self):
        return PostgreSqlCursorWrapper(self.raw_conn.cursor())

    def commit(self):
        return self.raw_conn.commit()

    def rollback(self):
        # 🛡️ asistencia.py llama conn.rollback() en sus except; antes no existía y tronaba
        return self.raw_conn.rollback()

    def close(self):
        return self.raw_conn.close()

def obtener_conexion_sql():
    engine = obtener_engine_sql()
    raw_conn = engine.raw_connection()
    return PostgreSqlConnectionWrapper(raw_conn)

# =================================================================
# 3. EMULADOR COMPATIBLE CON CONTROL DE ACCESO (ANTI-IDOR Y NO REPLACE)
# =================================================================
class MockWorksheet:
    def __init__(self, table_name, engine, sheet_title=None):
        self.table_name = table_name if table_name in TABLAS_PERMITIDAS else "conducta_registros"
        self.engine = engine
        self.title = str(sheet_title or table_name).strip()
        
    def col_values(self, col_idx):
        try:
            df = pd.read_sql(f'SELECT * FROM "{self.table_name}"', self.engine)
            if df.empty or col_idx > len(df.columns):
                return []
            return df.iloc[:, col_idx - 1].astype(str).tolist()
        except Exception as e:
            logger.error(f"Error en col_values: {e}")
            return []
            
    def append_rows(self, rows):        
        try:
            df_actual = pd.read_sql(f'SELECT * FROM "{self.table_name}" LIMIT 1', self.engine)
            cols = [c for c in df_actual.columns if not c.endswith('_id')]
            
            filas_ajustadas = []
            for r in rows:
                if 'Origen_Pestana' in cols and len(r) == len(cols) - 1:
                    filas_ajustadas.append(r + [self.title])
                else:
                    filas_ajustadas.append(r)
                    
            df_nuevos = pd.DataFrame(filas_ajustadas, columns=cols[:len(filas_ajustadas[0])])
            df_nuevos.to_sql(self.table_name, self.engine, if_exists='append', index=False)
            return True
        except Exception as e:
            # 🛡️ Antes regresaba False y quien llamaba mostraba "guardado" de todos modos
            logger.error(f"Error en append_rows: {e}")
            raise

    def append_row(self, row):
        return self.append_rows([row])

    def get_all_values(self):
        try:
            query = text(f'SELECT * FROM "{self.table_name}"')
            df = pd.read_sql(query, self.engine)
            if df.empty:
                return []
            df.columns = df.columns.str.strip()
            
            if self.table_name == "conducta_registros":
                if "pasillo" in self.title.lower():
                    df = df[
                        df['Materia'].astype(str).str.lower().str.contains("pasillo") | 
                        df.get('Origen_Pestana', pd.Series()).astype(str).str.lower().str.contains("pasillo")
                    ]
                elif " - " in self.title:
                    materia_b, grupo_b = self.title.split(" - ", 1)
                    df = df[
                        (df['Materia'].astype(str).str.lower().str.strip() == materia_b.lower().strip()) & 
                        (df['Grupo'].astype(str).str.lower().str.strip() == grupo_b.lower().strip())
                    ]
                    
            if df.empty:
                return []
            return [df.columns.tolist()] + df.astype(str).values.tolist()
        except Exception as e:
            logger.error(f"Error en get_all_values: {e}")
            return []

    def update_cell_seguro(self, row_idx, val, profesor_solicitante, es_admin=False):
        if not es_admin and not str(profesor_solicitante).strip():
            logger.warning("Intento de update_cell_seguro sin identificar profesor solicitante.")
            return False
        try:
            vals = self.get_all_values()
            if len(vals) >= row_idx:
                fila = vals[row_idx - 1]
                headers = vals[0]
                
                with self.engine.begin() as conn:
                    if "incidencia_id" in headers:
                        idx_pk = headers.index("incidencia_id")
                        pk_val = int(fila[idx_pk])
                        if es_admin:
                            query = text('UPDATE "conducta_registros" SET "Observaciones" = :val WHERE "incidencia_id" = :pk')
                            conn.execute(query, {"val": str(val), "pk": pk_val})
                        else:
                            query = text('UPDATE "conducta_registros" SET "Observaciones" = :val WHERE "incidencia_id" = :pk AND LOWER(TRIM("Profesor")) = LOWER(TRIM(:prof))')
                            conn.execute(query, {"val": str(val), "pk": pk_val, "prof": profesor_solicitante})
                    else:
                        fecha_target, alumno_target = fila[0], fila[4]
                        if es_admin:
                            query = text('UPDATE "conducta_registros" SET "Observaciones" = :val WHERE "Fecha" = :fec AND "Alumno" = :alm')
                            conn.execute(query, {"val": str(val), "fec": str(fecha_target), "alm": str(alumno_target)})
                        else:
                            query = text('UPDATE "conducta_registros" SET "Observaciones" = :val WHERE "Fecha" = :fec AND "Alumno" = :alm AND LOWER(TRIM("Profesor")) = LOWER(TRIM(:prof))')
                            conn.execute(query, {"val": str(val), "fec": str(fecha_target), "alm": str(alumno_target), "prof": profesor_solicitante})
                return True
            return False
        except Exception as e:
            logger.error(f"Violación o error en update_cell_seguro: {e}")
            return False

    def delete_rows_seguro(self, row_idx, profesor_solicitante, es_admin=False):
        if not es_admin and not str(profesor_solicitante).strip():
            logger.warning("Intento de delete_rows_seguro sin identificar profesor solicitante.")
            return False
        try:
            vals = self.get_all_values()
            if len(vals) >= row_idx:
                fila = vals[row_idx - 1]
                headers = vals[0]
                
                with self.engine.begin() as conn:
                    if "incidencia_id" in headers:
                        idx_pk = headers.index("incidencia_id")
                        pk_val = int(fila[idx_pk])
                        if es_admin:
                            query = text('DELETE FROM "conducta_registros" WHERE "incidencia_id" = :pk')
                            conn.execute(query, {"pk": pk_val})
                        else:
                            query = text('DELETE FROM "conducta_registros" WHERE "incidencia_id" = :pk AND LOWER(TRIM("Profesor")) = LOWER(TRIM(:prof))')
                            conn.execute(query, {"pk": pk_val, "prof": profesor_solicitante})
                    else:
                        fecha_target, alumno_target = fila[0], fila[4]
                        if es_admin:
                            query = text('DELETE FROM "conducta_registros" WHERE "Fecha" = :fec AND "Alumno" = :alm')
                            conn.execute(query, {"fec": str(fecha_target), "alm": str(alumno_target)})
                        else:
                            query = text('DELETE FROM "conducta_registros" WHERE "Fecha" = :fec AND "Alumno" = :alm AND LOWER(TRIM("Profesor")) = LOWER(TRIM(:prof))')
                            conn.execute(query, {"fec": str(fecha_target), "alm": str(alumno_target), "prof": profesor_solicitante})
                return True
            return False
        except Exception as e:
            logger.error(f"Violación o error en delete_rows_seguro: {e}")
            return False

    # 🛡️ BLOQUEO DE MÉTODOS HEREDADOS INSEGUROS (Previene escalada de privilegios)
    def update_cell(self, row_idx, col_idx, val):
        logger.warning("Llamada insegura a update_cell bloqueada por política anti-IDOR.")
        return False

    def delete_rows(self, row_idx):
        logger.warning("Llamada insegura a delete_rows bloqueada por política anti-IDOR.")
        return False

    # 🛡️ PROTECCIÓN ESTRICTA CONTRA BORRADO MASIVO DE TABLAS CRÍTICAS
    def update(self, range_name=None, values=None, **kwargs):
        matriz = values if values is not None else range_name
        if not matriz or len(matriz) < 2:
            return True
            
        headers = [str(c).strip() for c in matriz[0]]
        filas = matriz[1:]
        df_matriz = pd.DataFrame(filas, columns=headers)
        
        with self.engine.begin() as conn:
            if "asistencia" in self.table_name.lower() and self.table_name != "asistencia_config":
                if 'Alumno' in df_matriz.columns:
                    clase_actual = self.title
                    cols_fechas = [c for c in df_matriz.columns if c != 'Alumno']
                    df_melt = df_matriz.melt(id_vars=['Alumno'], value_vars=cols_fechas, var_name='Fecha', value_name='Estatus')
                    df_melt['Clase'] = clase_actual
                    df_melt = df_melt[df_melt['Estatus'] != ""]
                    
                    conn.execute(text('DELETE FROM "asistencia_registros" WHERE "Clase" = :clase'), {"clase": clase_actual})
                    df_melt[['Clase', 'Alumno', 'Fecha', 'Estatus']].to_sql('asistencia_registros', conn, if_exists='append', index=False)
                    return True
            else:
                tablas_reemplazables = {"asistencia_config", "calif_ponderaciones", "calif_actividades"}
                if self.table_name not in tablas_reemplazables:
                    logger.error(f"Intento bloqueado de sobrescribir tabla crítica completa: {self.table_name}")
                    return False
                conn.execute(text(f'DELETE FROM "{self.table_name}"'))
                df_matriz.to_sql(self.table_name, conn, if_exists='append', index=False)
                return True

    def clear(self):
        return True

class MockSpreadsheet:
    def __init__(self, title, engine):
        self.title = title
        self.engine = engine
        tabla_principal = resolver_nombre_tabla(title)
        self.sheet1 = MockWorksheet(tabla_principal, engine, sheet_title="sheet1")
        
    def worksheet(self, title):
        tabla_real = resolver_nombre_tabla(self.title, title)
        return MockWorksheet(tabla_real, self.engine, sheet_title=title)

    def worksheets(self):
        try:
            tabla_real = resolver_nombre_tabla(self.title)
            if tabla_real == "conducta_registros":
                df = pd.read_sql('SELECT DISTINCT "Materia", "Grupo" FROM "conducta_registros"', self.engine)
                hojas = [MockWorksheet("conducta_registros", self.engine, sheet_title="Reportes_Pasillo")]
                for _, r in df.iterrows():
                    if pd.notna(r['Materia']) and pd.notna(r['Grupo']):
                        m = str(r['Materia']).strip()
                        g = str(r['Grupo']).strip()
                        if "pasillo" not in m.lower():
                            hojas.append(MockWorksheet("conducta_registros", self.engine, sheet_title=f"{m} - {g}"))
                return hojas
            elif tabla_real == "asistencia_registros":
                df = pd.read_sql('SELECT DISTINCT "Clase" FROM "asistencia_registros"', self.engine)
                return [MockWorksheet("asistencia_registros", self.engine, sheet_title=str(c).strip()) for c in df['Clase'].dropna().unique()]
            else:
                return [self.sheet1]
        except Exception:
            return [self.sheet1]

class MockGSpreadClient:
    def __init__(self, engine):
        self.engine = engine
        
    def open(self, title):
        return MockSpreadsheet(title, self.engine)

def conectar_gsheets():
    engine = obtener_engine_sql()
    return MockGSpreadClient(engine)

# =================================================================
# 4. CONSULTAS DE LECTURA INSTANTÁNEA EN SUPABASE (POSTGRESQL)
# =================================================================
@st.cache_data(ttl=60)
def leer_datos(_client_or_conn, nombre_tabla, nombre_pestana=None):
    engine = obtener_engine_sql()
    tabla_real = resolver_nombre_tabla(nombre_tabla, nombre_pestana)
    try:
        if tabla_real == "asistencia_registros" and nombre_pestana and nombre_pestana != "Configuracion":
            clase_buscada = str(nombre_pestana).strip().lower()
            query = text('SELECT "Alumno", "Fecha", "Estatus" FROM "asistencia_registros" WHERE LOWER(TRIM("Clase")) = :clase')
            df_long = pd.read_sql(query, engine, params={"clase": clase_buscada})
            
            if df_long.empty: return pd.DataFrame()
            # 🛡️ pivot() truena si un alumno tiene dos registros en la misma fecha, y el error
            # dejaba la clase sin historial (todos con 0 faltas). pivot_table tolera duplicados.
            if df_long.duplicated(subset=['Alumno', 'Fecha']).any():
                logger.warning(f"Asistencia duplicada en la clase '{nombre_pestana}'")
            df_pivot = df_long.pivot_table(index='Alumno', columns='Fecha', values='Estatus', aggfunc='last').reset_index()
            df_pivot.columns.name = None
            return df_pivot.fillna("")

        df = pd.read_sql(f'SELECT * FROM "{tabla_real}"', engine)
        df.columns = df.columns.str.strip()
        
        if tabla_real == "usuarios":
            renombres = {c: "Usuario" for c in df.columns if c.lower() in ["usuario", "email", "correo"]}
            if renombres:
                df = df.rename(columns=renombres)
                    
        return df.copy()
    except Exception as e:
        logger.error(f"Error interno leyendo '{tabla_real}' en Supabase: {e}")
        st.error("🚨 No se pudo cargar la información en este momento. Por favor recarga la página.")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def leer_todos_los_registros(_client_or_conn):
    engine = obtener_engine_sql()
    try:
        df = pd.read_sql('SELECT * FROM "conducta_registros"', engine)
        df.columns = df.columns.str.strip()
        if 'Grupo' in df.columns:
            df['Grado'] = df['Grupo'].astype(str).str.extract(r'(\d+)')[0].fillna('N/A')
        return df.copy()
    except Exception as e:
        logger.error(f"Error seguro en leer_todos_los_registros: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def leer_todas_las_asignaciones(_client_or_conn, nombre_archivo=None):
    engine = obtener_engine_sql()
    try:
        df = pd.read_sql('SELECT * FROM "asignaciones"', engine)
        df.columns = df.columns.str.strip()
        
        renombres = {}
        for col in df.columns:
            col_limpia = str(col).lower().replace(" ", "_").replace("’", "").replace("'", "").strip()
            if col_limpia in ["usuario_profesor", "usuario_prof", "profesor", "usuario", "correo"]:
                renombres[col] = "Usuario_Profesor"
            elif col_limpia in ["materia", "asignatura", "clase"]:
                renombres[col] = "Materia"
            elif col_limpia in ["grupo", "salon", "seccion"]:
                renombres[col] = "Grupo"
            elif col_limpia in ["nivel", "etapa"]:
                renombres[col] = "Nivel"
            elif col_limpia in ["area", "departamento"]:
                renombres[col] = "Area"
        if renombres:
            df = df.rename(columns=renombres)
        return df.copy()
    except Exception as e:
        logger.error(f"Error interno leyendo 'asignaciones' en Supabase: {e}")
        st.error("🚨 Error al cargar las asignaciones académicas. Intenta nuevamente.")
        return pd.DataFrame()

def obtener_lista_alumnos(client_or_conn, archivo, grupo):
    engine = obtener_engine_sql()
    try:
        query = text('SELECT * FROM "alumnos" WHERE "Grupo_Base" = :grp')
        df = pd.read_sql(query, engine, params={"grp": str(grupo).strip()})
        if df.empty: return []
            
        df.columns = df.columns.str.strip()
        if 'Nombre Completo' in df.columns:
            nombres = df['Nombre Completo'].fillna('').astype(str)
        else:
            p = df.iloc[:, 1].fillna('').astype(str)
            m = df.iloc[:, 2].fillna('').astype(str)
            n = df.iloc[:, 3].fillna('').astype(str)
            nombres = p + " " + m + " " + n
            
        nombres = nombres.str.replace(r'\s+', ' ', regex=True).str.strip()
        return sorted([nom for nom in nombres.unique() if nom])
    except Exception:
        return []

def obtener_dataframe_alumnos(client_or_conn, archivo, grupo):
    engine = obtener_engine_sql()
    try:
        query = text('SELECT * FROM "alumnos" WHERE "Grupo_Base" = :grp')
        df = pd.read_sql(query, engine, params={"grp": str(grupo).strip()})
        if df.empty: return None
        df.columns = df.columns.str.strip()
        
        # 🛡️ Saneamiento genérico de columnas basura sin hardcodear correos personales
        cols_basura = [c for c in df.columns if "@" in str(c) or str(c).startswith("Columna_")]
        df = df.drop(columns=cols_basura, errors='ignore')
        
        if "correo 2" in df.columns: df = df.rename(columns={"correo 2": "correo_secundario"})
        if "Área" in df.columns: df = df.rename(columns={"Área": "area_academica"})
        
        if 'Nombre Completo' not in df.columns:
            p = df.iloc[:, 1].fillna('').astype(str)
            m = df.iloc[:, 2].fillna('').astype(str)
            n = df.iloc[:, 3].fillna('').astype(str)
            df['Nombre Completo'] = (p + " " + m + " " + n).str.replace(r'\s+', ' ', regex=True).str.strip()
        return df.copy()
    except Exception:
        return None

# =================================================================
# 5. FUNCIONES REQUERIDAS POR PANELES DE TUTORÍA Y ALUMNOS
# =================================================================
@st.cache_data(ttl=60)
def compilar_asistencias_grupo_tutor(_client_or_conn, grupo_sel):
    engine = obtener_engine_sql()
    try:
        sufijo = f"% - {str(grupo_sel).strip()}"
        query = text('SELECT * FROM "asistencia_registros" WHERE "Clase" LIKE :suf')
        df = pd.read_sql(query, engine, params={"suf": sufijo})
        if df.empty:
            return pd.DataFrame()
            
        df['Materia'] = df['Clase'].str.replace(f" - {str(grupo_sel).strip()}", "", regex=False).str.strip()
        df['Categoría'] = 'Asistencia'
        df['Falta'] = df['Estatus']
        df['Profesor'] = 'Control de Asistencia'
        df['Puntos_Descontados'] = 0
        df['Observaciones'] = ''
        df['Fecha_DT'] = pd.to_datetime(df['Fecha'], format='%d-%m-%Y', errors='coerce')
        df['Fecha'] = df['Fecha_DT'].dt.strftime("%Y-%m-%d %H:%M:%S")
        return df[df['Falta'].isin(['🔴 Falta', '🟡 Retardo'])].copy()
    except Exception as e:
        logger.error(f"Error en compilar_asistencias_grupo_tutor: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def obtener_info_alumno_por_correo(_client_or_conn, archivo_alumnos, correo_buscar):
    engine = obtener_engine_sql()
    correo_limpio = str(correo_buscar).lower().strip()
    try:
        df = pd.read_sql('SELECT * FROM "alumnos"', engine)
        if df.empty:
            return None
        df.columns = df.columns.str.strip()
        
        col_correo = next((c for c in df.columns if c.lower() in ['correo', 'email']), None)
        col_sec = next((c for c in df.columns if c.lower() in ['correo_secundario', 'correo 2']), None)
        
        coincidencia = pd.DataFrame()
        if col_correo and col_correo in df.columns:
            coincidencia = df[df[col_correo].astype(str).str.strip().str.lower() == correo_limpio]
        if coincidencia.empty and col_sec and col_sec in df.columns:
            coincidencia = df[df[col_sec].astype(str).str.strip().str.lower() == correo_limpio]
            
        if coincidencia.empty:
            return None
            
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
            "Grupo": str(fila.get("Grupo_Base", "")).strip(),
            "ID": str(fila.get("alumno_id", fila.get("ID", ""))),
            "Correo_Padres": str(fila.get("Correo_Tutor_Legal", "")).strip()
        }
    except Exception as e:
        logger.error(f"Error en obtener_info_alumno_por_correo: {e}")
        return None

@st.cache_data(ttl=60)
def obtener_resumen_asistencia_alumno(_client_or_conn, nombre_alumno, grupo_alumno):
    engine = obtener_engine_sql()
    try:
        sufijo = f"% - {str(grupo_alumno).strip()}"
        query = text('SELECT * FROM "asistencia_registros" WHERE "Clase" LIKE :suf AND LOWER(TRIM("Alumno")) = :alm')
        df = pd.read_sql(query, engine, params={"suf": sufijo, "alm": str(nombre_alumno).lower().strip()})
        if df.empty:
            return pd.DataFrame()
            
        try:
            df_conf = pd.read_sql('SELECT * FROM "asistencia_config"', engine)
            df_conf.columns = df_conf.columns.str.strip()
        except Exception:
            df_conf = pd.DataFrame()
            
        limite_faltas_dict = {0: 99, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9}
        resultados = []
        
        for clase_nombre, df_clase in df.groupby('Clase'):
            materia_nombre = clase_nombre.replace(f" - {str(grupo_alumno).strip()}", "").strip()
            
            conf_materia = df_conf[df_conf['Clase'] == clase_nombre] if not df_conf.empty and 'Clase' in df_conf.columns else pd.DataFrame()
            dias_semana_clase = 0
            if not conf_materia.empty:
                dias_semana_clase = sum(int(conf_materia.iloc[0].get(c, 0)) for c in ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes'])
                
            limite = limite_faltas_dict.get(dias_semana_clase, 7)
            
            estatus_clase = df_clase['Estatus'].astype(str)
            hubo_clase = ~estatus_clase.str.startswith("⚪")  # 🛡️ "Sin Clase (motivo)" nunca cuenta
            faltas_reales = int((estatus_clase.str.contains("Falta") & hubo_clase).sum())
            retardos = int((estatus_clase.str.contains("Retardo") & hubo_clase).sum())
            faltas_efectivas = faltas_reales + (retardos // 3)
            derecho = "✅ SÍ" if faltas_efectivas <= limite else "❌ NO"
            
            resultados.append({
                "Materia": materia_nombre,
                "Frecuencia Semanal": f"{dias_semana_clase} hrs" if dias_semana_clase > 0 else "N/D",
                "Faltas Reales": faltas_reales,
                "Retardos": retardos,
                "Faltas Efectivas": faltas_efectivas,
                "Límite Permitido": limite,
                "Derecho Examen": derecho
            })
            
        return pd.DataFrame(resultados)
    except Exception as e:
        logger.error(f"Error en obtener_resumen_asistencia_alumno: {e}")
        return pd.DataFrame()

def sanitizar_para_csv(df_input):
    df_sanitizado = df_input.copy()
    for col in df_sanitizado.columns:
        serie = df_sanitizado[col]
        # 🛡️ Con pandas 3 el texto ya no es 'object'; además se respetan los vacíos y los números
        if pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie):
            df_sanitizado[col] = serie.map(
                lambda val: ("'" + val) if isinstance(val, str) and val.strip().startswith(('=', '+', '-', '@', '\t', '\r')) else val
            )
    return df_sanitizado

def format_calif(val):
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

# =================================================================
# MATERIA TEÓRICA (laboratorio y teoría comparten asistencia y conducta)
# Misma tabla que usan paneles/asistencia.py y paneles/docente.py.
# =================================================================
_FUSION_MATERIAS = {
    "lab física": "Física",
    "laboratorio de química": "Química",
    "lab química": "Química",
    "laboratorio de biología": "Biología 1",
    "lab biología": "Biología 1",
    "laboratorio de física iii": "Física III",
    "lab física iii": "Física III",
    "laboratorio de química iii": "Química III",
    "lab química iii": "Química III",
    "laboratorio de biología iv": "Biología IV",
    "lab biología iv": "Biología IV",
    "laboratorio de lab física iv a i": "Física IV A I",
    "lab física iv a i": "Física IV A I",
    "laboratorio de lab física iv a ii": "Física IV A II",
    "lab física iv a ii": "Física IV A II",
    "laboratorio de lab química iv a i": "Química IV A I",
    "lab química iv a i": "Química IV A I",
    "laboratorio de lab química iv a ii": "Química IV A II",
    "lab química iv a ii": "Química IV A II",
}

def obtener_materia_teorica(nombre_materia):
    limpio = str(nombre_materia).lower().strip().replace("  ", " ")
    return _FUSION_MATERIAS.get(limpio, str(nombre_materia).strip())