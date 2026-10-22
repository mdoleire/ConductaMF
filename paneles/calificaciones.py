# paneles/calificaciones.py
import streamlit as st
import pandas as pd
import uuid
import time
import logging
import re
import requests
import unicodedata
from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy import text

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_ASISTENCIA,
    PERIODOS_LECTIVOS, 
    SUPER_USUARIOS_WHITELIST
)
try:
    # Nombres exactos de tareas de laboratorio que SÍ se importan en materias que no son de laboratorio
    # (sin importar mayúsculas ni acentos). Se puede definir en config.py.
    from config import ACTIVIDADES_LAB_SIEMPRE_INCLUIDAS
except ImportError:
    ACTIVIDADES_LAB_SIEMPRE_INCLUIDAS = ["Laboratorio"]
from database import (
    leer_datos, 
    obtener_lista_alumnos, 
    leer_todas_las_asignaciones,
    obtener_engine_sql,
    leer_todos_los_registros,
    obtener_materia_teorica,
    sanitizar_para_csv
)
from calculadora import format_calif, calcular_calificacion_progresiva

# 🎨 SEMÁFORO EN ESCALA 100 (GOOGLE CLASSROOM)
def format_calif_100(val):
    if val >= 90.0: return f"🟢 {val:.1f}"
    if val >= 70.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

# 🛡️ EMPAREJADOR INTELIGENTE DE NOMBRES (INMUNE AL ORDEN NOMBRE/APELLIDO)
def normalizar_palabras(txt):
    s = str(txt).lower().strip().replace("'", "").replace("’", "")
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return set(w for w in s.split() if len(w) > 2)

def encontrar_alumno_oficial(nombre_cr, lista_oficial):
    tokens_cr = normalizar_palabras(nombre_cr)
    mejor_match = None
    max_coincidencias = 0
    for nom_of in lista_oficial:
        tokens_of = normalizar_palabras(nom_of)
        interseccion = len(tokens_cr.intersection(tokens_of))
        if interseccion > max_coincidencias and interseccion >= 2:
            max_coincidencias = interseccion
            mejor_match = nom_of
    return mejor_match or nombre_cr

# =================================================================
# 🛡️ AUXILIARES DE CLASSROOM Y PERIODOS
# =================================================================
def _classroom_get(url, headers, params=None):
    data = requests.get(url, headers=headers, params=params or {}, timeout=20).json()
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise RuntimeError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
    return data

def _classroom_get_todo(url, headers, clave):
    """Recorre todas las páginas (nextPageToken). Antes solo se leía la primera."""
    items, token = [], None
    while True:
        data = _classroom_get(url, headers, {"pageToken": token} if token else None)
        lote = data.get(clave, [])
        if isinstance(lote, list):
            items.extend(lote)
        token = data.get("nextPageToken")
        if not token:
            return items

def _fecha_tarea_cr(tarea):
    """Fecha de entrega de la tarea; si no tiene, la de creación."""
    d = tarea.get("dueDate") or {}
    try:
        if d.get("year") and d.get("month") and d.get("day"):
            return date(int(d["year"]), int(d["month"]), int(d["day"]))
        return date.fromisoformat(str(tarea.get("creationTime", ""))[:10])
    except (ValueError, TypeError):
        return None

def _periodo_de_fecha(fecha, periodos):
    """Mismo criterio que asistencia.py: el primer periodo cuya fecha de fin no ha pasado."""
    for p in periodos:
        if fecha <= datetime.strptime(p["fin"], "%Y-%m-%d").date():
            return p["nombre"]
    return periodos[-1]["nombre"] if periodos else None

# 🧪 "Lab" como palabra o "laboratorio": no confunde "Elaboración", "colaborativo", "sílabas" ni "Labor"
_PATRON_LAB = re.compile(r"\blab(?:s|\.)?(?!\w)|\blaboratorio", re.IGNORECASE)

def _es_lab(texto):
    return bool(_PATRON_LAB.search(str(texto)))

def _normalizar(texto):
    s = unicodedata.normalize("NFD", str(texto).lower())
    return " ".join("".join(c for c in s if unicodedata.category(c) != "Mn").split())

def _mostrar_lista(items, maximo=15):
    for item in items[:maximo]:
        st.markdown(f"- {item}")
    if len(items) > maximo:
        st.caption(f"…y {len(items) - maximo} más.")

# =================================================================
# 🧮 PROMEDIO DEL PERIODO (lo usan la matriz de captura y la pestaña de finales)
# =================================================================
def calcular_promedios_periodo(actividades, notas, alumnos, rubros_pesos):
    """Promedio del periodo en base 100 para cada alumno.
    Cada rubro promedia sus actividades (una actividad sin nota cuenta 0) y se pondera con su
    porcentaje. Si un rubro aún no tiene actividades, el resultado se reescala a los rubros evaluados.
    Los rubros se comparan sin distinguir mayúsculas, acentos ni espacios: antes "Trabajos y Tareas" y
    "Trabajos y tareas" contaban como dos rubros y ese porcentaje se sumaba dos veces."""
    pesos_norm = {_normalizar(k): float(v) for k, v in rubros_pesos.items()}

    def peso_rubro(nombre):
        r = _normalizar(nombre)
        if r in pesos_norm:
            return pesos_norm[r]
        for k, w in pesos_norm.items():
            if k in r or r in k:
                return w
        return list(pesos_norm.values())[0] if pesos_norm else 100.0

    lista_acts = []
    for _, act in actividades.iterrows():
        id_act = str(act["ID_Actividad"]).strip()
        notas_act = notas[notas["ID_Actividad"] == id_act] if not notas.empty else pd.DataFrame()
        dicc = (dict(zip(notas_act["Alumno"].astype(str).str.strip(),
                         pd.to_numeric(notas_act["Nota"], errors="coerce").fillna(0.0)))
                if not notas_act.empty else {})
        lista_acts.append((_normalizar(act["Rubro"]), float(act.get("Puntos_Max", 100.0)), dicc))

    rubros_con_tareas = list({r for r, _, _ in lista_acts})
    peso_total = sum(peso_rubro(r) for r in rubros_con_tareas)

    resultado = {}
    for al in alumnos:
        desglose = {r: [] for r in rubros_con_tareas}
        for rubro, p_max, dicc in lista_acts:
            nota = float(dicc.get(str(al).strip(), 0.0))
            desglose[rubro].append((nota / p_max) * 100.0 if p_max > 0 else 0.0)
        puntos = sum((sum(l) / len(l) if l else 0.0) * (peso_rubro(r) / 100.0) for r, l in desglose.items())
        resultado[al] = round(puntos / (peso_total / 100.0), 1) if peso_total > 0 else 0.0
    return resultado

def _fecha_columna_asistencia(columna):
    """'15-10-2026' o '15-10-2026 (S1)' → date."""
    try:
        return datetime.strptime(str(columna).split(" (")[0].strip(), "%d-%m-%Y").date()
    except ValueError:
        return None

# =================================================================
# 🏁 PESTAÑA: CALIFICACIONES FINALES DEL PERIODO
# =================================================================
def _renderizar_finales_periodo(gc, engine, materia_sel, grupo_sel, grupo_limpio, clase_id,
                                periodo_sel, periodos, alumnos):
    info_p = next((p for p in periodos if p["nombre"] == periodo_sel), None)
    if info_p is None:
        st.info("Elige un periodo para ver sus calificaciones finales.")
        return
    inicio = datetime.strptime(info_p["inicio"], "%Y-%m-%d").date()
    fin = datetime.strptime(info_p["fin"], "%Y-%m-%d").date()
    hoy = datetime.now(ZoneInfo("America/Mexico_City")).date()

    st.markdown(f"#### {materia_sel} {grupo_sel}, {periodo_sel}")
    if hoy < inicio:
        st.info(f"El {periodo_sel} empieza el {inicio:%d/%m/%Y}; todavía no hay calificaciones.")
        return
    if hoy > fin:
        st.caption(f"🔒 El {periodo_sel} cerró el {fin:%d/%m/%Y}: estas son las calificaciones finales.")
    else:
        st.caption(f"⏳ El {periodo_sel} sigue en curso hasta el {fin:%d/%m/%Y}: estas calificaciones todavía pueden cambiar.")
    if not alumnos:
        st.warning(f"No hay alumnos registrados en la lista de '{grupo_limpio}'.")
        return

    avisos = []

    # 1. Académica: mismo cálculo que la matriz de captura
    pond = pd.read_sql(text('SELECT * FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                       engine, params={"c": clase_id, "p": periodo_sel})
    acts = pd.read_sql(text('SELECT * FROM "calif_actividades" WHERE "Clase" = :c AND "Periodo" = :p'),
                       engine, params={"c": clase_id, "p": periodo_sel})
    promedios = {}
    if pond.empty:
        avisos.append("No hay criterios de evaluación para este periodo; configúralos en la pestaña de captura.")
    elif acts.empty:
        avisos.append("Todavía no hay actividades en este periodo.")
    else:
        notas = pd.read_sql(text('SELECT * FROM "calif_notas" WHERE "Clase" = :c'), engine, params={"c": clase_id})
        promedios = calcular_promedios_periodo(acts, notas, alumnos, dict(zip(pond["Rubro"], pond["Porcentaje"])))

    # 2. Conducta: reportes de esta materia y grupo dentro del periodo (laboratorio cuenta con su teoría)
    materia_teorica = obtener_materia_teorica(materia_sel)
    conducta = {}
    df_c = leer_todos_los_registros(gc)
    if not df_c.empty and {"Alumno", "Materia", "Grupo", "Fecha"}.issubset(df_c.columns):
        df_c = df_c.copy()
        df_c["_fecha"] = pd.to_datetime(df_c["Fecha"], errors="coerce")
        df_c = df_c[
            (df_c["Materia"].astype(str).str.strip() == materia_teorica)
            & (df_c["Grupo"].astype(str).str.split("(").str[0].str.strip() == grupo_limpio)
            & (df_c["_fecha"] >= pd.Timestamp(inicio))
            & (df_c["_fecha"] < pd.Timestamp(fin) + pd.Timedelta(days=1))   # incluye todo el último día
        ]
        for al_l, df_al in df_c.groupby(df_c["Alumno"].astype(str).str.strip().str.lower()):
            calif_c, _ = calcular_calificacion_progresiva(df_al)
            conducta[al_l] = (calif_c, len(df_al))

    # 3. Asistencia: la lista de la clase (laboratorio comparte la de su teoría)
    faltas, retardos = {}, {}
    df_a = leer_datos(gc, FILE_ASISTENCIA, f"{materia_teorica} - {grupo_sel}")
    if not df_a.empty and "Alumno" in df_a.columns:
        cols_periodo = []
        for c in df_a.columns:
            f = _fecha_columna_asistencia(c) if c != "Alumno" else None
            if f and inicio <= f <= fin:
                cols_periodo.append(c)
        for _, r in df_a.iterrows():
            al_l = str(r["Alumno"]).strip().lower()
            valores = [str(r[c]).strip() for c in cols_periodo]
            faltas[al_l] = sum(v == "🔴 Falta" for v in valores)
            retardos[al_l] = sum(v == "🟡 Retardo" for v in valores)
    else:
        avisos.append("Todavía no hay listas de asistencia de esta clase.")

    filas = []
    for al in alumnos:
        al_l = str(al).strip().lower()
        calif_c, n_inc = conducta.get(al_l, (10.0, 0))
        filas.append({
            "Alumno": al,
            "Académica": promedios.get(al),
            "Conducta": calif_c,
            "Incidencias": n_inc,
            "Faltas": faltas.get(al_l, 0),
            "Retardos": retardos.get(al_l, 0),
        })
    df = pd.DataFrame(filas)
    mostrar_retardos = df["Retardos"].sum() > 0

    m1, m2, m3 = st.columns(3)
    academicas = df["Académica"].dropna()
    m1.metric("Promedio académico del grupo", f"{academicas.mean():.1f}" if not academicas.empty else "—")
    m2.metric("Promedio de conducta", f"{df['Conducta'].mean():.1f}")
    m3.metric("Faltas en el periodo", int(df["Faltas"].sum()))

    vista = pd.DataFrame({
        "Alumno": df["Alumno"],
        "Académica (base 100)": [format_calif_100(v) if pd.notna(v) else "—" for v in df["Académica"]],
        "Conducta (base 10)": [format_calif(v) for v in df["Conducta"]],
        "Incidencias": df["Incidencias"],
        "Faltas": df["Faltas"],
    })
    if mostrar_retardos:
        vista["Retardos"] = df["Retardos"]
    st.dataframe(vista, hide_index=True, use_container_width=True)
    st.caption("Académica: promedio ponderado de las actividades del periodo, de Classroom y manuales, igual que en la captura. "
               "Conducta: descuentos de los reportes de esta materia en el periodo. "
               "Faltas: listas de asistencia de esta clase en el periodo.")
    for aviso in avisos:
        st.info(aviso)

    df_csv = df.rename(columns={"Académica": "Académica (base 100)", "Conducta": "Conducta (base 10)"})
    if not mostrar_retardos:
        df_csv = df_csv.drop(columns=["Retardos"])
    st.download_button(
        "📥 Descargar calificaciones finales (CSV)",
        data=sanitizar_para_csv(df_csv).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"Finales_{clase_id}_{periodo_sel}.csv".replace(" ", "_"),
        mime="text/csv",
    )

def renderizar_panel_calificaciones(gc, usuario, nombre_prof):
    st.header(f"📊 Calificador Académico: {nombre_prof}")
    
    # -----------------------------------------------------------------
    # 🛡️ VARIABLES GLOBALES INICIALIZADAS
    # -----------------------------------------------------------------
    token_google = st.session_state.get("access_token")
    id_curso_auto = None
    nombre_curso_auto = ""
    cursos_cr = []
    res_c = {}
    
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    engine = obtener_engine_sql()
    
    # 1. Cargar asignaciones docentes
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura de asignaciones docentes.")
        return
        
    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
    
    if es_superusuario:
        mis_asig = df_asig.copy()
    else:
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
        
    if mis_asig.empty:
        st.warning("⚠️ Sin materias asignadas para calificar.")
        return
        
    niveles = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles) > 1:
        nivel_sel = st.radio("Sección Escolar:", niveles, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_sel]
    else:
        nivel_sel = niveles[0]

    # Selectores: Materia, Grupo y Periodo
    c1, c2, c3 = st.columns(3)
    materia_sel = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="calif_mat")
    grupos_de_esta_materia = mis_asig[mis_asig['Materia'] == materia_sel]['Grupo'].unique().tolist()
    grupo_sel = c2.selectbox("Grupo activo:", grupos_de_esta_materia, key="calif_grup")
    
    nivel_key = "Secundaria" if "secundaria" in str(nivel_sel).lower() else "Preparatoria"
    periodos_nivel_cfg = PERIODOS_LECTIVOS.get(nivel_key, [])
    periodos_disponibles = [p["nombre"] for p in periodos_nivel_cfg]
    # 🛡️ Por defecto el periodo vigente (antes siempre arrancaba en el primero)
    periodo_vigente = _periodo_de_fecha(datetime.now(ZoneInfo("America/Mexico_City")).date(), periodos_nivel_cfg)
    idx_periodo_vigente = periodos_disponibles.index(periodo_vigente) if periodo_vigente in periodos_disponibles else 0
    periodo_sel = c3.selectbox("Periodo de Evaluación:", periodos_disponibles, index=idx_periodo_vigente, key="calif_per")
    
    clase_id = f"{materia_sel} - {grupo_sel}"
    
    # 2. Cargar lista oficial de alumnos de este salón desde el inicio
    try:
        grupo_limpio = grupo_sel.split("(")[0].strip()
        alumnos_clase = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
    except Exception:
        alumnos_clase = []

    # -----------------------------------------------------------------
    # 🤖 CEREBRO AUTO-MATCHER CLASSROOM
    # -----------------------------------------------------------------
    if token_google:
        try:
            headers_cr = {"Authorization": f"Bearer {token_google}"}
            res_c = requests.get("https://classroom.googleapis.com/v1/courses?teacherId=me&courseStates=ACTIVE", headers=headers_cr, timeout=20).json()
            
            if "error" not in res_c:
                cursos_cr = res_c.get("courses", [])
                if cursos_cr:
                    import re
                    import unicodedata
                    def limpiar_texto(txt):
                        if not txt: return ""
                        t = str(txt).lower().strip()
                        t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
                        return re.sub(r'[^a-z0-9]', '', t) # 🧹 DESTRUYE TODO excepto letras y números

                    materia_limpia = limpiar_texto(materia_sel)
                    mat_clave = limpiar_texto(materia_sel.split()[0]) # Ej. "fisica"
                    grp_num = ''.join(filter(str.isdigit, grupo_sel)) # Ej. "4"
                    grp_letra = ''.join(filter(str.isalpha, grupo_sel)).lower() # Ej. "b"
                    grupo_exacto = f"{grp_num}{grp_letra}" # Ej. "4b"
                    app_quiere_lab = "lab" in materia_limpia
                    
                    for c in cursos_cr:
                        nom_cr = limpiar_texto(c.get("name", ""))
                        sec_cr = limpiar_texto(c.get("section", ""))
                        texto_total = nom_cr + sec_cr
                        cr_es_lab = "lab" in texto_total
                        
                        if mat_clave in texto_total and grupo_exacto in texto_total:
                            if app_quiere_lab == cr_es_lab:
                                id_curso_auto = c["id"]
                                nombre_curso_auto = f"{c.get('name', 'Curso')} {c.get('section', '')}".strip()
                                break
        except Exception:
            pass 

    st.markdown("---")

    # =================================================================
    # PESTAÑAS: CAPTURA Y CALIFICACIONES FINALES DEL PERIODO
    # =================================================================
    tab_captura, tab_finales = st.tabs(["📝 Capturar Calificaciones", "🏁 Calificaciones Finales del Periodo"])

    # La pestaña de finales se dibuja primero en el código porque la de captura puede
    # detenerse (st.stop / return) cuando faltan criterios o actividades.
    with tab_finales:
        _renderizar_finales_periodo(gc, engine, materia_sel, grupo_sel, grupo_limpio, clase_id,
                                    periodo_sel, periodos_nivel_cfg, alumnos_clase)

    with tab_captura:
        # 🌟 LEYENDA VERDE DE CONEXIÓN EXITOSA
        if id_curso_auto:
            st.success(f"🔗 Conectado automáticamente a tu Classroom de: **{nombre_curso_auto}**")

        # =================================================================
        # 3. PONDERACIONES / CRITERIOS (SUPABASE)
        # =================================================================
        query_pond = text('SELECT * FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p')
        pond_actual = pd.read_sql(query_pond, engine, params={"c": clase_id, "p": periodo_sel})
        
        if pond_actual.empty:
            st.warning(f"⚠️ No has configurado los criterios de evaluación para **{clase_id}** en el **{periodo_sel}**.")
        
            # 🎓 OPCIÓN 1: CARGAR DIRECTO DE GOOGLE CLASSROOM (RECOMENDADA)
            if token_google:
                with st.container():
                    st.markdown("##### 🚀 Opción Rápida: Importar desde Classroom")
                    st.caption("Lee automáticamente los porcentajes que ya configuraste en los ajustes de Google Classroom.")
                
                    if "error" in res_c:
                        st.warning("⚠️ Tu sesión con Google Classroom caducó por seguridad (1 hora límite).")
                        st.info("👉 Por favor, usa el botón '🔒 Cerrar Sesión' en el menú izquierdo y vuelve a entrar para renovar tu conexión.")
                    elif not cursos_cr:
                        st.info("ℹ️ Tu cuenta de Google no tiene cursos activos configurados como 'Profesor'.")
                    else:
                        if id_curso_auto:
                            id_c_pond = id_curso_auto
                            btn_texto = "🎓 Cargar Criterios Oficiales (Detectado Automáticamente)"
                        else:
                            dict_c = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                            curso_elegido_pond = st.selectbox("Selecciona la clase correspondiente en Classroom:", list(dict_c.keys()), key="c_pond_cr")
                            id_c_pond = dict_c[curso_elegido_pond]
                            btn_texto = "🎓 Cargar Criterios del Curso Seleccionado"
                        
                        if st.button(btn_texto, type="primary", use_container_width=True, key="btn_cargar_criterios_cr_unico"):
                            with st.spinner("Descargando categorías y ponderaciones oficiales de Classroom..."):
                                try:
                                    headers_cr = {"Authorization": f"Bearer {token_google}"}
                                    res_det = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_c_pond}", headers=headers_cr, timeout=20).json()
                                
                                    if "error" in res_det:
                                        st.error(f"🚨 Google Classroom reportó: {res_det['error'].get('message', res_det['error'])}")
                                    else:
                                        cats = res_det.get("gradebookSettings", {}).get("gradeCategories", [])
                                        if not cats: cats = res_det.get("gradeCategories", [])
                                        
                                        if not cats:
                                            st.warning("⚠️ Esta clase en Classroom no devolvió categorías de calificación.")
                                            st.info("💡 Desplázate hacia abajo y usa la configuración manual.")
                                        else:
                                            with engine.begin() as conn:
                                                conn.execute(
                                                    text('DELETE FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                                                    {"c": clase_id, "p": periodo_sel}
                                                )
                                                for cat in cats:
                                                    cat_nom = str(cat.get("name", "")).strip()
                                                    cat_w_raw = cat.get("weight", 0)
                                                    cat_pct = int(round(cat_w_raw / 10000)) if cat_w_raw > 0 else 0
                                                    if cat_nom: # 🛡️ FIX: Acepta categorías con 0%
                                                        conn.execute(
                                                            text('INSERT INTO "calif_ponderaciones" ("Clase", "Periodo", "Rubro", "Porcentaje") VALUES (:c, :p, :r, :pct)'),
                                                            {"c": clase_id, "p": periodo_sel, "r": cat_nom, "pct": cat_pct}
                                                        )
                                            leer_datos.clear()
                                            st.success(f"✅ ¡Éxito! Se importaron {len(cats)} categorías oficiales de Classroom.")
                                            time.sleep(1)
                                            st.rerun()
                                except Exception as e_cr_pond:
                                    st.error(f"Error técnico de conexión: {e_cr_pond}")
                    
            st.markdown("---")

            # 📝 OPCIÓN 2: CONFIGURACIÓN MANUAL
            st.markdown("##### 📝 Opción Alternativa: Configuración Manual")
            criterios_base = pd.DataFrame([
                {"Categoría / Rubro": "Examen de periodo", "Porcentaje (%)": 40},
                {"Categoría / Rubro": "Laboratorio", "Porcentaje (%)": 30},
                {"Categoría / Rubro": "Trabajos y Tareas", "Porcentaje (%)": 15},
                {"Categoría / Rubro": "Actividades y participación", "Porcentaje (%)": 15}
            ])
        
            df_criterios_edit = st.data_editor(
                criterios_base,
                num_rows="dynamic",
                column_config={
                    "Categoría / Rubro": st.column_config.TextColumn("Categoría / Rubro", required=True),
                    "Porcentaje (%)": st.column_config.NumberColumn("Porcentaje (%)", min_value=0, max_value=100, step=5, required=True)
                },
                use_container_width=True,
                hide_index=True,
                key=f"editor_pond_{clase_id}_{periodo_sel}"
            )
        
            suma_porcentajes = int(df_criterios_edit["Porcentaje (%)"].fillna(0).sum())
            todas_mis_clases = sorted(list(set([f"{r['Materia']} - {r['Grupo']}" for _, r in mis_asig.iterrows()])))
        
            st.markdown("##### 👥 Aplicar estos mismos criterios a:")
            clases_destino_pond = st.multiselect("Selecciona las materias/salones que compartirán esta ponderación:", options=todas_mis_clases, default=[clase_id])
        
            c_status, c_save_btn = st.columns([3, 2])
            with c_status:
                if suma_porcentajes == 100:
                    st.success(f"Suma total: **{suma_porcentajes}%** ✅")
                else:
                    st.error(f"Suma total: **{suma_porcentajes}%** ❌ (Debe dar 100%)")
                
            with c_save_btn:
                if st.button("💾 Guardar Criterios Manualmente", type="secondary", use_container_width=True):
                    if suma_porcentajes != 100:
                        st.error("🚨 La suma debe dar 100%.")
                    else:
                        with st.spinner("Guardando en Supabase..."):
                            with engine.begin() as conn:
                                for target_clase in clases_destino_pond:
                                    conn.execute(
                                        text('DELETE FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                                        {"c": target_clase, "p": periodo_sel}
                                    )
                                    for _, fila in df_criterios_edit.iterrows():
                                        r_nom = str(fila["Categoría / Rubro"]).strip()
                                        r_pct = int(fila["Porcentaje (%)"])
                                        if r_nom:
                                            conn.execute(
                                                text('INSERT INTO "calif_ponderaciones" ("Clase", "Periodo", "Rubro", "Porcentaje") VALUES (:c, :p, :r, :pct)'),
                                                {"c": target_clase, "p": periodo_sel, "r": r_nom, "pct": r_pct}
                                            )
                            leer_datos.clear()
                            st.success("✅ Criterios guardados exitosamente.")
                            time.sleep(1)
                            st.rerun()
            st.stop() # 🛑 Muro de contención hasta que haya criterios
        
        rubros_pesos = dict(zip(pond_actual['Rubro'], pond_actual['Porcentaje']))
        categorias_validas = list(rubros_pesos.keys())
    
        col_t1, col_t2 = st.columns([4, 1])
        with col_t1:
            cols_badge = st.columns(len(rubros_pesos))
            for i, (rubro, pct) in enumerate(rubros_pesos.items()):
                cols_badge[i].metric(rubro, f"{pct}%")
            
        with col_t2:
            if st.button("⚙️ Modificar Criterios", help="Borra las ponderaciones actuales para reeditarlas", use_container_width=True):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text('DELETE FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p'),
                            {"c": clase_id, "p": periodo_sel}
                        )
                    leer_datos.clear()
                    st.success("✅ Criterios eliminados. Ya puedes reconfigurarlos.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e_mod:
                    st.error(f"Error al modificar criterios: {e_mod}")
        
        st.markdown("---")

        # =================================================================
        # 4. ACCIONES DE ACTIVIDADES Y DESCARGA CLASSROOM
        # =================================================================
        query_act = text('SELECT * FROM "calif_actividades" WHERE "Clase" = :c AND "Periodo" = :p')
        mis_actividades = pd.read_sql(query_act, engine, params={"c": clase_id, "p": periodo_sel})

        col_btn_act1, col_btn_act2, col_btn_act3, col_btn_act4 = st.columns(4)
    
        # --- BOTÓN 1: CREAR MANUAL ---
        with col_btn_act1:
            with st.popover("➕ Nueva Tarea Manual", use_container_width=True):
                st.markdown("### Crear Actividad Manual")
                nombre_actividad = st.text_input("Nombre de la Actividad:", placeholder="Ej. Tarea 1 - Vectores")
                rubro_actividad = st.selectbox("Categoría a la que pertenece:", categorias_validas)
                puntos_max = st.number_input("Puntos Máximos:", min_value=10.0, max_value=100.0, value=100.0, step=10.0)
            
                st.markdown("##### 👥 Asignar a grupos:")
                grupos_seleccionados_tarea = st.multiselect("Grupos que harán la actividad:", options=grupos_de_esta_materia, default=[grupo_sel])
            
                if st.button("🚀 Crear y Asignar", type="primary", use_container_width=True):
                    if not nombre_actividad.strip():
                        st.error("⚠️ Asigna un nombre a la actividad.")
                    elif not grupos_seleccionados_tarea:
                        st.error("⚠️ Selecciona al menos un grupo.")
                    else:
                        with st.spinner("Creando en Supabase..."):
                            try:
                                fecha_creacion = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
                                with engine.begin() as conn:
                                    for g in grupos_seleccionados_tarea:
                                        id_act = f"ACT-{uuid.uuid4().hex[:6].upper()}"
                                        clase_target = f"{materia_sel} - {g}"
                                        conn.execute(
                                            text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                                    VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)'''),
                                            {"id": id_act, "c": clase_target, "p": periodo_sel, "nom": nombre_actividad.strip(), "rub": rubro_actividad, "pmax": puntos_max, "fec": fecha_creacion}
                                        )
                                leer_datos.clear()
                                st.success(f"✅ Actividad creada para {len(grupos_seleccionados_tarea)} grupo(s).")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e_act:
                                st.error(f"Error al crear: {e_act}")

        # --- BOTÓN 2: SINCRONIZAR TAREAS CLASSROOM ---
        with col_btn_act2:
            if not token_google:
                with st.popover("🔄 Sincronizar (M...)", use_container_width=True):
                    st.warning("⚠️ Requiere conexión:")
                    client_id_cr = st.secrets["auth"]["google_client_id"]
                    redirect_uri_cr = st.secrets["auth"]["redirect_uri"]
                    params_cr = {
                        "client_id": client_id_cr,
                        "redirect_uri": redirect_uri_cr,
                        "response_type": "code",
                        "scope": "openid email profile https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.students.readonly https://www.googleapis.com/auth/classroom.rosters.readonly",
                        "access_type": "online",
                        "prompt": "consent"
                    }
                    import urllib.parse
                    url_cr = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params_cr)}"
                    st.link_button("🔑 Conectar Classroom", url_cr, type="primary", use_container_width=True)
            else:
                def ejecutar_sincronizacion(id_curso_objetivo, forzar=frozenset()):
                    """Importa tareas y notas de Classroom. `forzar`: IDs (CR-...) que se importan en el
                    periodo seleccionado aunque el filtro de periodo o de laboratorio las omitiría."""
                    try:
                        headers_cr = {"Authorization": f"Bearer {token_google}"}
                        base_cr = f"https://classroom.googleapis.com/v1/courses/{id_curso_objetivo}"

                        res_curso_det = _classroom_get(base_cr, headers_cr)
                        cats_cr = res_curso_det.get("gradebookSettings", {}).get("gradeCategories", [])
                        if not cats_cr: cats_cr = res_curso_det.get("gradeCategories", [])
                        mapa_cats_cr = {str(c["id"]): str(c.get("name", "Trabajos y Tareas")).strip() for c in cats_cr if isinstance(c, dict) and "id" in c}

                        tareas_cr = _classroom_get_todo(f"{base_cr}/courseWork", headers_cr, "courseWork")
                        estudiantes_cr = _classroom_get_todo(f"{base_cr}/students", headers_cr, "students")

                        # 🛡️ Correo → nombre oficial con las columnas reales de "alumnos".
                        # Antes se leía "Nombre Completo" (no existe): todo correo empataba con un
                        # nombre vacío y esas calificaciones se descartaban sin aviso.
                        # Nota: Classroom solo envía el correo si la app pide el permiso
                        # classroom.profile.emails, que no se pide; en la práctica se empata por nombre.
                        df_grupo_db = pd.read_sql(
                            text('SELECT "Apellido Paterno", "Apellido Materno", "Nombres", "correo", "correo 2" FROM "alumnos" WHERE "Grupo_Base" = :grp'),
                            engine, params={"grp": grupo_limpio}
                        )
                        alumnos_clase_set = set(alumnos_clase)
                        mapa_email_a_oficial = {}
                        for _, r in df_grupo_db.iterrows():
                            partes = ["" if pd.isna(r.get(c)) else str(r.get(c)).strip() for c in ("Apellido Paterno", "Apellido Materno", "Nombres")]
                            nombre_of = " ".join(" ".join(partes).split())
                            if nombre_of not in alumnos_clase_set:
                                continue
                            for col_mail in ("correo", "correo 2"):
                                mail = "" if pd.isna(r.get(col_mail)) else str(r.get(col_mail)).lower().strip()
                                if "@" in mail:
                                    mapa_email_a_oficial[mail] = nombre_of

                        mapa_userid_a_nombre = {}
                        sin_emparejar = []
                        for s in estudiantes_cr:
                            if not isinstance(s, dict): continue
                            u_id = s.get("userId")
                            prof = s.get("profile") or {}
                            email_cr = str(prof.get("emailAddress") or "").lower().strip()
                            nom_cr = str((prof.get("name") or {}).get("fullName", "")).strip()
                            if email_cr and email_cr in mapa_email_a_oficial:
                                mapa_userid_a_nombre[u_id] = mapa_email_a_oficial[email_cr]
                            else:
                                candidato = encontrar_alumno_oficial(nom_cr, alumnos_clase)
                                if candidato in alumnos_clase_set:
                                    mapa_userid_a_nombre[u_id] = candidato
                                else:
                                    # 🛡️ Antes se guardaba con el nombre de Classroom y quedaba huérfana
                                    sin_emparejar.append(nom_cr or str(u_id))

                        # Periodo ya asignado a las tareas de Classroom que existen en esta clase
                        existentes = pd.read_sql(
                            text('SELECT "ID_Actividad", "Periodo" FROM "calif_actividades" WHERE "Clase" = :c AND "ID_Actividad" LIKE :pref'),
                            engine, params={"c": clase_id, "pref": "CR-%"}
                        )
                        periodo_existente = dict(zip(existentes["ID_Actividad"].astype(str), existentes["Periodo"].astype(str)))

                        fecha_hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
                        total_notas = 0
                        tareas_procesadas = 0
                        omitidas_periodo, omitidas_lab, sin_peso = [], [], []
                        es_materia_lab = _es_lab(materia_sel)
                        rubros_exactos = {str(r).strip() for r in rubros_pesos}
                        # Rubro para tareas sin categoría, escrito exactamente como en las ponderaciones
                        rubro_por_defecto = next((str(r).strip() for r in rubros_pesos
                                                  if _normalizar(r) == "trabajos y tareas"), "Trabajos y Tareas")
                        sin_categoria = []
                        rubros_norm = {_normalizar(r) for r in rubros_pesos}
                        excepciones_norm = {_normalizar(x) for x in ACTIVIDADES_LAB_SIEMPRE_INCLUIDAS}

                        with engine.begin() as conn:
                            for t in tareas_cr:
                                if not isinstance(t, dict): continue
                                if t.get("state") == "DELETED": continue

                                id_act_cr = f"CR-{t.get('id', '0')}"

                                # 🛡️ PERIODO: las tareas ya registradas conservan el suyo (no se reacomodan
                                # periodos cerrados); las nuevas se asignan por fecha de entrega o creación.
                                # Solo se procesan las que pertenecen al periodo seleccionado.
                                nom_t = str(t.get("title", "Sin Título"))
                                forzada = id_act_cr in forzar
                                if id_act_cr in periodo_existente:
                                    periodo_tarea = periodo_existente[id_act_cr]
                                    motivo_periodo = f"ya está registrada en el {periodo_tarea}"
                                else:
                                    fecha_t = _fecha_tarea_cr(t)
                                    periodo_tarea = _periodo_de_fecha(fecha_t, periodos_nivel_cfg) if fecha_t else periodo_sel
                                    tipo_fecha = "entrega" if t.get("dueDate") else "creación"
                                    motivo_periodo = (f"su fecha de {tipo_fecha} ({fecha_t:%d/%m/%Y}) cae en el {periodo_tarea}"
                                                      if fecha_t else "")
                                if periodo_tarea != periodo_sel and not forzada:
                                    omitidas_periodo.append({"id": id_act_cr, "nombre": nom_t, "motivo": motivo_periodo})
                                    continue

                                p_max_t = float(t.get("maxPoints", 100.0))

                                rubro_final = None
                                if "gradeCategory" in t and isinstance(t["gradeCategory"], dict):
                                    rubro_final = str(t["gradeCategory"].get("name") or "").strip() or None
                                elif "gradeCategoryId" in t:
                                    rubro_final = mapa_cats_cr.get(str(t["gradeCategoryId"]))
                                tarea_sin_categoria = not rubro_final
                                if tarea_sin_categoria:
                                    # 🛡️ Antes se ponía "Trabajos y Tareas" fijo; si la clase lo escribe distinto
                                    # ("Trabajos y tareas"), nacía un rubro gemelo que duplicaba su porcentaje
                                    rubro_final = rubro_por_defecto

                                # 🛡️ FILTRO DE LABORATORIO (materias que no son de laboratorio)
                                # Se omite una tarea de laboratorio salvo que: la materia califique ese rubro
                                # (está en sus ponderaciones), su nombre esté en ACTIVIDADES_LAB_SIEMPRE_INCLUIDAS
                                # o el maestro la importe a mano desde el reporte.
                                # Antes bastaba con que el nombre contuviera "lab" (elaborar, colaborativo, sílabas…)
                                # y la lista de excepciones nunca se aplicaba.
                                lab_por_rubro, lab_por_nombre = _es_lab(rubro_final), _es_lab(nom_t)
                                if not es_materia_lab and not forzada and (lab_por_rubro or lab_por_nombre):
                                    rubro_calificado = lab_por_rubro and _normalizar(rubro_final) in rubros_norm
                                    en_excepciones = _normalizar(nom_t) in excepciones_norm
                                    if not (rubro_calificado or en_excepciones):
                                        motivo_lab = (f"su rubro «{rubro_final}» no está en las ponderaciones de esta materia"
                                                      if lab_por_rubro else "su nombre indica que es de laboratorio")
                                        omitidas_lab.append({"id": id_act_cr, "nombre": nom_t, "motivo": motivo_lab})
                                        continue

                                if tarea_sin_categoria:
                                    sin_categoria.append(nom_t)
                                elif rubro_final.strip() not in rubros_exactos:
                                    sin_peso.append(f"{nom_t} (rubro «{rubro_final}»)")

                                conn.execute(
                                    text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                            VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)
                                            ON CONFLICT ("ID_Actividad") DO UPDATE SET 
                                                "Nombre_Actividad" = EXCLUDED."Nombre_Actividad", 
                                                "Rubro" = EXCLUDED."Rubro", 
                                                "Puntos_Max" = EXCLUDED."Puntos_Max",
                                                "Clase" = EXCLUDED."Clase",
                                                "Periodo" = CASE WHEN :forzada THEN EXCLUDED."Periodo" ELSE "calif_actividades"."Periodo" END'''),
                                    {"id": id_act_cr, "c": clase_id, "p": periodo_sel, "nom": nom_t, "rub": rubro_final, "pmax": p_max_t, "fec": fecha_hoy, "forzada": forzada}
                                )
                                tareas_procesadas += 1

                                conn.execute(text('DELETE FROM "calif_notas" WHERE "ID_Actividad" = :id AND "Clase" = :c'), {"id": id_act_cr, "c": clase_id})

                                entregas = _classroom_get_todo(f"{base_cr}/courseWork/{t.get('id')}/studentSubmissions", headers_cr, "studentSubmissions")
                                for sub in entregas:
                                    if not isinstance(sub, dict): continue
                                    u_id = sub.get("userId")
                                    nom_alm = mapa_userid_a_nombre.get(u_id)
                                    nota_raw = sub.get("assignedGrade") if sub.get("assignedGrade") is not None else sub.get("draftGrade")

                                    if nom_alm and nota_raw is not None:
                                        conn.execute(
                                            text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                                    VALUES (:id, :c, :alm, :nota)
                                                    ON CONFLICT ("ID_Actividad", "Alumno") DO UPDATE SET "Nota" = EXCLUDED."Nota"'''),
                                            {"id": id_act_cr, "c": clase_id, "alm": nom_alm, "nota": float(nota_raw)}
                                        )
                                        total_notas += 1

                        # 🛡️ El resultado se guarda y se muestra después del rerun (antes desaparecía en 1.5 s)
                        return True, {
                            "curso": id_curso_objetivo, "clase": clase_id, "periodo": periodo_sel,
                            "tareas": tareas_procesadas, "notas": total_notas,
                            "omitidas_periodo": omitidas_periodo, "omitidas_lab": omitidas_lab,
                            "sin_peso": sin_peso, "sin_emparejar": sin_emparejar,
                            "sin_categoria": sin_categoria, "rubro_defecto": rubro_por_defecto,
                            "n": st.session_state.get("reporte_sync", {}).get("n", 0) + 1,
                        }

                    except Exception as e:
                        # 🛡️ Antes se mostraba el traceback completo al usuario
                        logging.exception("Error en sincronización con Classroom")
                        return False, f"🚨 No se pudo completar la sincronización: {e}"

                # Interfaz de botones
                if id_curso_auto:
                    if st.button("🔄 Sincronizar Tareas", type="secondary", use_container_width=True, help="El sistema detectó automáticamente tu clase."):
                        with st.spinner("Descargando avance de Classroom..."):
                            exito, resultado = ejecutar_sincronizacion(id_curso_auto)
                            if exito:
                                leer_datos.clear()
                                st.session_state["reporte_sync"] = resultado
                                st.rerun()
                            else:
                                st.error(resultado)
                else:
                    with st.popover("🔄 Sincronizar (Manual)", use_container_width=True):
                        if "error" in res_c:
                            st.error("🚨 Tu sesión de Classroom caducó (Límite 1 hora). Cierra sesión a la izquierda y vuelve a entrar.")
                        elif not cursos_cr:
                            st.info("ℹ️ Tu cuenta no es 'Profesor' de ningún curso activo en Classroom.")
                        else:
                            dict_cursos = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                            curso_seleccionado_label = st.selectbox("Curso en Classroom:", list(dict_cursos.keys()))
                        
                            if st.button("🚀 Iniciar Sincronización", type="primary", use_container_width=True):
                                id_manual = dict_cursos[curso_seleccionado_label]
                                with st.spinner("Descargando avance de Classroom..."):
                                    exito, resultado = ejecutar_sincronizacion(id_manual)
                                    if exito:
                                        leer_datos.clear()
                                        st.session_state["reporte_sync"] = resultado
                                        st.rerun()
                                    else:
                                        st.error(resultado)

        # --- BOTÓN 3 NUEVO: EDITAR ACTIVIDAD ---
        with col_btn_act3:
            with st.popover("✏️ Editar Tarea", use_container_width=True):
                st.markdown("### Modificar Actividad Existente")
                if mis_actividades.empty:
                    st.info("No hay actividades registradas en este periodo para editar.")
                else:
                    dict_acts_edit = {
                        f"{r['Nombre_Actividad']} ({r['Rubro']})": str(r['ID_Actividad']).strip()
                        for _, r in mis_actividades.iterrows()
                    }
                    act_a_editar_lbl = st.selectbox("Selecciona la actividad a modificar:", list(dict_acts_edit.keys()), key="sel_act_edit")
                    id_act_a_editar = dict_acts_edit[act_a_editar_lbl]
                
                    fila_act_edit = mis_actividades[mis_actividades['ID_Actividad'] == id_act_a_editar].iloc[0]
                
                    nuevo_nombre_act = st.text_input("Nombre de la Actividad:", value=str(fila_act_edit['Nombre_Actividad']), key="edit_nom_act")
                    rubro_actual = str(fila_act_edit['Rubro'])
                    idx_rubro_act = categorias_validas.index(rubro_actual) if rubro_actual in categorias_validas else 0
                    nuevo_rubro_act = st.selectbox("Categoría / Rubro:", categorias_validas, index=idx_rubro_act, key="edit_rub_act")
                    nuevos_puntos_max = st.number_input("Puntos Máximos:", min_value=10.0, max_value=100.0, value=float(fila_act_edit.get('Puntos_Max', 100.0)), step=10.0, key="edit_pts_act")
                
                    if st.button("💾 Guardar Cambios de la Actividad", type="primary", use_container_width=True):
                        with st.spinner("Actualizando en Supabase..."):
                            try:
                                with engine.begin() as conn:
                                    conn.execute(
                                        text('''UPDATE "calif_actividades" 
                                                SET "Nombre_Actividad" = :nom, "Rubro" = :rub, "Puntos_Max" = :pmax
                                                WHERE "ID_Actividad" = :id AND "Clase" = :c'''),
                                        {"nom": nuevo_nombre_act.strip(), "rub": nuevo_rubro_act, "pmax": nuevos_puntos_max, "id": id_act_a_editar, "c": clase_id}
                                    )
                                leer_datos.clear()
                                st.success("✅ Actividad y categoría actualizadas exitosamente.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e_upd_act:
                                st.error(f"Error al actualizar actividad: {e_upd_act}")

        # --- BOTÓN 4: ELIMINAR ACTIVIDAD ---
        with col_btn_act4:
            with st.popover("🗑️ Eliminar Tarea", use_container_width=True):
                st.markdown("### Eliminar Tarea o Examen")
                if mis_actividades.empty:
                    st.info("No hay actividades registradas en este periodo para eliminar.")
                else:
                    st.warning("⚠️ **Atención:** Se borrarán también todas las calificaciones asociadas a esta tarea en este grupo.")
                    dict_acts_del = {
                        f"{r['Nombre_Actividad']} ({r['Rubro']})": str(r['ID_Actividad']).strip()
                        for _, r in mis_actividades.iterrows()
                    }
                    act_a_borrar_lbl = st.selectbox("Actividad a eliminar:", list(dict_acts_del.keys()), key="sel_act_del")
                    id_act_a_borrar = dict_acts_del[act_a_borrar_lbl]
                
                    confirmar_borrado = st.checkbox("Confirmo que deseo borrarla", key="chk_conf_del_act")
                
                    if st.button("🗑️ Borrar Definitivamente", type="secondary", disabled=not confirmar_borrado, use_container_width=True):
                        with st.spinner("Eliminando de Supabase..."):
                            try:
                                with engine.begin() as conn:
                                    conn.execute(
                                        text('DELETE FROM "calif_notas" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                        {"id": id_act_a_borrar, "c": clase_id}
                                    )
                                    conn.execute(
                                        text('DELETE FROM "calif_actividades" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                        {"id": id_act_a_borrar, "c": clase_id}
                                    )
                                leer_datos.clear()
                                st.success(f"✅ Actividad eliminada exitosamente.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e_del:
                                st.error(f"Error al eliminar actividad: {e_del}")

        # =================================================================
        # 🔄 REPORTE DE LA ÚLTIMA SINCRONIZACIÓN CON CLASSROOM
        # =================================================================
        reporte = st.session_state.get("reporte_sync")
        if reporte and (reporte.get("clase"), reporte.get("periodo")) == (clase_id, periodo_sel):
            with st.container(border=True):
                c_rep, c_cerrar = st.columns([6, 1])
                c_rep.success(f"🔄 Classroom: se actualizaron {reporte['tareas']} tareas y {reporte['notas']} notas del {periodo_sel}.")
                if c_cerrar.button("Cerrar", key=f"cerrar_reporte_{reporte['n']}", use_container_width=True):
                    st.session_state.pop("reporte_sync", None)
                    st.rerun()

                if reporte["omitidas_lab"]:
                    st.markdown(f"**🧪 {len(reporte['omitidas_lab'])} tarea(s) de laboratorio no se importaron**")
                    _mostrar_lista([f"{x['nombre']}: {x['motivo']}" for x in reporte["omitidas_lab"]])
                if reporte["omitidas_periodo"]:
                    st.markdown(f"**📅 {len(reporte['omitidas_periodo'])} tarea(s) pertenecen a otro periodo**")
                    _mostrar_lista([f"{x['nombre']}: {x['motivo']}" if x["motivo"] else x["nombre"] for x in reporte["omitidas_periodo"]])

                omitidas = reporte["omitidas_lab"] + reporte["omitidas_periodo"]
                if omitidas and token_google:
                    opciones_forzar = {x["id"]: x["nombre"] for x in omitidas}
                    elegidas = st.multiselect(
                        f"Importar de todos modos en el {periodo_sel}:", list(opciones_forzar),
                        format_func=opciones_forzar.get, key=f"forzar_sync_{reporte['n']}",
                        help="Si una tarea ya estaba en otro periodo, se cambia a este.",
                    )
                    if st.button("📥 Importar las seleccionadas", disabled=not elegidas, key=f"btn_forzar_{reporte['n']}"):
                        with st.spinner("Importando de Classroom..."):
                            exito, resultado = ejecutar_sincronizacion(reporte["curso"], forzar=frozenset(elegidas))
                        if exito:
                            leer_datos.clear()
                            st.session_state["reporte_sync"] = resultado
                            st.rerun()
                        else:
                            st.error(resultado)

                if reporte.get("sin_categoria"):
                    st.markdown(f"**📂 {len(reporte['sin_categoria'])} tarea(s) no tienen categoría en Classroom**")
                    st.caption(f"La app las contó en «{reporte.get('rubro_defecto', 'Trabajos y Tareas')}», pero Classroom puede "
                               "calcular su promedio sin ellas. Asígnales una categoría en Classroom y vuelve a sincronizar "
                               "para que ambos las cuenten igual.")
                    _mostrar_lista(reporte["sin_categoria"])
                if reporte["sin_peso"]:
                    st.markdown(f"**⚖️ {len(reporte['sin_peso'])} tarea(s) tienen un rubro sin porcentaje en este periodo**")
                    st.caption("No cuentan en el promedio que ve el alumno. Agrega ese rubro en ⚙️ Modificar Criterios "
                               "o cambia la categoría de la tarea en Classroom para que coincida.")
                    _mostrar_lista(reporte["sin_peso"])
                if reporte["sin_emparejar"]:
                    st.markdown(f"**👤 {len(reporte['sin_emparejar'])} alumno(s) de Classroom no coinciden con la lista oficial**")
                    st.caption("Sus calificaciones no se importaron. Revisa cómo está escrito su nombre en Classroom.")
                    _mostrar_lista(reporte["sin_emparejar"])

        st.markdown("---")
    
        # =================================================================
        # 5. MATRIZ DE CALIFICACIONES (ESCALA 100) - SUPABASE
        # =================================================================
        if not alumnos_clase:
            st.warning(f"No hay alumnos registrados en la lista de '{grupo_limpio}'.")
            return
        
        if mis_actividades.empty:
            st.info("💡 Aún no hay actividades en este periodo. Crea una manual o sincroniza desde Google Classroom arriba.")
            return

        query_notas = text('SELECT * FROM "calif_notas" WHERE "Clase" = :c')
        mis_notas = pd.read_sql(query_notas, engine, params={"c": clase_id})

        datos_matriz = {"Alumno": alumnos_clase}
        actividades_cols = []
    
        for _, act in mis_actividades.iterrows():
            id_act = str(act['ID_Actividad']).strip()
            col_nombre = f"{act['Nombre_Actividad']} ({act['Rubro']})"
            p_max = float(act.get('Puntos_Max', 100.0))
            actividades_cols.append((id_act, col_nombre, act['Rubro'], p_max))
        
            notas_act = mis_notas[mis_notas['ID_Actividad'] == id_act] if not mis_notas.empty else pd.DataFrame()
            dicc_notas = dict(zip(notas_act['Alumno'].astype(str).str.strip(), pd.to_numeric(notas_act['Nota'], errors='coerce').fillna(0.0))) if not notas_act.empty else {}
        
            datos_matriz[col_nombre] = [float(dicc_notas.get(str(al).strip(), 0.0)) for al in alumnos_clase]

        df_editable = pd.DataFrame(datos_matriz)
    
        # 🧮 Mismo cálculo que la pestaña "Calificaciones Finales del Periodo"
        promedios_por_alumno = calcular_promedios_periodo(mis_actividades, mis_notas, alumnos_clase, rubros_pesos)
        promedios_calculados = [promedios_por_alumno[al] for al in alumnos_clase]

        df_editable['Promedio Periodo'] = [format_calif_100(p) for p in promedios_calculados]
    
        config_editor = {
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Promedio Periodo": st.column_config.TextColumn("Promedio Periodo (Base 100)", disabled=True)
        }
        for _, col_nom, _, p_max in actividades_cols:
            config_editor[col_nom] = st.column_config.NumberColumn(
                col_nom, min_value=0.0, max_value=float(p_max), step=1.0, format="%.1f", required=True
            )

        st.subheader("📝 Captura de Calificaciones (Base 100)")
        df_resultado = st.data_editor(
            df_editable,
            column_config=config_editor,
            use_container_width=True,
            hide_index=True,
            key=f"ed_calif_{clase_id}_{periodo_sel}"
        )

        col_save, col_dl = st.columns([1, 1])
        with col_save:
            if st.button("💾 Guardar Calificaciones Manuales", type="primary", use_container_width=True):
                with st.spinner("Guardando en Supabase..."):
                    try:
                        with engine.begin() as conn:
                            for _, r in df_resultado.iterrows():
                                al_nombre = str(r['Alumno']).strip()
                                for id_act, col_nom, _, _ in actividades_cols:
                                    nota_val = float(r.get(col_nom, 0.0))
                                    conn.execute(
                                        text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                                VALUES (:id, :c, :alm, :nota)
                                                ON CONFLICT ("ID_Actividad", "Alumno") DO UPDATE SET "Nota" = EXCLUDED."Nota"'''),
                                        {"id": id_act, "c": clase_id, "alm": al_nombre, "nota": nota_val}
                                    )
                        leer_datos.clear()
                        st.success("✅ Calificaciones guardadas exitosamente en Supabase.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e_grades:
                        st.error(f"Error al guardar notas: {e_grades}")
                
        with col_dl:
            csv_boleta = df_resultado.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 Descargar Boleta del Grupo (CSV)",
                data=csv_boleta,
                file_name=f"Calificaciones_{clase_id}_{periodo_sel}.csv",
                mime="text/csv",
                use_container_width=True
            )