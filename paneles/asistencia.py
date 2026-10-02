# paneles/asistencia.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

from config import (
    FILE_ASIGNACIONES, 
    FILE_ALUMNOS, 
    FILE_ASISTENCIA, 
    SUPER_USUARIOS_WHITELIST, 
    PERIODOS_LECTIVOS
)
from database import (
    leer_datos, 
    obtener_lista_alumnos, 
    obtener_dataframe_alumnos, 
    leer_todas_las_asignaciones,
    obtener_conexion_sql
)

def renderizar_panel_asistencia(gc, usuario, nombre_prof):
    
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

    st.header("📅 Gestión de Asistencia")
    
    if "modo_edicion_horario" not in st.session_state:
        st.session_state.modo_edicion_horario = False
        
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    
    hoy_cdmx = datetime.now(ZoneInfo("America/Mexico_City"))
    dia_num_hoy = hoy_cdmx.weekday()
    dias_espanol = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    nombre_dia_hoy = dias_espanol.get(dia_num_hoy)

    # 🎛️ MODOS DE VISTA REESTRUCTURADOS (SIN INTERRUPTORES CONFUSOS)
    modo_vista = st.radio(
        "Acción:", 
        ["📝 Pasar Lista del Día", "📊 Vista Histórica del Grupo (Modificar Asistencia)"], 
        horizontal=True
    )
    st.markdown("---")

    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura correcta en el archivo de asignaciones.")
        return
        
    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
    
    if es_superusuario:
        mis_asig = df_asig.copy()
    else:
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles_prof) > 1:
        nivel_elegido = st.radio("🏫 Nivel Escolar:", niveles_prof, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_elegido]
    elif len(niveles_prof) == 1:
        nivel_elegido = niveles_prof[0]
    else:
        nivel_elegido = "Preparatoria"

    try:
        df_config = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
    except Exception:
        df_config = pd.DataFrame(columns=["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

    c1, c2, c3 = st.columns([3, 3, 2])
    materia_seleccionada = c1.selectbox("Materia:", mis_asig['Materia'].unique(), key="asist_mat")
    materia = obtener_materia_teorica(materia_seleccionada)
    grupo = c2.selectbox("Grupo:", mis_asig[mis_asig['Materia'] == materia_seleccionada]['Grupo'].unique(), key="asist_grup")
    
    with c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if not st.session_state.modo_edicion_horario:
            if st.button("⚙️ Modificar horario", use_container_width=True):
                st.session_state.modo_edicion_horario = True
                st.rerun()

    try:
        grupo_limpio = grupo.split("(")[0].strip()
        df_alumnos_crudo = obtener_dataframe_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
        
        if df_alumnos_crudo is not None and not df_alumnos_crudo.empty:
            # 🛡️ SANEAMIENTO: Usamos area_academica
            col_area = 'area_academica' if 'area_academica' in df_alumnos_crudo.columns else ('Área' if 'Área' in df_alumnos_crudo.columns else None)
            if col_area:
                texto_busqueda = f"{materia} {grupo}".upper()
                if "ÁREA 1" in texto_busqueda or "ÁREA I" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('1|I|CIENCIAS', na=False)]
                elif "ÁREA 2" in texto_busqueda or "ÁREA II" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('2|II', na=False)]
                elif "ÁREA 3" in texto_busqueda or "ÁREA III" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('3|III|HUMANIDADES', na=False)]
                elif "ÁREA 4" in texto_busqueda or "ÁREA IV" in texto_busqueda:
                    df_alumnos_crudo = df_alumnos_crudo[df_alumnos_crudo[col_area].astype(str).str.upper().str.contains('4|IV', na=False)]
            if 'Nombre Completo' in df_alumnos_crudo.columns:
                nombres = df_alumnos_crudo['Nombre Completo'].replace(r'^nan nan nan$|^nan$|^$', pd.NA, regex=True).dropna()
                alumnos = sorted(nombres.unique().tolist())
            else:
                alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
        else:
            alumnos = []
    except Exception as e:
        alumnos = []
        st.error(f"Error al obtener alumnos: {e}")
        
    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo '{grupo_limpio}'.")
        return

    nombre_pestana = f"{materia} - {grupo}"
    config_actual = pd.DataFrame()
    if not df_config.empty and 'Clase' in df_config.columns:
        config_actual = df_config[df_config['Clase'] == nombre_pestana]

    v_lun, v_mar, v_mie, v_jue, v_vie = 0, 0, 0, 0, 0
    if not config_actual.empty:
        v_lun = int(config_actual.iloc[0].get('Lunes', 0))
        v_mar = int(config_actual.iloc[0].get('Martes', 0))
        v_mie = int(config_actual.iloc[0].get('Miercoles', 0))
        v_jue = int(config_actual.iloc[0].get('Jueves', 0))
        v_vie = int(config_actual.iloc[0].get('Viernes', 0))

    if config_actual.empty:
        st.info(f"⚙️ Configuración requerida para {nombre_pestana}")
        mostrar_formulario = True
        detener_app = True
    else:
        mostrar_formulario = st.session_state.modo_edicion_horario
        detener_app = False

    # Formulario para editar horario de la materia
    if mostrar_formulario:
        with st.container():
            if not config_actual.empty:
                _, c_cerrar = st.columns([8, 2])
                with c_cerrar:
                    if st.button("❌ Cerrar", use_container_width=True):
                        st.session_state.modo_edicion_horario = False
                        st.rerun()

            with st.form(f"form_horario_{nombre_pestana}"):
                st.write("Horas de clase por día (0 = Sin clase, 1 = Sencilla, 2 = Doble):")
                c_lun, c_mar, c_mie, c_jue, c_vie = st.columns(5)
                h_lun = c_lun.number_input("Lunes", 0, 4, v_lun)
                h_mar = c_mar.number_input("Martes", 0, 4, v_mar)
                h_mie = c_mie.number_input("Miérc.", 0, 4, v_mie)
                h_jue = c_jue.number_input("Jueves", 0, 4, v_jue)
                h_vie = c_vie.number_input("Viernes", 0, 4, v_vie)

                if st.form_submit_button("💾 Guardar Horario", type="primary"):
                    if sum([h_lun, h_mar, h_mie, h_jue, h_vie]) == 0:
                        st.error("⚠️ Asigna al menos 1 hora de clase a la semana.")
                    else:
                        try:
                            conn = obtener_conexion_sql()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM [asistencia_config] WHERE [Clase] = ?", (nombre_pestana,))
                            cursor.execute(
                                "INSERT INTO [asistencia_config] (Clase, Lunes, Martes, Miercoles, Jueves, Viernes) VALUES (?, ?, ?, ?, ?, ?)",
                                (nombre_pestana, int(h_lun), int(h_mar), int(h_mie), int(h_jue), int(h_vie))
                            )
                            conn.commit()
                            st.session_state.modo_edicion_horario = False
                            leer_datos.clear() 
                            st.success("✅ Horario actualizado correctamente en la base de datos.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_h:
                            st.error(f"Error al guardar horario: {e_h}")
    if detener_app:
        return

    # Total de horas a la semana (frecuencia real)
    dias_semana_clase = sum([v_lun, v_mar, v_mie, v_jue, v_vie])
    horario_clase = {0: v_lun, 1: v_mar, 2: v_mie, 3: v_jue, 4: v_vie, 5: 0, 6: 0}

    # =================================================================
    # DETECCIÓN DE PERIODO Y LÍMITES
    # =================================================================
    nivel_key = "Secundaria" if "secundaria" in nivel_elegido.lower() else "Preparatoria"
    periodos_nivel = PERIODOS_LECTIVOS.get(nivel_key, [])
    
    periodo_actual_nombre = "1° Periodo"
    idx_periodo = 0
    fecha_evaluacion = hoy_cdmx.date()

    for i, p in enumerate(periodos_nivel):
        inicio = datetime.strptime(p["inicio"], "%Y-%m-%d").date()
        fin = datetime.strptime(p["fin"], "%Y-%m-%d").date()
        if inicio <= fecha_evaluacion <= fin:
            periodo_actual_nombre = p["nombre"]
            idx_periodo = i
            break
    else:
        if periodos_nivel:
            primero = datetime.strptime(periodos_nivel[0]["inicio"], "%Y-%m-%d").date()
            if fecha_evaluacion < primero:
                periodo_actual_nombre = periodos_nivel[0]["nombre"]
                idx_periodo = 0
            else:
                periodo_actual_nombre = periodos_nivel[-1]["nombre"]
                idx_periodo = len(periodos_nivel) - 1

    if "secundaria" in nivel_elegido.lower():
        opciones_asistencia = ["✅ Presente", "🔴 Falta"]
        opciones_hist = ["✅ Presente", "🔴 Falta", "⚪ Sin Clase", ""]
        limites_tabla = {1: [2, 2, 3], 2: [3, 4, 5], 3: [5, 6, 7], 4: [6, 8, 10], 5: [8, 10, 12]}
    else:
        opciones_asistencia = ["✅ Presente", "🟡 Retardo", "🔴 Falta"]
        opciones_hist = ["✅ Presente", "🟡 Retardo", "🔴 Falta", "⚪ Sin Clase", ""]
        limites_tabla = {1: [2, 2, 2, 2, 2], 2: [4, 3, 4, 4, 4], 3: [5, 5, 4, 5, 5], 4: [7, 7, 6, 7, 7], 5: [9, 9, 7, 9, 9]}

    limites_fila = limites_tabla.get(dias_semana_clase, [99, 99, 99, 99, 99])
    limite_faltas = limites_fila[idx_periodo] if idx_periodo < len(limites_fila) else limites_fila[-1]

    # Cargar datos de la clase actual
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    # ✅ FIX: Función para ordenar las fechas cronológicamente de forma estricta
    def clave_orden_fecha(col_nombre):
        try:
            f_limpia = col_nombre.split(" (")[0].strip()
            dt = datetime.strptime(f_limpia, "%d-%m-%Y")
            # Desempate para clases dobles: S1 va primero (1), S2 va después (2)
            prioridad = 1 if "(S1)" in col_nombre else (2 if "(S2)" in col_nombre else 0)
            return (dt, prioridad)
        except Exception:
            return (datetime.min, 0)

    # Extraemos y ordenamos del día más antiguo al más reciente
    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    columnas_fechas.sort(key=clave_orden_fecha)
    
    peso_fechas = {}

    for col_f in columnas_fechas:
        if "(S1)" in col_f or "(S2)" in col_f:
            peso_fechas[col_f] = 1
        else:
            try:
                fecha_limpia = col_f.split(" (")[0]
                d_sem = datetime.strptime(fecha_limpia, "%d-%m-%Y").weekday()
                peso_fechas[col_f] = horario_clase.get(d_sem, 1) or 1
            except Exception:
                peso_fechas[col_f] = 1

    # Cálculo exacto de inasistencias acumuladas
    faltas_dict, retardos_dict, faltas_efectivas_dict, derecho_examen_dict = {}, {}, {}, {}
    for al in alumnos:
        if al in df_historial['Alumno'].values:
            fila_al = df_historial[df_historial['Alumno'] == al].iloc[0]
            f_real = sum(peso_fechas.get(c, 1) for c in columnas_fechas if str(fila_al[c]) == '🔴 Falta')
            r_real = sum(1 for c in columnas_fechas if str(fila_al[c]) == '🟡 Retardo')
            f_efec = f_real + (r_real // 3)
            
            faltas_dict[al] = f_real
            retardos_dict[al] = r_real
            faltas_efectivas_dict[al] = f_efec
            
            if f_efec > limite_faltas:
                derecho_examen_dict[al] = "❌ SIN DERECHO"
            elif f_efec == limite_faltas:
                derecho_examen_dict[al] = "🚨 LÍMITE ALCANZADO"
            elif f_efec == (limite_faltas - 1) and limite_faltas > 1:
                derecho_examen_dict[al] = "⚠️ EN RIESGO (-1 falta)"
            else:
                derecho_examen_dict[al] = "✅ SÍ"
        else:
            faltas_dict[al], retardos_dict[al], faltas_efectivas_dict[al] = 0, 0, 0
            derecho_examen_dict[al] = "✅ SÍ"

    # =================================================================
    # 🗓️ CÁLCULO DE DÍAS QUE DEBIERON TENER CLASE (CALENDARIO VS ASISTENCIA)
    # =================================================================
    inicio_p_dt = datetime.strptime(periodos_nivel[idx_periodo]["inicio"], "%Y-%m-%d").date()
    hoy_dt = hoy_cdmx.date()
    
    fechas_calendario_debio = []
    curr = inicio_p_dt
    while curr <= hoy_dt:
        if horario_clase.get(curr.weekday(), 0) > 0:
            fechas_calendario_debio.append(curr.strftime("%d-%m-%Y"))
        curr += timedelta(days=1)
        
    fechas_ya_registradas = [c.split(" (")[0].strip() for c in columnas_fechas]
    fechas_pendientes = [f for f in fechas_calendario_debio if f not in fechas_ya_registradas]

    # =================================================================
    # MODO 1: PASE DE LISTA DEL DÍA
    # =================================================================
    if modo_vista == "📝 Pasar Lista del Día":
        st.info(f"💡 Frecuencia: **{dias_semana_clase} horas/semana**. Evaluando **{periodo_actual_nombre}** (Límite: **{limite_faltas} faltas** | 3 Retardos = 1 Falta).")
        
        # Alertas de alumnos en riesgo
        alumnos_sin_derecho = [al for al, est in derecho_examen_dict.items() if est == "❌ SIN DERECHO"]
        alumnos_en_riesgo = [al for al, est in derecho_examen_dict.items() if "RIESGO" in est or "LÍMITE" in est]
        if alumnos_sin_derecho:
            st.error(f"🚫 **ALUMNOS SIN DERECHO:** {', '.join(alumnos_sin_derecho)} (Superaron el límite de {limite_faltas} faltas).")
        if alumnos_en_riesgo:
            st.warning(f"⚠️ **EN RIESGO PREVENTIVO:** {', '.join(alumnos_en_riesgo)}.")

        # Fechas seleccionables: Hoy + Días pendientes de pase de lista
        fechas_disponibles_pase = []
        etiquetas_pase = {}
        
        if horario_clase.get(dia_num_hoy, 0) > 0:
            f_hoy_str = hoy_cdmx.strftime("%d-%m-%Y")
            fechas_disponibles_pase.append(f_hoy_str)
            etiquetas_pase[f_hoy_str] = f"Hoy ({nombre_dia_hoy}) {f_hoy_str}"
            
        for f_p in reversed(fechas_pendientes):
            if f_p not in fechas_disponibles_pase:
                fechas_disponibles_pase.append(f_p)
                d_p_num = datetime.strptime(f_p, "%d-%m-%Y").weekday()
                etiquetas_pase[f_p] = f"⚠️ Pendiente: {dias_espanol[d_p_num]} {f_p}"
                
        if not fechas_disponibles_pase:
            st.success(f"🎉 **Estás al corriente con todas tus clases registradas hasta el día de hoy.**")
            st.caption("Si deseas revisar o modificar alguna fecha anterior, ingresa arriba a 'Vista Histórica del Grupo'.")
            return

        fecha_str = st.selectbox("📅 Fecha de clase:", fechas_disponibles_pase, format_func=lambda x: etiquetas_pase[x])
        dia_seleccionado = datetime.strptime(fecha_str, "%d-%m-%Y").weekday()
        horas_ese_dia = horario_clase.get(dia_seleccionado, 1)

        if horas_ese_dia >= 2:
            tipo_sesion = st.radio(
                "¿Cómo registrarás la clase doble de hoy?",
                ["🕒 Bloque Continuo (Sesión de 2 horas)", "1️⃣ Primer Módulo (1 hora)", "2️⃣ Segundo Módulo (1 hora)"],
                horizontal=True
            )
            if "Primer" in tipo_sesion:
                col_fecha_final = f"{fecha_str} (S1)"
                st.info("ℹ️ Cada inasistencia contará como **1 falta**.")
            elif "Segundo" in tipo_sesion:
                col_fecha_final = f"{fecha_str} (S2)"
                st.info("ℹ️ Cada inasistencia contará como **1 falta**.")
            else:
                col_fecha_final = f"{fecha_str}"
                st.warning("⚠️ **ATENCIÓN: Registrando Bloque Continuo (2 horas).** Una inasistencia computará como **2 faltas reglamentarias**.")
        else:
            col_fecha_final = fecha_str

        if col_fecha_final in df_historial.columns:
            valores_previos = dict(zip(df_historial['Alumno'], df_historial[col_fecha_final]))
            col_asist = [valores_previos.get(al, "✅ Presente") if pd.notna(valores_previos.get(al)) and valores_previos.get(al) != "" else "✅ Presente" for al in alumnos]
        else:
            col_asist = ["✅ Presente"] * len(alumnos)

        df_view = pd.DataFrame({
            "Alumno": alumnos,
            "Asistencia": col_asist,
            "Faltas Reales": [faltas_dict[al] for al in alumnos],
            "Retardos": [retardos_dict[al] for al in alumnos],
            "Faltas Efectivas": [faltas_efectivas_dict[al] for al in alumnos],
            "Derecho Examen": [derecho_examen_dict[al] for al in alumnos]
        })

        col_config = {
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Asistencia": st.column_config.SelectboxColumn("Asistencia", options=opciones_asistencia, required=True),
            "Faltas Reales": st.column_config.NumberColumn("Faltas", disabled=True),
            "Faltas Efectivas": st.column_config.NumberColumn("Efectivas", disabled=True),
            "Derecho Examen": st.column_config.TextColumn("Derecho", disabled=True)
        }
        if "secundaria" in nivel_elegido.lower():
            col_config["Retardos"] = None
        else:
            col_config["Retardos"] = st.column_config.NumberColumn("Retardos", disabled=True)

        df_editado = st.data_editor(
            df_view,
            column_config=col_config,
            hide_index=True,
            use_container_width=True,
            key=f"ed_{materia}_{grupo}_{col_fecha_final}"
        )

        if st.button("💾 Guardar Asistencia", type="primary"):
            with st.spinner(f"Guardando asistencia del {col_fecha_final}..."):
                mapeo_asist = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
                conn = obtener_conexion_sql()
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, col_fecha_final))
                
                # 🛡️ PK SEGURA: Nombramos explícitamente las columnas para no colisionar con asistencia_id
                lote_insert = [(nombre_pestana, al, col_fecha_final, mapeo_asist.get(al, "✅ Presente")) for al in alumnos]
                cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote_insert)
                conn.commit()
                
                leer_datos.clear()
                st.success("✅ Asistencia guardada correctamente.")
                time.sleep(1)
                st.rerun()

    # =================================================================
    # MODO 2: VISTA HISTÓRICA DEL GRUPO (MODIFICAR ASISTENCIA)
    # =================================================================
    else:
        st.markdown(f"### 📈 Historial y Modificación: {grupo} ({materia})")
        st.caption("Edita cualquier celda directamente en la tabla. Los totales se recalcularán automáticamente.")
        
        # 🟡 1. DETECCIÓN VISUAL DE DÍAS PENDIENTES Y GESTIÓN RÁPIDA
        if fechas_pendientes:
            st.warning(f"🟡 **Atención: Hay {len(fechas_pendientes)} día(s) en los que debió haber clase y no se ha pasado lista:**\n\n" + 
                       ", ".join([f"`{f}`" for f in fechas_pendientes]))
            
            with st.popover("⚙️ Gestionar Fechas Pendientes / Añadir a la Lista", use_container_width=True):
                st.markdown("##### 📅 Días pendientes en el calendario oficial")
                fecha_gestionar = st.selectbox("Selecciona la fecha pendiente:", fechas_pendientes, key="f_gest_sel")
                
                # Detectamos las horas programadas para ese día específico
                dia_sem_gest = datetime.strptime(fecha_gestionar, "%d-%m-%Y").weekday()
                horas_dia_gest = horario_clase.get(dia_sem_gest, 1)
                
                # --- ACCIÓN 1: AÑADIR A LA LISTA PARA REGISTRO RÁPIDO ---
                st.markdown("---")
                st.markdown("##### 🚀 Opción 1: Pasar lista de ese día (Añadir a la tabla)")
                
                columnas_a_crear = [fecha_gestionar]
                
                if horas_dia_gest >= 2:
                    st.caption("ℹ️ Este día tiene programada **clase doble (2 horas)**:")
                    tipo_bloque_gest = st.radio(
                        "Estructura de la sesión:",
                        [
                            "👥 Ambos Módulos Separados (Crear S1 y S2 a la vez)",
                            "🕒 Bloque Continuo (1 sola columna - Falta cuenta doble)",
                            "1️⃣ Solo Primer Módulo (Sesión S1)",
                            "2️⃣ Solo Segundo Módulo (Sesión S2)"
                        ],
                        key=f"tipo_blq_{fecha_gestionar}"
                    )
                    
                    if "Ambos Módulos" in tipo_bloque_gest:
                        columnas_a_crear = [f"{fecha_gestionar} (S1)", f"{fecha_gestionar} (S2)"]
                        st.info("💡 Se crearán dos columnas contiguas: **S1** y **S2** (cada falta vale 1 hora).")
                    elif "Primer" in tipo_bloque_gest:
                        columnas_a_crear = [f"{fecha_gestionar} (S1)"]
                    elif "Segundo" in tipo_bloque_gest:
                        columnas_a_crear = [f"{fecha_gestionar} (S2)"]
                    else:
                        columnas_a_crear = [fecha_gestionar]
                        st.warning("⚠️ En Bloque Continuo, una falta equivaldrá a 2 faltas reglamentarias.")
                
                if st.button("➕ Añadir a la lista (Prellenar presentes)", type="primary", use_container_width=True, key=f"btn_add_date_quick_{fecha_gestionar}"):
                    conn = obtener_conexion_sql()
                    cursor = conn.cursor()
                    
                    for col_n in columnas_a_crear:
                        cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, col_n))
                        # 🛡️ PK SEGURA: Columnas explícitas
                        lote_nuevo = [(nombre_pestana, al, col_n, "✅ Presente") for al in alumnos]
                        cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote_nuevo)
                        
                    conn.commit()
                    leer_datos.clear()
                    st.success(f"✅ Se añadieron: {', '.join(columnas_a_crear)} a la tabla.")
                    time.sleep(1)
                    st.rerun()
                    if "Primer" in tipo_bloque_gest:
                        col_fecha_agregar = f"{fecha_gestionar} (S1)"
                    elif "Segundo" in tipo_bloque_gest:
                        col_fecha_agregar = f"{fecha_gestionar} (S2)"
                    else:
                        col_fecha_agregar = fecha_gestionar
                
                # --- ACCIÓN 2: JUSTIFICAR O DESCARTAR DÍA ---
                st.markdown("---")
                st.markdown("##### ⚪ Opción 2: Justificar día sin clase (Auditorio, Festivo, etc.)")
                motivo = st.text_input("Motivo / Justificación:", placeholder="Ej. Bajaron al auditorio / Suspensión oficial", key="motivo_input_just")
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    if st.button("⚪ Marcar Sin Clase", use_container_width=True, key="btn_just_sin_clase"):
                        motivo_final = f"⚪ Sin Clase ({motivo.strip()})" if motivo.strip() else "⚪ Sin Clase"
                        conn = obtener_conexion_sql()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, fecha_gestionar))
                        lote_sin_clase = [(nombre_pestana, al, fecha_gestionar, motivo_final) for al in alumnos]
                        cursor.executemany("INSERT INTO [asistencia_registros] VALUES (?, ?, ?, ?)", lote_sin_clase)
                        conn.commit()
                        leer_datos.clear()
                        st.success(f"✅ Fecha {fecha_gestionar} registrada como sin clase.")
                        time.sleep(1)
                        st.rerun()
                with col_g2:
                    if st.button("🗑️ Descartar día", use_container_width=True, key="btn_descartar_fecha"):
                        conn = obtener_conexion_sql()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ? AND [Fecha] = ?", (nombre_pestana, fecha_gestionar))
                        lote_descarte = [(nombre_pestana, al, fecha_gestionar, "⚪ Descartado") for al in alumnos]
                        cursor.executemany("INSERT INTO [asistencia_registros] VALUES (?, ?, ?, ?)", lote_descarte)
                        conn.commit()
                        leer_datos.clear()
                        st.success(f"✅ Fecha {fecha_gestionar} descartada del calendario.")
                        time.sleep(1)
                        st.rerun()

        # 2. CONSTRUCCIÓN DE LA TABLA EDITABLE HISTÓRICA
        if df_historial.empty or len(columnas_fechas) == 0:
            st.info("💡 Aún no hay asistencias registradas en este salón. Pasa lista en 'Pasar Lista del Día' o usa '➕ Añadir a la lista' arriba.")
            return

        df_mostrar = pd.DataFrame({"Alumno": df_historial["Alumno"]})
        df_mostrar["Derecho Examen"] = df_mostrar["Alumno"].map(derecho_examen_dict)
        df_mostrar["Faltas Efectivas"] = df_mostrar["Alumno"].map(faltas_efectivas_dict)
        df_mostrar["Faltas Reales"] = df_mostrar["Alumno"].map(faltas_dict)
        df_mostrar["Retardos"] = df_mostrar["Alumno"].map(retardos_dict)
        
        for col in columnas_fechas:
            df_mostrar[col] = df_historial[col]
            
        config_cols_hist = {
            "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
            "Derecho Examen": st.column_config.TextColumn("Derecho", disabled=True),
            "Faltas Efectivas": st.column_config.NumberColumn("Efectivas", disabled=True),
            "Faltas Reales": st.column_config.NumberColumn("Faltas", disabled=True)
        }
        if "secundaria" in nivel_elegido.lower():
            config_cols_hist["Retardos"] = None
        else:
            config_cols_hist["Retardos"] = st.column_config.NumberColumn("Retardos", disabled=True)
            
        for col in columnas_fechas:
            config_cols_hist[col] = st.column_config.SelectboxColumn(col, options=opciones_hist, required=False)

        df_editado_hist = st.data_editor(
            df_mostrar,
            column_config=config_cols_hist,
            use_container_width=True,
            hide_index=True,
            key=f"ed_hist_{materia}_{grupo}"
        )
        
        c_h1, c_h2 = st.columns([1, 1])
        with c_h1:
            if st.button("💾 Guardar Cambios Históricos", type="primary", use_container_width=True):
                with st.spinner("Actualizando en Supabase..."):
                    conn = obtener_conexion_sql()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM [asistencia_registros] WHERE [Clase] = ?", (nombre_pestana,))
                    
                    lote_hist = []
                    for _, r in df_editado_hist.iterrows():
                        al_nom = r['Alumno']
                        for col_f in columnas_fechas:
                            val_estatus = str(r.get(col_f, "")).strip()
                            if val_estatus != "":
                                lote_hist.append((nombre_pestana, al_nom, col_f, val_estatus))
                                
                    # 🛡️ PK SEGURA: Columnas explícitas
                    cursor.executemany('INSERT INTO [asistencia_registros] ("Clase", "Alumno", "Fecha", "Estatus") VALUES (?, ?, ?, ?)', lote_hist)
                    conn.commit()
                    
                    leer_datos.clear()
                    st.success("✅ Cambios históricos guardados correctamente.")
                    time.sleep(1)
                    st.rerun()
                    
        with c_h2:
            # 🛡️ LIMPIEZA DE EMOJIS PARA EXCEL EN ASISTENCIA
            df_export_asist = df_mostrar.copy()
            remplazos_excel = {
                "✅ Presente": "Presente",
                "🔴 Falta": "Falta",
                "🟡 Retardo": "Retardo",
                "⚪ Sin Clase": "Sin Clase",
                "⚪ Descartado": "Descartado",
                "✅ SÍ": "SÍ",
                "❌ NO": "NO",
                "❌ SIN DERECHO": "SIN DERECHO",
                "🚨 LÍMITE ALCANZADO": "LÍMITE ALCANZADO",
                "⚠️ EN RIESGO (-1 falta)": "EN RIESGO (-1 falta)"
            }
            # Reemplaza los emojis por texto limpio en todas las columnas
            for col in df_export_asist.columns:
                df_export_asist[col] = df_export_asist[col].replace(remplazos_excel)
                
            st.download_button(
                "📥 Descargar Matriz CSV",
                df_export_asist.to_csv(index=False).encode('utf-8-sig'),
                f"Asistencia_{materia}_{grupo}.csv",
                mime="text/csv",
                use_container_width=True
            )