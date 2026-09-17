# paneles/docente.py
import streamlit as st
import pandas as pd
import json
import time
import gspread
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import google.generativeai as genai

from config import (
    FILE_ALUMNOS, 
    FILE_ASIGNACIONES, 
    FILE_REGISTROS, 
    FILE_ASISTENCIA,
    CATALOGO_SANCIONES, 
    SUPER_USUARIOS_WHITELIST
)
from database import (
    leer_datos, 
    leer_todos_los_registros, 
    obtener_lista_alumnos, 
    obtener_dataframe_alumnos,
    leer_todas_las_asignaciones
)
from paneles.analitica import mostrar_tablero_analitico

st.markdown("""
    <style>
    div[data-baseweb="select"] > div {
        white-space: normal !important;
        word-wrap: break-word !important;
    }
    ul[role="listbox"] li {
        white-space: normal !important;
        word-wrap: break-word !important;
        height: auto !important;
        padding-top: 10px !important;
        padding-bottom: 10px !important;
    }
    </style>
""", unsafe_allow_html=True)

def renderizar_panel_docente(gc, usuario, nombre_prof):
    
    def obtener_materia_teorica(nombre_materia):
        diccionario_fusion = {
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
            "lab química iv a ii": "Química IV A II"
        }
        limpio = str(nombre_materia).lower().strip().replace("  ", " ")
        return diccionario_fusion.get(limpio, str(nombre_materia).strip())

    st.header(f"🛡️ Panel Docente: {nombre_prof}")
    
    if "form_reset" not in st.session_state:
        st.session_state["form_reset"] = 0
    if "ia_closed_state" not in st.session_state:
        st.session_state["ia_closed_state"] = 0
        
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST

    # 🛡️ CARGA GLOBAL DE ASIGNACIONES 
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if not df_asig.empty and 'Usuario_Profesor' in df_asig.columns:
        df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
        df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
        df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
        if es_superusuario:
            mis_asig = df_asig.copy()
            st.info("👑 Modo Super Usuario: Acceso completo a grupos y materias.")
        else:
            mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    else:
        mis_asig = pd.DataFrame()
        
    # =================================================================
    # 🎛️ SUB-MENÚ EN BARRA LATERAL
    # ==========================================
    # Al declarar esto aquí, se colocará automáticamente en el panel izquierdo
    sub_modulo_docente = st.sidebar.radio(
        "Acción de Conducta:",
        ["➕ Nuevo Reporte", "✏️ Editar / Eliminar Reporte"]
    )
    
    # =================================================================
    # VISTA 1: NUEVO REPORTE
    # =================================================================
    if sub_modulo_docente == "➕ Nuevo Reporte":
        
        with st.container():
            st.subheader("📝 Registrar Nueva Incidencia")
            
            fecha_incidencia = st.date_input(
                "📅 Fecha en la que ocurrió la incidencia:", 
                value=datetime.now(ZoneInfo("America/Mexico_City")).date(),
                key=f"fecha_inc_{st.session_state.form_reset}"
            )
            
            reporte_pasillo = st.checkbox("🚨 ¿Es un reporte de pasillo / fuera de clase?", key=f"pasillo_{st.session_state.form_reset}")
            st.markdown("---")
            
            materia = "Pasillo / Inst. General"
            grupo_final = []
            alumnos_final = ["General (Ver observaciones)"] 
            
            if reporte_pasillo:
                c1, c2, c3 = st.columns(3)
                nivel = c1.selectbox("Nivel:", ["Secundaria", "Preparatoria"], key=f"niv_{st.session_state.form_reset}")
                opciones_grados = ["1°", "2°", "3°"] if nivel == "Secundaria" else ["4°", "5°", "6°"]
                
                grados_sel = c2.multiselect("Grado(s):", opciones_grados, key=f"grad_{st.session_state.form_reset}")
                
                grupos_disponibles = []
                
                if not df_asig.empty and 'Grupo' in df_asig.columns:
                    todos_los_grupos = df_asig['Grupo'].dropna().unique().tolist()
                    if grados_sel:
                        for grad_individual in grados_sel:
                            numero_grado = grad_individual.replace("°", "") 
                            grupos_del_grado = [g for g in todos_los_grupos if g.startswith(f"{numero_grado}°")]
                            grupos_disponibles.extend(grupos_del_grado)
                        grupos_disponibles = sorted(list(set(grupos_disponibles)))
                else:
                    if grados_sel:
                        for grad_individual in grados_sel:
                            grupos_disponibles.extend([f"{grad_individual}A", f"{grad_individual}B"])
                        grupos_disponibles = sorted(grupos_disponibles)
                
                grupos_sel = c3.multiselect("Grupo(s) implicado(s):", grupos_disponibles, key=f"grups_p_{st.session_state.form_reset}")
                grupo_final = grupos_sel
                
                alumnos_por_grupo_seleccionados = []
                if grupos_sel:
                    st.markdown("**Selecciona a los alumnos involucrados por salón:**")
                    pestanas = st.tabs(grupos_sel) 
                    
                    for idx, g_sel in enumerate(grupos_sel):
                        with pestanas[idx]:
                            try:
                                lista_grupo = obtener_lista_alumnos(gc, FILE_ALUMNOS, g_sel.strip())
                                if lista_grupo:
                                    sel_alumnos = st.multiselect(
                                        f"Implicados de {g_sel}:", 
                                        lista_grupo, 
                                        key=f"al_{g_sel}_{st.session_state.form_reset}"
                                    )
                                    if sel_alumnos:
                                        for nombre in sel_alumnos:
                                            alumnos_por_grupo_seleccionados.append((g_sel, nombre))
                                else:
                                    st.warning(f"⚠️ No hay alumnos listos en {g_sel}")
                            except Exception:
                                st.warning(f"⚠️ No se encontró la base de datos para {g_sel}")
                    
                    if alumnos_por_grupo_seleccionados:
                        alumnos_final = [nombre for _, nombre in alumnos_por_grupo_seleccionados]
    
            else:
                if mis_asig.empty: 
                    st.warning("⚠️ Sin materias asignadas para tu usuario actual.")
                    st.stop()            
    
                niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
                if len(niveles_prof) > 1:
                    nivel_elegido = st.radio("Sección:", niveles_prof, horizontal=True, key=f"nav_niv_{st.session_state.form_reset}")
                    mis_asig_vista = mis_asig[mis_asig['Nivel'] == nivel_elegido]
                else:
                    mis_asig_vista = mis_asig.copy()
    
                hoy_cdmx = datetime.now(ZoneInfo("America/Mexico_City"))
                dia_semana_map = {0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves", 4: "Viernes"}
                nombre_dia_hoy = dia_semana_map.get(hoy_cdmx.weekday(), "Fin de semana")
    
                ver_todas = st.toggle("🔓 Mostrar todas las materias (Fuera del horario de hoy)", key=f"tog_mat_{st.session_state.form_reset}")
                
                mis_asig_filtradas = mis_asig_vista.copy()
                if not ver_todas and not es_superusuario and hoy_cdmx.weekday() in dia_semana_map:
                    try:
                        df_conf = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
                        if not df_conf.empty and 'Clase' in df_conf.columns and nombre_dia_hoy in df_conf.columns:
                            clases_hoy = df_conf[pd.to_numeric(df_conf[nombre_dia_hoy], errors='coerce').fillna(0) > 0]['Clase'].tolist()
                            materias_validas = []
                            for _, r in mis_asig_vista.iterrows():
                                tag = f"{obtener_materia_teorica(r['Materia'])} - {r['Grupo']}"
                                if tag in clases_hoy or tag not in df_conf['Clase'].values:
                                    materias_validas.append(r['Materia'])
                            if materias_validas:
                                mis_asig_filtradas = mis_asig_vista[mis_asig_vista['Materia'].isin(materias_validas)]
                    except Exception:
                        pass
                           
                c1, c2 = st.columns(2)
                materia = c1.selectbox("Materia:", mis_asig_filtradas['Materia'].unique(), key=f"mat_select_{st.session_state.form_reset}")
                grupo = c2.selectbox("Grupo:", mis_asig_filtradas[mis_asig_filtradas['Materia'] == materia]['Grupo'].unique(), key=f"grup_select_{st.session_state.form_reset}")
                grupo_final = [grupo]
                
                captura_multiple = st.checkbox("Habilitar registro múltiple", key=f"check_mult_{st.session_state.form_reset}")
                
                try:
                    grupo_base = grupo.split("(")[0].strip()
                    df_alumnos_crudo = obtener_dataframe_alumnos(gc, FILE_ALUMNOS, grupo_base)
    
                    if df_alumnos_crudo is not None and not df_alumnos_crudo.empty:
                        if 'Área' in df_alumnos_crudo.columns:
                            texto_busqueda = f"{obtener_materia_teorica(materia)} {grupo}".upper()
                            if "ÁREA 1" in texto_busqueda or "ÁREA I" in texto_busqueda:
                                df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'].astype(str).str.upper().str.contains('1|I|CIENCIAS', na=False)]
                            elif "ÁREA 2" in texto_busqueda or "ÁREA II" in texto_busqueda:
                                df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'].astype(str).str.upper().str.contains('2|II', na=False)]
                            elif "ÁREA 3" in texto_busqueda or "ÁREA III" in texto_busqueda:
                                df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'].astype(str).str.upper().str.contains('3|III|HUMANIDADES', na=False)]
                            elif "ÁREA 4" in texto_busqueda or "ÁREA IV" in texto_busqueda:
                                df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo['Área'].astype(str).str.upper().str.contains('4|IV', na=False)]
    
                        if 'Nombre Completo' not in df_alumnos_crudo.columns:
                            col_pat = next((c for c in df_alumnos_crudo.columns if 'patern' in str(c).lower()), None)
                            col_mat = next((c for c in df_alumnos_crudo.columns if 'matern' in str(c).lower()), None)
                            col_nom = next((c for c in df_alumnos_crudo.columns if 'nombre' in str(c).lower()), None)
    
                            s_pat = df_alumnos_crudo[col_pat].astype(str).fillna('') if col_pat else ''
                            s_mat = df_alumnos_crudo[col_mat].astype(str).fillna('') if col_mat else ''
                            s_nom = df_alumnos_crudo[col_nom].astype(str).fillna('') if col_nom else ''
    
                            df_alumnos_crudo['Nombre Completo'] = (s_pat + " " + s_mat + " " + s_nom).str.strip().replace(r'\s+', ' ', regex=True)
                            df_alumnos_crudo['Nombre Completo'] = df_alumnos_crudo['Nombre Completo'].replace(r'^nan nan nan$|^nan$|^$', pd.NA, regex=True)
    
                        nombres_finales = df_alumnos_crudo['Nombre Completo'].dropna()
                        opc = sorted(nombres_finales.unique().tolist())
                    else:
                        opc = []
    
                    if not opc:
                        st.warning(f"La pestaña '{grupo_base}' no tiene alumnos registrados para esta especialidad.")
                        with st.expander("🔍 Ver datos crudos (Solo Diagnóstico)"):
                            st.write("Columnas detectadas:", df_alumnos_crudo.columns.tolist() if df_alumnos_crudo is not None else "Ninguna")
                            if df_alumnos_crudo is not None:
                                st.dataframe(df_alumnos_crudo.head(3))
                                
                except Exception as e:
                  opc = []
                  st.error(f"Error al procesar la pestaña '{grupo_base}': {e}")
                    
                if not captura_multiple:
                    alumnos_sel_raw = st.selectbox("Alumno:", ["Seleccione..."] + opc, key=f"indiv_{st.session_state.form_reset}")
                    alumnos_final = [alumnos_sel_raw] if alumnos_sel_raw != "Seleccione..." else []
                else:
                    alumnos_final = st.multiselect("Alumnos:", opc, key=f"grup_{st.session_state.form_reset}")
    
            st.markdown("---")
            
            key_cat_recomendada = f"ia_cat_{st.session_state.form_reset}"
            key_fal_recomendada = f"ia_fal_{st.session_state.form_reset}"
    
            if key_cat_recomendada not in st.session_state:
                st.session_state[key_cat_recomendada] = list(CATALOGO_SANCIONES.keys())[0]
            if key_fal_recomendada not in st.session_state:
                st.session_state[key_fal_recomendada] = None
    
            popover_key = f"pop_ia_{st.session_state.form_reset}_{st.session_state.ia_closed_state}"
            
            with st.popover("🪄 Usar Asistente de Clasificación (IA)", use_container_width=True, key=popover_key):
                st.markdown("### 🪄 Clasificación Inteligente")
                st.caption("Escribe los hechos ocurridos. La IA seleccionará la categoría y falta correspondientes en el formulario.")
                
                relato_incidencia = st.text_area(
                    "Descripción de los hechos:",
                    placeholder="Ejemplo: El alumno utilizó el celular durante la explicación...",
                    key=f"relato_ia_{st.session_state.form_reset}"
                )
    
                if st.button("🪄 Clasificar Hechos", type="primary", key=f"btn_ia_{st.session_state.form_reset}"):
                    if not relato_incidencia.strip():
                        st.warning("⚠️ Redacta los hechos antes de solicitar la clasificación.")
                    else:
                        try:
                            api_key_gemini = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api_key")
                            if not api_key_gemini:
                                for k in st.secrets.keys():
                                    sec = st.secrets[k]
                                    if isinstance(sec, dict):
                                        api_key_gemini = sec.get("GEMINI_API_KEY") or sec.get("gemini_api_key")
                                        if api_key_gemini: break
                            
                            if not api_key_gemini:
                                st.error("🔑 Llave de API no configurada.")
                            else:
                                genai.configure(api_key=api_key_gemini)
                                instrucciones_ia = f"""
                                Eres un asistente de disciplina escolar del Colegio Miraflores.
                                Tu función es clasificar estrictamente el relato dentro de las opciones de este catálogo oficial:
                                {json.dumps(CATALOGO_SANCIONES, ensure_ascii=False, indent=2)}
    
                                Reglas obligatorias:
                                1. Devuelve ÚNICA Y EXCLUSIVAMENTE un JSON plano con estas claves exactas:
                                {{"categoria": "Nombre de la Categoría", "falta": "Nombre de la Falta"}}
                                2. Respeta con exactitud las mayúsculas, acentos y signos del catálogo.
                                """
                                modelo = genai.GenerativeModel(
                                    model_name='gemini-3.6-flash',
                                    system_instruction=instrucciones_ia,
                                    generation_config={"response_mime_type": "application/json"}
                                )
                                
                                with st.spinner("Analizando hechos con IA..."):
                                    respuesta_api = modelo.generate_content(relato_incidencia)
                                    datos_clasificados = json.loads(respuesta_api.text.strip())
                                    
                                    cat_ia = datos_clasificados.get("categoria")
                                    fal_ia = datos_clasificados.get("falta")
                                    
                                    if cat_ia in CATALOGO_SANCIONES and fal_ia in CATALOGO_SANCIONES[cat_ia]:
                                        st.session_state[key_cat_recomendada] = cat_ia
                                        st.session_state[key_fal_recomendada] = fal_ia
                                        st.session_state[f"cat_{st.session_state.form_reset}"] = cat_ia
                                        
                                        puntos_falta = CATALOGO_SANCIONES[cat_ia][fal_ia]["puntos"]
                                        st.session_state[f"falta_{st.session_state.form_reset}"] = f"{fal_ia} ({puntos_falta} pt)"
                                        st.session_state[f"obs_prefill_{st.session_state.form_reset}"] = relato_incidencia
                                    else:
                                        st.warning("⚠️ La falta sugerida no coincidió exactamente con el catálogo oficial.")
                        
                        except Exception as e:
                            st.error(f"⚠️ El clasificador no está disponible temporalmente: {e}")
    
                if st.session_state[key_fal_recomendada]:
                    cat_sug = st.session_state[key_cat_recomendada]
                    fal_sug = st.session_state[key_fal_recomendada]
                    st.success(f"✅ Sugerencia: **{cat_sug}** ➔ **{fal_sug}**.")
                    
                    if st.button("Cerrar Ventana", type="secondary", key=f"close_ia_{st.session_state.form_reset}", use_container_width=True):
                        st.session_state["ia_closed_state"] += 1
                        st.rerun()
            
            c_cat, c_fal = st.columns([1, 2])
            lista_categorias = list(CATALOGO_SANCIONES.keys())
            try:
                indice_categoria_defecto = lista_categorias.index(st.session_state[key_cat_recomendada])
            except ValueError:
                indice_categoria_defecto = 0
                
            with c_cat:
                categoria = st.selectbox(
                    "Categoría:", 
                    lista_categorias, 
                    index=indice_categoria_defecto, 
                    key=f"cat_{st.session_state.form_reset}"
                )
                
            dict_faltas = CATALOGO_SANCIONES[categoria]
            opciones_visuales = [f"{nombre} ({datos['puntos']} pt)" for nombre, datos in dict_faltas.items()]
            
            indice_falta_defecto = 0
            if st.session_state[key_fal_recomendada]:
                for index_opcion, texto_opcion in enumerate(opciones_visuales):
                    if texto_opcion.startswith(st.session_state[key_fal_recomendada]):
                        indice_falta_defecto = index_opcion
                        break
                        
            with c_fal:
                falta_seleccionada_visual = st.selectbox(
                    "Falta cometida:", 
                    opciones_visuales, 
                    index=indice_falta_defecto, 
                    key=f"falta_{st.session_state.form_reset}"
                )
                
            falta_original = falta_seleccionada_visual.rsplit(" (",1)[0]
            redaccion_inicial = st.session_state.get(f"obs_prefill_{st.session_state.form_reset}", "")
            
            obs = st.text_area(
                "Observaciones y detalles de lo ocurrido:", 
                value=redaccion_inicial,
                key=f"obs_{st.session_state.form_reset}"
            )
    
            if st.button("💾 Guardar Registro", type="primary"):
                materia_final = obtener_materia_teorica(materia)
                
                if reporte_pasillo and not grupo_final:
                    st.error("⚠️ Selecciona al menos un grupo implicado en el reporte.")
                    st.stop()
                elif not reporte_pasillo and not alumnos_final:
                    st.error("⚠️ Selecciona al menos un alumno.")
                    st.stop()
                    
                obs_segura = str(obs).strip()
                if obs_segura.startswith(("=", "+", "-", "@")):
                    obs_segura = "'" + obs_segura
                    
                info_falta = dict_faltas.get(falta_original)
                p = info_falta["puntos"] if info_falta else 0
                s = info_falta["semaforo"] if info_falta else "Gris"
                
                hora_actual = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%H:%M:%S")
                f = f"{fecha_incidencia.strftime('%Y-%m-%d')} {hora_actual}"
                
                lote = []
                
                if reporte_pasillo:
                    if alumnos_por_grupo_seleccionados:
                        for g_real, al_limpio in alumnos_por_grupo_seleccionados:
                            lote.append([f, nombre_prof, materia_final, g_real, al_limpio, categoria, falta_original, obs_segura, p, s])
                    else:
                        for g in grupo_final:
                            lote.append([f, nombre_prof, materia_final, g, "General (Ver observaciones)", categoria, falta_original, obs_segura, p, s])
                else:
                    for g in grupo_final:
                        for al in alumnos_final:
                            lote.append([f, nombre_prof, materia_final, g, al, categoria, falta_original, obs_segura, p, s])
                
                try:
                    with st.spinner("Guardando en la nube..."):
                        doc = gc.open(FILE_REGISTROS)
                        #st.warning(f"🔗 ID del archivo que está leyendo Streamlit: {doc.id}")
                        clase_id = "Reportes_Pasillo" if reporte_pasillo else f"{materia_final} - {grupo_final[0]}"
                        
                        try:
                            ws = doc.worksheet(clase_id)
                        except gspread.exceptions.WorksheetNotFound:
                            ws = doc.add_worksheet(title=clase_id, rows="1000", cols="10")
                            ws.append_row(["Fecha", "Profesor", "Materia", "Grupo", "Alumno", "Categoría", "Falta", "Observaciones", "Puntos_Descontados", "Es_Grave"])
                        
                        ws.append_rows(lote)
                        leer_todos_los_registros.clear()
    
                        st.session_state.form_reset += 1
                        st.success("✅ Incidencia guardada con éxito en la base de datos.")
                        time.sleep(1.5)
                        st.rerun()
                except Exception as e:
                    st.error(f"🚨 Error crítico al intentar guardar en Sheets: {e}")

    # =================================================================
    # VISTA 2: EDICIÓN Y ELIMINACIÓN DE REPORTES (100% AUTOMATIZADA)
    # =================================================================
    else:
        with st.container():
            st.subheader("✏️ Editar o Eliminar Reportes Anteriores")
            st.info("💡 Selecciona la ubicación de un reporte tuyo para modificar sus observaciones o borrarlo permanentemente.")
            
            # Normalizador invisible: garantiza que 'Díaz' coincida con 'Diaz' y 'D'oleire' con 'Doleire'
            import unicodedata
            def normalizar(txt):
                t = str(txt).lower().strip().replace("'", "").replace("’", "")
                return ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')

            prof_target = normalizar(nombre_prof)
            
            # 🔍 Lectura dinámica de las pestañas que existen en el archivo real de Google Sheets
            try:
                time.sleep(0.05) # Micro-pausa preventiva contra límites de Google
                doc_registros = gc.open(FILE_REGISTROS)
                nombres_hojas_reales = [h.title for h in doc_registros.worksheets()]
            except Exception as e:
                nombres_hojas_reales = []

            es_pasillo_edit = st.checkbox("Buscar en 'Reportes de Pasillo'", key="edit_pasillo")
            
            ws_name = None
            if es_pasillo_edit:
                # Detecta automáticamente la pestaña de pasillo sin importar mayúsculas, espacios o guiones
                ws_name = next((h for h in nombres_hojas_reales if "pasillo" in h.lower()), "Reportes_Pasillo")
            else:
                if not mis_asig.empty:
                    c1_e, c2_e = st.columns(2)
                    mat_edit_raw = c1_e.selectbox("Materia:", mis_asig['Materia'].unique(), key="e_mat")
                    mat_edit_teorica = obtener_materia_teorica(mat_edit_raw)
                    grupos_disponibles_edit = mis_asig[mis_asig['Materia'] == mat_edit_raw]['Grupo'].unique()
                    grup_edit = c2_e.selectbox("Grupo:", grupos_disponibles_edit, key="e_grup")
                    
                    nombre_buscado = f"{mat_edit_teorica} - {grup_edit}"
                    if nombre_buscado in nombres_hojas_reales:
                        ws_name = nombre_buscado
                    else:
                        st.info(f"ℹ️ La pestaña '{nombre_buscado}' aún no tiene registros guardados.")
                else:
                    st.warning("No tienes materias asignadas para buscar reportes.")
                    
            if ws_name:
                try:
                    ws_edit = doc_registros.worksheet(ws_name)
                    todas_filas_edit = ws_edit.get_all_values()
                except Exception:
                    todas_filas_edit = []
                    
                if len(todas_filas_edit) > 1:
                    headers = [str(h).strip() for h in todas_filas_edit[0]]
                    df_edit = pd.DataFrame(todas_filas_edit[1:], columns=headers)
                    
                    # 🛡️ FILTRO AUTOMÁTICO TOLERANTE A ACENTOS
                    if not es_superusuario and 'Profesor' in df_edit.columns:
                        df_edit = df_edit[df_edit['Profesor'].apply(normalizar) == prof_target]
                        
                    if not df_edit.empty:
                        df_edit['Label'] = df_edit['Fecha'] + " | " + df_edit['Alumno'] + " | " + df_edit['Falta']
                        reporte_sel = st.selectbox("Selecciona el reporte a modificar:", ["Seleccione..."] + df_edit['Label'].tolist(), key="rep_sel")
                        
                        if reporte_sel != "Seleccione...":
                            fila_seleccionada = df_edit[df_edit['Label'] == reporte_sel].iloc[0]
                            fecha_exacta = fila_seleccionada['Fecha']
                            alumno_exacto = fila_seleccionada['Alumno']
                            obs_actual = fila_seleccionada['Observaciones']
                            
                            st.markdown(f"**Alumno:** {alumno_exacto} <br> **Falta:** {fila_seleccionada['Falta']}", unsafe_allow_html=True)
                            
                            nueva_obs = st.text_area("Observaciones / Detalles:", value=obs_actual, key="new_obs")
                            
                            c_btn1, c_btn2 = st.columns(2)
                            
                            if c_btn1.button("💾 Actualizar Observación", type="primary", use_container_width=True):
                                with st.spinner("Actualizando en la nube..."):
                                    all_vals = ws_edit.get_all_values()
                                    row_idx = next((i + 1 for i, row in enumerate(all_vals) if len(row) > 4 and str(row[0]).strip() == str(fecha_exacta).strip() and str(row[4]).strip() == str(alumno_exacto).strip()), None)
                                    
                                    if row_idx:
                                        # Columna 8 corresponde a Observaciones
                                        ws_edit.update_cell(row_idx, 8, nueva_obs)
                                        # Limpieza automática total de caché en segundo plano
                                        leer_todos_los_registros.clear()
                                        leer_datos.clear()
                                        st.success("✅ Observación actualizada correctamente.")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("❌ No se encontró el registro exacto en la base de datos.")
                                        
                            if c_btn2.button("🗑️ Eliminar Reporte", type="secondary", use_container_width=True):
                                with st.spinner("Eliminando reporte..."):
                                    all_vals = ws_edit.get_all_values()
                                    row_idx = next((i + 1 for i, row in enumerate(all_vals) if len(row) > 4 and str(row[0]).strip() == str(fecha_exacta).strip() and str(row[4]).strip() == str(alumno_exacto).strip()), None)
                                    
                                    if row_idx:
                                        ws_edit.delete_rows(row_idx)
                                        # Limpieza automática total de caché en segundo plano
                                        leer_todos_los_registros.clear()
                                        leer_datos.clear()
                                        st.success("✅ Reporte eliminado permanentemente.")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("❌ No se encontró el registro exacto en la base de datos.")
                    else:
                        st.info(f"No tienes reportes registrados en la pestaña '{ws_name}'.")
                else:
                    st.info(f"La pestaña '{ws_name}' aún no cuenta con registros guardados.")

    # =================================================================
    # ANALÍTICA (SIEMPRE VISIBLE AL FONDO)
    # =================================================================
    st.markdown("---")
    st.subheader("📈 Analítica de Conducta")
    df_full = leer_todos_los_registros(gc)
    
    if es_superusuario:
        df_doc = df_full
        titulo_tablero = "Reportes Globales Institucionales"
    else:
        df_doc = df_full[df_full['Profesor'] == nombre_prof] if not df_full.empty else df_full
        titulo_tablero = "Mis Reportes Docentes"
        
    mostrar_tablero_analitico(df_doc, titulo_tablero, modo_descarga=True)