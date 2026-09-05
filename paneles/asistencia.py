# paneles/asistencia.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import gspread
import time

from config import FILE_ASIGNACIONES, FILE_ALUMNOS, FILE_ASISTENCIA, SUPER_USUARIOS_WHITELIST
from database import leer_datos, obtener_lista_alumnos, leer_todas_las_asignaciones

def renderizar_panel_asistencia(gc, usuario, nombre_prof):
    st.header("📅 Gestión de Asistencia")
    
    if "modo_edicion_horario" not in st.session_state:
        st.session_state.modo_edicion_horario = False
        
    usuario = str(usuario).lower().strip()
    es_superusuario = usuario in SUPER_USUARIOS_WHITELIST
    
    # 1. Definir el tiempo exacto HOY
    hoy_cdmx = datetime.now(ZoneInfo("America/Mexico_City"))
    dia_num_hoy = hoy_cdmx.weekday()
    dias_espanol = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    nombre_dia_hoy = dias_espanol.get(dia_num_hoy)

    modo_vista = st.radio(
        "Acción:", 
        ["📝 Pasar Lista / Editar Día", "📊 Vista Histórica del Grupo"], 
        horizontal=True
    )
    st.markdown("---")

    habilitar_historico = st.toggle("🔓 Modificar asistencia de días anteriores (Mostrar todas las materias)")

    # ========================================================
    # BARRERA INQUEBRANTABLE (FIN DE SEMANA)
    # ========================================================
    if modo_vista == "📝 Pasar Lista / Editar Día" and not habilitar_historico:
        if dia_num_hoy in [5, 6]:
            st.warning(f"☕ **Hoy es {nombre_dia_hoy}. No hay clases programadas en fin de semana.**")
            st.info("💡 Para revisar o modificar inasistencias de días anteriores, activa el interruptor de arriba.")
            return  # Detiene toda la ejecución de esta pantalla aquí mismo

    # ========================================================
    # CARGA DE DATOS (Solo se ejecuta si pasó la barrera)
    # ========================================================
    df_asig = leer_todas_las_asignaciones(gc, FILE_ASIGNACIONES)
    if df_asig.empty or 'Usuario_Profesor' not in df_asig.columns:
        st.warning("⚠️ No se encontró la estructura correcta en el archivo de asignaciones.")
        return
        
    df_asig['Usuario_Profesor'] = df_asig['Usuario_Profesor'].astype(str).str.lower().str.strip()
    if 'Materia' in df_asig.columns:
        df_asig['Materia'] = df_asig['Materia'].astype(str).str.strip()
    if 'Grupo' in df_asig.columns:
        df_asig['Grupo'] = df_asig['Grupo'].astype(str).str.strip()
        
    if es_superusuario:
        mis_asig = df_asig.copy()
    else:
        mis_asig = df_asig[df_asig['Usuario_Profesor'] == usuario]
    
    if mis_asig.empty:
        st.warning("Sin materias asignadas para pasar lista.")
        return

    # Separación de Nivel
    niveles_prof = sorted(mis_asig['Nivel'].unique().tolist())
    if len(niveles_prof) > 1:
        nivel_elegido = st.radio("🏫 Nivel Escolar:", niveles_prof, horizontal=True)
        mis_asig = mis_asig[mis_asig['Nivel'] == nivel_elegido]

    # Cargar Configuración de Horarios
    try:
        df_config = leer_datos(gc, FILE_ASISTENCIA, "Configuracion")
    except Exception:
        df_config = pd.DataFrame(columns=["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

    materias_filtradas = mis_asig.copy()

    # LOGICA DE FILTRADO DE MATERIAS PARA EL DÍA EN CURSO (Lunes a Viernes)
    if modo_vista == "📝 Pasar Lista / Editar Día" and not habilitar_historico and not es_superusuario:
        if not df_config.empty and 'Clase' in df_config.columns and nombre_dia_hoy in df_config.columns:
            clases_hoy = df_config[pd.to_numeric(df_config[nombre_dia_hoy], errors='coerce').fillna(0) > 0]['Clase'].tolist()
            materias_hoy = []
            for _, r in mis_asig.iterrows():
                tag = f"{r['Materia']} - {r['Grupo']}"
                if tag in clases_hoy or tag not in df_config['Clase'].values:
                    materias_hoy.append(r['Materia'])
            
            if materias_hoy:
                materias_filtradas = mis_asig[mis_asig['Materia'].isin(materias_hoy)]
            else:
                st.success(f"☕ **Hoy {nombre_dia_hoy} no tienes ninguna clase asignada en tu horario.**")
                st.info("💡 Activa el interruptor arriba para modificar días anteriores.")
                return

    c1, c2, c3 = st.columns([3, 3, 2])
    materia = c1.selectbox("Materia:", materias_filtradas['Materia'].unique(), key="asist_mat")
    grupo = c2.selectbox("Grupo:", materias_filtradas[materias_filtradas['Materia'] == materia]['Grupo'].unique(), key="asist_grup")
    
    with c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if not st.session_state.modo_edicion_horario:
            if st.button("⚙️ Modificar horario", use_container_width=True):
                st.session_state.modo_edicion_horario = True
                st.rerun()

    # Obtener alumnos
    try:
        grupo_limpio = grupo.split("(")[0].strip()
        alumnos = obtener_lista_alumnos(gc, FILE_ALUMNOS, grupo_limpio)
    except Exception:
        alumnos = []

    if not alumnos:
        st.warning(f"No se encontraron alumnos registrados para el grupo '{grupo_limpio}'.")
        return

    nombre_pestana = f"{materia} - {grupo}"

    # Horarios de la materia
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
                        doc = gc.open(FILE_ASISTENCIA)
                        try:
                            ws_conf = doc.worksheet("Configuracion")
                        except gspread.exceptions.WorksheetNotFound:
                            ws_conf = doc.add_worksheet("Configuracion", rows="100", cols="6")
                            ws_conf.append_row(["Clase", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes"])

                        nueva_fila = [nombre_pestana, h_lun, h_mar, h_mie, h_jue, h_vie]
                        if config_actual.empty:
                            ws_conf.append_row(nueva_fila)
                        else:
                            todas_filas = ws_conf.get_all_values()
                            for i, f in enumerate(todas_filas[1:], start=2):
                                if f and f[0] == nombre_pestana:
                                    ws_conf.update(values=[nueva_fila], range_name=f"A{i}:F{i}")
                                    break
                                    
                        st.session_state.modo_edicion_horario = False
                        leer_datos.clear() 
                        st.success("✅ Horario guardado.")
                        time.sleep(1)
                        st.rerun()
    if detener_app:
        return

    dias_semana_clase = sum(1 for h in [v_lun, v_mar, v_mie, v_jue, v_vie] if h > 0)
    limite_faltas_dict = {0: 99, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9}
    limite_faltas = limite_faltas_dict.get(dias_semana_clase, 7)
    horario_clase = {0: v_lun, 1: v_mar, 2: v_mie, 3: v_jue, 4: v_vie, 5: 0, 6: 0}

    # Leer historial
    try:
        df_historial = leer_datos(gc, FILE_ASISTENCIA, nombre_pestana)
    except Exception:
        df_historial = pd.DataFrame()

    if df_historial.empty or 'Alumno' not in df_historial.columns:
        df_historial = pd.DataFrame({"Alumno": alumnos})

    columnas_fechas = [c for c in df_historial.columns if c != 'Alumno']
    peso_fechas = {}
    for col_f in columnas_fechas:
        try:
            d_sem = datetime.strptime(col_f, "%d-%m-%Y").weekday()
            peso_fechas[col_f] = horario_clase.get(d_sem, 1) or 1
        except Exception:
            peso_fechas[col_f] = 1

    faltas_dict, retardos_dict, faltas_efectivas_dict, derecho_examen_dict = {}, {}, {}, {}
    for al in alumnos:
        if al in df_historial['Alumno'].values:
            fila_al = df_historial[df_historial['Alumno'] == al].iloc[0]
            f_pond = sum(peso_fechas[c] for c in columnas_fechas if str(fila_al[c]) == '🔴 Falta')
            r_pond = sum(peso_fechas[c] for c in columnas_fechas if str(fila_al[c]) == '🟡 Retardo')
            f_efec = f_pond + (r_pond // 3)
            faltas_dict[al] = f_pond
            retardos_dict[al] = r_pond
            faltas_efectivas_dict[al] = f_efec
            derecho_examen_dict[al] = "✅ SÍ" if f_efec <= limite_faltas else "❌ NO"
        else:
            faltas_dict[al], retardos_dict[al], faltas_efectivas_dict[al] = 0, 0, 0
            derecho_examen_dict[al] = "✅ SÍ"

    # ========================================================
    # MODO 1: Pase de Lista
    # ========================================================
    if modo_vista == "📝 Pasar Lista / Editar Día":
        st.info(f"💡 Frecuencia: **{dias_semana_clase} días/semana**. Límite: **{limite_faltas} faltas**. (3 Retardos = 1 Falta).")
        
        fechas_validas, etiquetas_fechas = [], {}
        
        if habilitar_historico:
            for i in range(1, 45):
                fecha_eval = hoy_cdmx - timedelta(days=i)
                dia_sem = fecha_eval.weekday()
                if dia_sem in [5, 6]: continue
                if dias_semana_clase > 0 and horario_clase.get(dia_sem, 0) == 0: continue
                
                f_str = fecha_eval.strftime("%d-%m-%Y")
                fechas_validas.append(f_str)
                etiquetas_fechas[f_str] = f"{dias_espanol[dia_sem]} {f_str}"
        else:
            f_str = hoy_cdmx.strftime("%d-%m-%Y")
            fechas_validas.append(f_str)
            etiquetas_fechas[f_str] = f"Hoy ({dias_espanol[dia_num_hoy]}) {f_str}"

        if not fechas_validas:
            st.warning("No se encontraron fechas de clase anteriores para esta materia.")
            return

        fecha_str = st.selectbox("📅 Fecha de clase:", fechas_validas, format_func=lambda x: etiquetas_fechas[x])

        if fecha_str in df_historial.columns:
            valores_previos = dict(zip(df_historial['Alumno'], df_historial[fecha_str]))
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

        df_editado = st.data_editor(
            df_view,
            column_config={
                "Alumno": st.column_config.TextColumn("Alumno", disabled=True),
                "Asistencia": st.column_config.SelectboxColumn("Asistencia", options=["✅ Presente", "🟡 Retardo", "🔴 Falta"], required=True),
                "Faltas Reales": st.column_config.NumberColumn("Faltas", disabled=True),
                "Retardos": st.column_config.NumberColumn("Retardos", disabled=True),
                "Faltas Efectivas": st.column_config.NumberColumn("Efectivas", disabled=True),
                "Derecho Examen": st.column_config.TextColumn("Derecho", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            key=f"ed_{materia}_{grupo}_{fecha_str}"
        )

        if st.button("💾 Guardar Asistencia", type="primary"):
            with st.spinner(f"Guardando asistencia del {fecha_str}..."):
                doc = gc.open(FILE_ASISTENCIA)
                try:
                    ws = doc.worksheet(nombre_pestana)
                except gspread.exceptions.WorksheetNotFound:
                    ws = doc.add_worksheet(title=nombre_pestana, rows="100", cols="50")
                    ws.append_row(["Alumno"])

                df_actualizado = df_historial.copy()
                al_existentes = df_actualizado['Alumno'].tolist() if 'Alumno' in df_actualizado.columns else []
                nuevos = [a for a in alumnos if a not in al_existentes]
                if nuevos:
                    df_nuevos = pd.DataFrame({"Alumno": nuevos})
                    df_actualizado = pd.concat([df_actualizado, df_nuevos], ignore_index=True).sort_values('Alumno').reset_index(drop=True)

                mapeo_asist = dict(zip(df_editado['Alumno'], df_editado['Asistencia']))
                df_actualizado[fecha_str] = df_actualizado['Alumno'].map(mapeo_asist)
                df_actualizado = df_actualizado.fillna("")

                datos_matriz = [df_actualizado.columns.values.tolist()] + df_actualizado.values.tolist()
                ws.update(values=datos_matriz, range_name="A1")
                
                leer_datos.clear()
                st.success(f"✅ Asistencia registrada correctamente.")
                time.sleep(1)
                st.rerun()

    # ========================================================
    # MODO 2: Vista Histórica
    # ========================================================
    else:
        st.markdown(f"### 📈 Historial de Asistencia: {grupo} ({materia})")
        if df_historial.empty or len(columnas_fechas) == 0:
            st.info("Sin registros de asistencia acumulados.")
            return

        df_mostrar = pd.DataFrame({"Alumno": df_historial["Alumno"]})
        df_mostrar["Derecho Examen"] = df_mostrar["Alumno"].map(derecho_examen_dict)
        df_mostrar["Faltas Efectivas"] = df_mostrar["Alumno"].map(faltas_efectivas_dict)
        df_mostrar["Faltas Reales"] = df_mostrar["Alumno"].map(faltas_dict)
        df_mostrar["Retardos"] = df_mostrar["Alumno"].map(retardos_dict)
        
        for col in columnas_fechas:
            df_mostrar[col] = df_historial[col]
        
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Descargar Matriz CSV",
            df_mostrar.to_csv(index=False).encode('utf-8-sig'),
            f"Asistencia_{materia}_{grupo}.csv",
            mime="text/csv"
        )