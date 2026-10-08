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

def auto_emparejar_curso_classroom(cursos_cr, materia_app, grupo_app):
    """
    Busca automáticamente el ID del curso de Classroom cruzando la Materia y el Grupo,
    ignorando mayúsculas, acentos y espacios.
    """
    def norm_text(txt):
        import unicodedata
        t = str(txt).lower().strip().replace("°", "").replace(" ", "")
        return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')

    mat_app_norm = norm_text(materia_app)
    grp_app_norm = norm_text(grupo_app)

    for c in cursos_cr:
        nom_cr_norm = norm_text(c.get("name", ""))
        sec_cr_norm = norm_text(c.get("section", ""))
        
        # Si la materia está en el nombre del curso de Classroom, 
        # y el grupo está en la sección o en el mismo nombre... ¡ES MATCH!
        if mat_app_norm in nom_cr_norm and (grp_app_norm in sec_cr_norm or grp_app_norm in nom_cr_norm):
            return c["id"]
            
    return None # Si no logra emparejar automáticamente

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
    # 2. PONDERACIONES / CRITERIOS (CON AUTO-CARGA DESDE CLASSROOM)
    # =================================================================
    query_pond = text('SELECT * FROM "calif_ponderaciones" WHERE "Clase" = :c AND "Periodo" = :p')
    pond_actual = pd.read_sql(query_pond, engine, params={"c": clase_id, "p": periodo_sel})
        
    if pond_actual.empty:
        st.warning(f"⚠️ No has configurado los criterios de evaluación para **{clase_id}** en el **{periodo_sel}**.")
        
        # 🎓 OPCIÓN 1: CARGAR DIRECTO DE GOOGLE CLASSROOM (RECOMENDADA)
        token_google = st.session_state.get("access_token")
        if token_google:
            with st.container():
                st.markdown("##### 🚀 Opción Rápida: Importar desde Classroom")
                st.caption("Lee automáticamente los porcentajes que ya configuraste en los ajustes de Google Classroom.")
                
                try:
                    headers_cr = {"Authorization": f"Bearer {token_google}"}
                    res_c = requests.get("https://classroom.googleapis.com/v1/courses?teacherId=me&courseStates=ACTIVE", headers=headers_cr).json()
                    
                    if "error" in res_c:
                        st.warning("⚠️ Tu sesión con Google Classroom caducó por seguridad (1 hora límite).")
                        st.info("👉 Por favor, usa el botón '🔒 Cerrar Sesión' en el menú izquierdo y vuelve a entrar para renovar tu conexión.")
                    else:
                        cursos_cr = res_c.get("courses", [])
                        
                        if not cursos_cr:
                            st.info("ℹ️ Tu cuenta de Google no tiene cursos activos configurados como 'Profesor'.")
                        else:
                            # 🤖 AUTO-MATCHER INTELIGENTE PARA LOS CRITERIOS
                            def limpiar_texto(txt):
                                import unicodedata
                                if not txt: return ""
                                t = str(txt).lower().strip()
                                return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')

                            mat_clave = limpiar_texto(materia_sel.split()[0])
                            grp_num = ''.join(filter(str.isdigit, grupo_sel))
                            grp_letra = ''.join(filter(str.isalpha, grupo_sel)).lower()
                            
                            id_curso_auto = None
                            for c in cursos_cr:
                                nom_cr = limpiar_texto(c.get("name", ""))
                                sec_cr = limpiar_texto(c.get("section", ""))
                                texto_total = nom_cr + " " + sec_cr
                                if mat_clave in texto_total and grp_num in texto_total and grp_letra in texto_total:
                                    id_curso_auto = c["id"]
                                    break
                            
                            # Si hace match, preparamos la variable. Si no, mostramos la lista.
                            if id_curso_auto:
                                id_c_pond = id_curso_auto
                                btn_texto = "🎓 Cargar Criterios Oficiales (Detectado Automáticamente)"
                            else:
                                dict_c = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                                curso_elegido_pond = st.selectbox("Selecciona la clase correspondiente en Classroom:", list(dict_c.keys()), key="c_pond_cr")
                                id_c_pond = dict_c[curso_elegido_pond] # <-- ¡EL FIX DEL ERROR ESTÁ AQUÍ!
                                btn_texto = "🎓 Cargar Criterios del Curso Seleccionado"
                                
                            if st.button(btn_texto, type="primary", use_container_width=True, key="btn_cargar_criterios_cr_unico"):
                                with st.spinner("Descargando categorías y ponderaciones oficiales de Classroom..."):
                                    res_det = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_c_pond}", headers=headers_cr).json()
                                    
                                    if "error" in res_det:
                                        st.error(f"🚨 Google Classroom reportó: {res_det['error'].get('message', res_det['error'])}")
                                    else:
                                        # 🛡️ FIX: Leer las categorías exactamente igual que abajo
                                        cats = res_det.get("gradebookSettings", {}).get("gradeCategories", [])
                                        if not cats:
                                            cats = res_det.get("gradeCategories", [])
                                            
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
                                                    if cat_nom and cat_pct > 0:
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

# --- BOTÓN 2: SINCRONIZAR DE CLASSROOM (AUTOMATIZADO Y BLINDADO) ---
    with col_btn_act2:
        token_google = st.session_state.get("access_token")
        
        if not token_google:
            with st.popover("🔄 Sincronizar Classroom", use_container_width=True):
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
                st.link_button("🔑 Conectar con Google Classroom", url_cr, type="primary", use_container_width=True)
        else:
            # 🧠 CEREBRO DE SINCRONIZACIÓN (Empaquetado para evitar errores de indentación)
            def ejecutar_sincronizacion(id_curso_objetivo):
                try:
                    headers_cr = {"Authorization": f"Bearer {token_google}"}
                    res_curso_det = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_objetivo}", headers=headers_cr).json()
                    cats_cr = res_curso_det.get("gradebookSettings", {}).get("gradeCategories", [])
                    if not cats_cr:
                        cats_cr = res_curso_det.get("gradeCategories", [])
                        
                    mapa_cats_cr = {str(c["id"]): str(c.get("name", "Trabajos y Tareas")).strip() for c in cats_cr}

                    res_w = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_objetivo}/courseWork", headers=headers_cr).json()
                    tareas_cr = res_w.get("courseWork", [])
                    
                    df_alumnos_db = pd.read_sql('SELECT * FROM "alumnos"', engine)
                    df_alumnos_db.columns = df_alumnos_db.columns.str.strip()
                    col_correo_db = next((c for c in df_alumnos_db.columns if 'correo' in c.lower()), 'Correo')
                    mapa_email_a_oficial = {str(r.get(col_correo_db, '')).lower().strip(): str(r.get('Nombre Completo', '')).strip() for _, r in df_alumnos_db.iterrows()}

                    res_st = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_objetivo}/students", headers=headers_cr).json()
                    mapa_userid_a_nombre = {}
                    for s in res_st.get("students", []):
                        u_id = s.get("userId")
                        prof = s.get("profile", {})
                        email_cr = str(prof.get("emailAddress", "")).lower().strip()
                        nom_cr = str(prof.get("name", {}).get("fullName", "")).strip()
                        if email_cr in mapa_email_a_oficial:
                            mapa_userid_a_nombre[u_id] = mapa_email_a_oficial[email_cr]
                        else:
                            mapa_userid_a_nombre[u_id] = encontrar_alumno_oficial(nom_cr, alumnos_clase)

                    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                    total_notas = 0
                    
                    with engine.begin() as conn:
                        for t in tareas_cr:
                            if t.get("state") == "DELETED": continue
                                
                            id_act_cr = f"CR-{t['id']}"
                            nom_t = t.get("title", "Sin Título")
                            p_max_t = float(t.get("maxPoints", 100.0))
                            
                            rubro_final = "Trabajos y Tareas"
                            if "gradeCategory" in t and isinstance(t["gradeCategory"], dict):
                                rubro_final = str(t["gradeCategory"].get("name", "Trabajos y Tareas")).strip()
                            elif "gradeCategoryId" in t:
                                cat_id_t = str(t["gradeCategoryId"])
                                rubro_final = mapa_cats_cr.get(cat_id_t, "Trabajos y Tareas")
                                if "lab" not in materia_sel.lower() and "laboratorio" in rubro_final.lower():
                                    continue # Se salta esta tarea y no la descarga
                            
                            conn.execute(
                                text('''INSERT INTO "calif_actividades" ("ID_Actividad", "Clase", "Periodo", "Nombre_Actividad", "Rubro", "Puntos_Max", "Fecha_Creacion")
                                        VALUES (:id, :c, :p, :nom, :rub, :pmax, :fec)
                                        ON CONFLICT ("ID_Actividad") DO UPDATE SET 
                                            "Nombre_Actividad" = EXCLUDED."Nombre_Actividad", 
                                            "Rubro" = EXCLUDED."Rubro", 
                                            "Puntos_Max" = EXCLUDED."Puntos_Max"'''),
                                {"id": id_act_cr, "c": clase_id, "p": periodo_sel, "nom": nom_t, "rub": rubro_final, "pmax": p_max_t, "fec": fecha_hoy}
                            )
                            
                            conn.execute(text('DELETE FROM "calif_notas" WHERE "ID_Actividad" = :id AND "Clase" = :c'), {"id": id_act_cr, "c": clase_id})
                            
                            res_sub = requests.get(f"https://classroom.googleapis.com/v1/courses/{id_curso_objetivo}/courseWork/{t['id']}/studentSubmissions", headers=headers_cr).json()
                            for sub in res_sub.get("studentSubmissions", []):
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

                    return True, f"🎉 ¡Sincronización completa! Importadas {len(tareas_cr)} tareas y {total_notas} notas."
                except Exception as e:
                    return False, f"Error técnico: {e}"

            # 🤖 INTERFAZ Y AUTOMATIZACIÓN
            headers_cr = {"Authorization": f"Bearer {token_google}"}
            try:
                res_c = requests.get("https://classroom.googleapis.com/v1/courses?teacherId=me&courseStates=ACTIVE", headers=headers_cr).json()
                cursos_cr = res_c.get("courses", [])
                
                # Auto-matcher MÁS INTELIGENTE (Busca solo la 1ra palabra de la materia, ej. "Física")
                id_curso_auto = None
                
                # Función rápida para matar acentos y mayúsculas en ambos lados
                def limpiar_texto(txt):
                    import unicodedata
                    if not txt: return ""
                    t = str(txt).lower().strip()
                    return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')

                mat_clave = limpiar_texto(materia_sel.split()[0]) # Ej. "fisica"
                grp_num = ''.join(filter(str.isdigit, grupo_sel)) # Ej. "4"
                grp_letra = ''.join(filter(str.isalpha, grupo_sel)).lower() # Ej. "b"
                
                for c in cursos_cr:
                    nom_cr = limpiar_texto(c.get("name", ""))
                    sec_cr = limpiar_texto(c.get("section", ""))
                    texto_total = nom_cr + " " + sec_cr
                    
                    # Ahora sí comparamos peras con peras (sin acentos)
                    if mat_clave in texto_total and grp_num in texto_total and grp_letra in texto_total:
                        id_curso_auto = c["id"]
                        break

                if id_curso_auto:
                    # ✅ MATCH AUTOMÁTICO ENCONTRADO
                    if st.button("🔄 Sincronizar Classroom", type="secondary", use_container_width=True, help="El sistema detectó automáticamente tu clase."):
                        with st.spinner("Descargando de Classroom..."):
                            exito, msg = ejecutar_sincronizacion(id_curso_auto)
                            if exito:
                                leer_datos.clear()
                                st.success(msg)
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    # ⚠️ NO HUBO MATCH, MOSTRAMOS SELECTOR MANUAL
                    with st.popover("🔄 Sincronizar (Manual)", use_container_width=True):
                        st.info("No pudimos detectar tu curso automáticamente. Por favor selecciónalo:")
                        dict_cursos = {f"{c['name']} ({c.get('section', 'General')})": c['id'] for c in cursos_cr}
                        curso_seleccionado_label = st.selectbox("Curso en Classroom:", list(dict_cursos.keys()))
                        
                        if st.button("🚀 Iniciar Sincronización", type="primary", use_container_width=True):
                            id_manual = dict_cursos[curso_seleccionado_label]
                            with st.spinner("Descargando de Classroom..."):
                                exito, msg = ejecutar_sincronizacion(id_manual)
                                if exito:
                                    leer_datos.clear()
                                    st.success(msg)
                                    time.sleep(1.5)
                                    st.rerun()
                                else:
                                    st.error(msg)

            except Exception as e_cr_general:
                st.error(f"Error al leer Classroom: {e_cr_general}")

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
        
        # Mapeo limpio con respaldo del normalizador
        datos_matriz[col_nombre] = [float(dicc_notas.get(str(al).strip(), 0.0)) for al in alumnos_clase]

    df_editable = pd.DataFrame(datos_matriz)
    
    # Cálculo proporcional en base 100
    # 🧮 CÁLCULO PROPORCIONAL TOLERANTE (RESUELVE EL 0.0)
    rubros_pesos_norm = {str(k).lower().strip(): float(v) for k, v in rubros_pesos.items()}

    def obtener_peso_rubro_flexible(r_nombre):
        r_c = str(r_nombre).lower().strip()
        # 1. Coincidencia directa
        if r_c in rubros_pesos_norm:
            return rubros_pesos_norm[r_c]
        # 2. Coincidencia parcial (ej. si uno dice 'Trabajos' y el otro 'Trabajos de 100')
        for k, w in rubros_pesos_norm.items():
            if k in r_c or r_c in k:
                return w
        # 3. Fallback: si no coincide, toma el peso del primer rubro disponible
        return list(rubros_pesos_norm.values())[0] if rubros_pesos_norm else 100.0

    rubros_con_tareas = list(set([r for _, _, r, _ in actividades_cols]))
    peso_total_evaluado = sum(obtener_peso_rubro_flexible(r) for r in rubros_con_tareas)

    promedios_calculados = []
    for idx, row in df_editable.iterrows():
        desglose_por_rubro = {r: [] for r in rubros_con_tareas}
        
        for id_act, col_nom, rubro, p_max in actividades_cols:
            val_nota = float(row.get(col_nom, 0.0))
            nota_base_100 = (val_nota / p_max) * 100.0 if p_max > 0 else 0.0
            desglose_por_rubro[rubro].append(nota_base_100)
            
        puntos_acumulados = 0.0
        for rubro, lista_notas in desglose_por_rubro.items():
            pct_rubro = obtener_peso_rubro_flexible(rubro)
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