# calculadora.py
import pandas as pd

def format_calif(val):
    """Asigna el color del semáforo a la calificación final"""
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def calcular_calificacion_progresiva(df_historial):
    """
    Calcula el descuento progresivo basándose en reincidencias POR DÍA/SESIÓN.
    Reglas por día:
    - Leve: 1ra del día (-0.2), 2da del día (-0.4), 3ra+ del día (-0.5)
    - Medio: (-0.5)
    - Grave: 1ra del día (-1.0), 2da del día (-1.2), 3ra+ (-1.5)
    - Crítica: Siempre (-5.0)
    """
    if df_historial.empty:
        return 10.0, 0.0

    df_calculo = df_historial.copy()
    
    # Extraemos únicamente el día calendario (YYYY-MM-DD) para agrupar por sesión
    if 'Fecha' in df_calculo.columns:
        df_calculo['Dia_Sesion'] = pd.to_datetime(df_calculo['Fecha'], errors='coerce').dt.date
    else:
        df_calculo['Dia_Sesion'] = 'Dia_Unico'
        
    total_descuento = 0.0
    
    # 🔄 Evaluamos día por día: cada día nuevo reinicia el conteo de reincidencias
    for dia, df_dia in df_calculo.groupby('Dia_Sesion'):
        conteo_dia = {"Leve": 0, "Medio": 0, "Grave": 0, "Crítica": 0}
        
        # Ordenamos cronológicamente dentro del mismo día
        if 'Fecha' in df_dia.columns:
            df_dia = df_dia.sort_values('Fecha')
            
        for _, row in df_dia.iterrows():
            semaforo = str(row.get('Es_Grave', ''))
            
            if "Leve" in semaforo:
                conteo_dia["Leve"] += 1
                if conteo_dia["Leve"] == 1: 
                    total_descuento += 0.2
                elif conteo_dia["Leve"] == 2: 
                    total_descuento += 0.4
                else: 
                    total_descuento += 0.5
                    
            elif "Medio" in semaforo:
                conteo_dia["Medio"] += 1
                total_descuento += 0.5
                
            elif "Grave" in semaforo:
                conteo_dia["Grave"] += 1
                if conteo_dia["Grave"] == 1: 
                    total_descuento += 1.0
                elif conteo_dia["Grave"] == 2: 
                    total_descuento += 1.2
                else: 
                    total_descuento += 1.5
                    
            elif "Crítica" in semaforo:
                conteo_dia["Crítica"] += 1
                total_descuento += 5.0

    # La calificación nunca puede ser menor a 0.0
    calificacion_final = max(0.0, 10.0 - total_descuento)
    
    return calificacion_final, total_descuento