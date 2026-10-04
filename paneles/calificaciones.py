# paneles/calificaciones.py
import streamlit as st
import pandas as pd
import uuid
import time
import requests
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_CALIFICACIONES, 
    PERIODOS_LECTIVOS, 
    SUPER_USUARIOS_WHITELIST
)
from database import (
    leer_datos, 
    obtener_lista_alumnos, 
    leer_todas_las_asignaciones,
    obtener_engine_sql
)

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

def renderizar_panel_calificaciones(gc, usuario, nombre_prof):
    st.header(f"📊 Calificador Académico: {nombre_prof}")
    
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
    periodos_disponibles = [p["nombre"] for p in PERIODOS_LECTIVOS.get(nivel_key, [])]
    periodo_sel = c3.selectbox("Periodo de Evaluación:", periodos_disponibles, key="calif_per")
    
    clase_id = f"{materia_sel} - {grupo_sel}"
    
    # 2. Cargar lista oficial de alumnos de este salón desde el inicio
    try:
        grupo_limpio = grupo_sel.split("(")[0].strip()
        alumnos_clase = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
    except Exception:
        alumnos_clase = []
        
    st.markdown("---")
    
    # =================================================================
    # 2. PONDERACIONES / CRITERIOS
    # =================================================================
    df_pond_todas = leer_datos(gc, FILE_CALIFICACIONES, "Ponderaciones")
    if not df_pond_todas.empty:
        df_pond_todas.columns = df_pond_todas.columns.str.strip()
        
    if not df_pond_todas.empty and 'Clase' in df_pond_todas.columns and 'Rubro' in df_pond_todas.columns:
        df_pond_todas['Clase'] = df_pond_todas['Clase'].astype(str).str.strip()
        df_pond_todas['Periodo'] = df_pond_todas['Periodo'].astype(str).str.strip()
        pond_actual = df_pond_todas[(df_pond_todas['Clase'] == clase_id) & (df_pond_todas['Periodo'] == periodo_sel)]
    else:
        pond_actual = pd.DataFrame()
        
    if pond_actual.empty:
        st.warning(f"⚠️ No has configurado los criterios de evaluación para **{clase_id}** en el **{periodo_sel}**.")
        
        # Opción A: Clonar del periodo anterior
        idx_actual = periodos_disponibles.index(periodo_sel) if periodo_sel in periodos_disponibles else 0
        if idx_actual > 0 and not df_pond_todas.empty and 'Clase' in df_pond_todas.columns:
            periodo_anterior = periodos_disponibles[idx_actual - 1]
            pond_ant = df_pond_todas[(df_pond_todas['Clase'] == clase_id) & (df_pond_todas['Periodo'] == periodo_anterior)]
            if not pond_ant.empty:
                if st.button(f"📋 Copiar ponderaciones del {periodo_anterior}", type="secondary"):
                    with st.spinner("Clonando criterios en Supabase..."):
                        with engine.begin() as conn:
                            for t in tareas_cr:
                                id_act_cr = f"CR-{t['id']}"
                                nom_t = t.get("title", "Sin Título")
                                p_max_t = float(t.get("maxPoints", 100.0))
                                
                                # Categoría inteligente
                                cat_id_t = t.get("gradeCategoryId")
                                rubro_detectado = mapa_cats_cr.get(cat_id_t, "Tareas y Trabajos")
                                
                                rubro_final = categorias_validas[0]
                                for c_val in categorias_validas:
                                    if any(w in c_val.lower() for w in rubro_detectado.lower().split()):
                                        rubro_final = c_val
                                        break
                                
                                # 1. Guardar o actualizar la actividad
                                conn.execute(
                                    text('DELETE FROM "calif_actividades" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                    {"id": id_act_cr, "c": clase_id}
                                )
                                conn.execute(
                                    text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                            VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)'''),
                                    {"id": id_act_cr, "c": clase_id, "p": periodo_sel, "nom": nom_t, "rub": rubro_final, "pmax": p_max_t, "fec": fecha_hoy}
                                )
                                
                                # 2. Descargar Notas de cada Alumno
                                res_sub = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/courseWork/{t['id']}/studentSubmissions", headers=headers_cr).json()
                                
                                # Limpiamos notas viejas de esta actividad en esta clase
                                conn.execute(
                                    text('DELETE FROM "calif_notas" WHERE "ID_Actividad" = :id AND "Clase" = :c'),
                                    {"id": id_act_cr, "c": clase_id}
                                )
                                
                                for sub in res_sub.get("studentSubmissions", []):
                                    u_id = sub.get("userId")
                                    nom_alm = mapa_userid_a_nombre.get(u_id)
                                    
                                    nota_asignada = sub.get("assignedGrade")
                                    if nota_asignada is None:
                                        nota_asignada = sub.get("draftGrade")
                                    
                                    # 🛡️ INSERCIÓN LIMPIA EN SUPABASE (SIN ON CONFLICT)
                                    if nom_alm and nota_asignada is not None:
                                        conn.execute(
                                            text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                                    VALUES (:id, :c, :alm, :nota)'''),
                                            {"id": id_act_cr, "c": clase_id, "alm": nom_alm, "nota": float(nota_asignada)}
                                        )
                                        total_notas_descargadas += 1

        st.markdown("##### 📝 Define tus Criterios de Evaluación")
        criterios_base = pd.DataFrame([
            {"Categoría / Rubro": "Tareas y Trabajos", "Porcentaje (%)": 50},
            {"Categoría / Rubro": "Exámenes", "Porcentaje (%)": 30},
            {"Categoría / Rubro": "Proyectos e Investigación", "Porcentaje (%)": 20}
        ])
        
        df_criterios_edit = st.data_editor(
            criterios_base,
            num_rows="dynamic",
            column_config={
                "Categoría / Rubro": st.column_config.TextColumn("Categoría / Rubro", required=True),
                "Porcentaje (%)": st.column_config.NumberColumn("Porcentaje (%)", min_value=1, max_value=100, step=5, required=True)
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
                st.success(f"Suma total: **{suma_porcentajes}%** ✅ (Listo para guardar)")
            else:
                st.error(f"Suma total: **{suma_porcentajes}%** ❌ (Debe dar 100%)")
                
        with c_save_btn:
            if st.button("💾 Guardar Criterios de Evaluación", type="primary", use_container_width=True):
                if suma_porcentajes != 100:
                    st.error("🚨 La suma debe ser exactamente 100%.")
                elif not clases_destino_pond:
                    st.error("🚨 Selecciona al menos una clase.")
                else:
                    with st.spinner("Guardando en Supabase..."):
                        try:
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
                            st.success(f"✅ Criterios guardados para {len(clases_destino_pond)} clase(s).")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_p:
                            st.error(f"Error al guardar: {e_p}")
        st.stop()
        
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
    # 3. ACCIONES DE ACTIVIDADES: CREAR, SINCRONIZAR, EDITAR Y ELIMINAR
    # =================================================================
    df_act_todas = leer_datos(gc, FILE_CALIFICACIONES, "Actividades")
    if not df_act_todas.empty and 'Clase' in df_act_todas.columns:
        df_act_todas['Clase'] = df_act_todas['Clase'].astype(str).str.strip()
        df_act_todas['Periodo'] = df_act_todas['Periodo'].astype(str).str.strip()
        mis_actividades = df_act_todas[(df_act_todas['Clase'] == clase_id) & (df_act_todas['Periodo'] == periodo_sel)]
    else:
        mis_actividades = pd.DataFrame()

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

    # --- BOTÓN 2: SINCRONIZAR DE CLASSROOM CON EMPAREJADOR INTELIGENTE ---
    with col_btn_act2:
        with st.popover("🔄 Sincronizar Classroom", use_container_width=True):
            st.markdown("### 🎓 Conexión con Google Classroom")
            token_google = st.session_state.get("access_token")
            
            if not token_google:
                st.warning("⚠️ No se detectó sesión de Classroom. Vincula tu cuenta institucional:")
                client_id_cr = st.secrets["auth"]["google_client_id"]
                redirect_uri_cr = st.secrets["auth"]["redirect_uri"]
                params_cr = {
                    "client_id": client_id_cr,
                    "redirect_uri": redirect_uri_cr,
                    "response_type": "code",
                    "scope": "openid email profile https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.students.readonly",
                    "access_type": "online",
                    "prompt": "consent"
                }
                import urllib.parse
                url_cr = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params_cr)}"
                st.link_button("🔑 Conectar con Google Classroom", url_cr, type="primary", use_container_width=True)
            else:
                try:
                    headers_cr = {"Authorization": f"Bearer {token_google}"}
                    res_c = requests.get("https://classroom.googleapis.com/v1/courses?teacherId=me&courseStates=ACTIVE", headers=headers_cr).json()
                    cursos_cr = res_c.get("courses", [])
                    
                    if not cursos_cr:
                        st.info("No se encontraron cursos activos en Google Classroom.")
                    else:
                        dict_cursos = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                        curso_seleccionado_label = st.selectbox("Selecciona el curso en Classroom:", list(dict_cursos.keys()))
                        id_curso_elegido = dict_cursos[curso_seleccionado_label]
                        
                        if st.button("🚀 Sincronizar Tareas y Calificaciones", type="primary", use_container_width=True):
                            with st.spinner("Descargando tareas y calificaciones reales..."):
                                # Categorías de Classroom
                                res_curso_det = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}", headers=headers_cr).json()
                                cats_cr = res_curso_det.get("gradeCategories", [])
                                mapa_cats_cr = {c["id"]: c.get("name", "Tareas y Trabajos") for c in cats_cr}

                                # Tareas
                                res_w = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/courseWork", headers=headers_cr).json()
                                tareas_cr = res_w.get("courseWork", [])
                                
                                if not tareas_cr:
                                    st.warning("Ese curso en Classroom no tiene tareas creadas.")
                                else:
                                    # Alumnos de Classroom
                                    res_st = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/students", headers=headers_cr).json()
                                    mapa_userid_a_nombre = {}
                                    
                                    for s in res_st.get("students", []):
                                        u_id = s.get("userId")
                                        prof = s.get("profile", {})
                                        nombre_cr = str(prof.get("name", {}).get("fullName", "")).strip()
                                        
                                        # 🛡️ EMPAREJAMIENTO DE NOMBRE (Nombre Apellido <-> Apellido Nombre)
                                        nombre_oficial_resuelto = encontrar_alumno_oficial(nombre_cr, alumnos_clase)
                                        mapa_userid_a_nombre[u_id] = nombre_oficial_resuelto
                                    
                                    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                                    total_notas_descargadas = 0
                                    
                                    with engine.begin() as conn:
                                        for t in tareas_cr:
                                            id_act_cr = f"CR-{t['id']}"
                                            nom_t = t.get("title", "Sin Título")
                                            p_max_t = float(t.get("maxPoints", 100.0))
                                            
                                            # Categoría inteligente obligada a pertenecer a las categorías válidas
                                            cat_id_t = t.get("gradeCategoryId")
                                            rubro_detectado = mapa_cats_cr.get(cat_id_t, "Tareas y Trabajos")
                                            
                                            rubro_final = categorias_validas[0]
                                            for c_val in categorias_validas:
                                                if any(w in c_val.lower() for w in rubro_detectado.lower().split()):
                                                    rubro_final = c_val
                                                    break
                                            
                                            conn.execute(
                                                text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                                        VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)
                                                        ON CONFLICT ("ID_Actividad") DO UPDATE SET "Nombre_Actividad" = EXCLUDED."Nombre_Actividad", "Rubro" = EXCLUDED."Rubro", "Puntos_Max" = EXCLUDED."Puntos_Max"'''),
                                                {"id": id_act_cr, "c": clase_id, "p": periodo_sel, "nom": nom_t, "rub": rubro_final, "pmax": p_max_t, "fec": fecha_hoy}
                                            )
                                            
                                            # Notas (Borradores y Oficiales)
                                            res_sub = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_elegido}/courseWork/{t['id']}/studentSubmissions", headers=headers_cr).json()
                                            for sub in res_sub.get("studentSubmissions", []):
                                                u_id = sub.get("userId")
                                                nom_alm = mapa_userid_a_nombre.get(u_id)
                                                
                                                nota_asignada = sub.get("assignedGrade")
                                                if nota_asignada is None:
                                                    nota_asignada = sub.get("draftGrade")
                                                
                                                if nom_alm and nota_asignada is not None:
                                                    conn.execute(
                                                        text('''INSERT INTO "calif_notas" ("ID_Actividad", "Clase", "Alumno", "Nota")
                                                                VALUES (:id, :c, :alm, :nota)
                                                                ON CONFLICT ("ID_Actividad", "Alumno") DO UPDATE SET "Nota" = EXCLUDED."Nota"'''),
                                                        {"id": id_act_cr, "c": clase_id, "alm": nom_alm, "nota": float(nota_asignada)}
                                                    )
                                                    total_notas_descargadas += 1
                                                    
                                    leer_datos.clear()
                                    st.success(f"🎉 ¡Éxito! Se importaron {len(tareas_cr)} tareas y {total_notas_descargadas} calificaciones.")
                                    time.sleep(1)
                                    st.rerun()
                except Exception as e_cr:
                    st.error(f"Error con Classroom: {e_cr}")

    # --- ✅ BOTÓN 3 NUEVO: EDITAR ACTIVIDAD (CAMBIAR CATEGORÍA, NOMBRE O PUNTOS) ---
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
                
                # Permite cambiar de categoría fácilmente
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
                st.warning("⚠️ **Atención:** Se borrarán también todas las calificaciones asociadas.")
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

    st.markdown("---")
    
    # =================================================================
    # 4. MATRIZ DE CALIFICACIONES (ESCALA 100)
    # =================================================================
    if not alumnos_clase:
        st.warning(f"No hay alumnos registrados en la lista de '{grupo_limpio}'.")
        return
        
    if mis_actividades.empty:
        st.info("💡 Aún no hay actividades en este periodo. Crea una manual o sincroniza desde Google Classroom arriba.")
        return

    df_notas_todas = leer_datos(gc, FILE_CALIFICACIONES, "Calificaciones")
    if not df_notas_todas.empty and 'Clase' in df_notas_todas.columns:
        df_notas_todas['Clase'] = df_notas_todas['Clase'].astype(str).str.strip()
        mis_notas = df_notas_todas[df_notas_todas['Clase'] == clase_id]
    else:
        mis_notas = pd.DataFrame()

    datos_matriz = {"Alumno": alumnos_clase}
    actividades_cols = []
    
    for _, act in mis_actividades.iterrows():
        id_act = str(act['ID_Actividad']).strip()
        col_nombre = f"{act['Nombre_Actividad']} ({act['Rubro']})"
        p_max = float(act.get('Puntos_Max', 100.0))
        actividades_cols.append((id_act, col_nombre, act['Rubro'], p_max))
        
        notas_act = mis_notas[mis_notas['ID_Actividad'] == id_act] if not mis_notas.empty else pd.DataFrame()
        dicc_notas = dict(zip(notas_act['Alumno'].astype(str).str.strip(), pd.to_numeric(notas_act['Nota'], errors='coerce').fillna(0.0))) if not notas_act.empty else {}
        
        # Mapeo limpio con respaldo del normalizador
        datos_matriz[col_nombre] = [float(dicc_notas.get(str(al).strip(), 0.0)) for al in alumnos_clase]

    df_editable = pd.DataFrame(datos_matriz)
    
    # Cálculo proporcional en base 100
    rubros_con_tareas = list(set([r for _, _, r, _ in actividades_cols]))
    peso_total_evaluado = sum(float(rubros_pesos.get(r, 0.0)) for r in rubros_con_tareas)
    
    promedios_calculados = []
    for idx, row in df_editable.iterrows():
        desglose_por_rubro = {r: [] for r in rubros_con_tareas}
        
        for id_act, col_nom, rubro, p_max in actividades_cols:
            val_nota = float(row.get(col_nom, 0.0))
            nota_base_100 = (val_nota / p_max) * 100.0 if p_max > 0 else 0.0
            desglose_por_rubro[rubro].append(nota_base_100)
            
        puntos_acumulados = 0.0
        for rubro, lista_notas in desglose_por_rubro.items():
            pct_rubro = float(rubros_pesos.get(rubro, 0.0))
            prom_rubro = (sum(lista_notas) / len(lista_notas)) if lista_notas else 0.0
            puntos_acumulados += (prom_rubro * (pct_rubro / 100.0))
            
        if peso_total_evaluado > 0:
            promedio_periodo_alumno = (puntos_acumulados / (peso_total_evaluado / 100.0))
        else:
            promedio_periodo_alumno = 0.0
            
        promedios_calculados.append(round(promedio_periodo_alumno, 1))

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
        if st.button("💾 Guardar Calificaciones", type="primary", use_container_width=True):
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