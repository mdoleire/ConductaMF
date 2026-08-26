# calculadora.py
import pandas as pd

def format_calif(val):
    """Asigna el color del semáforo a la calificación final"""
    if val >= 9.0: return f"🟢 {val:.1f}"
    if val >= 7.0: return f"🟡 {val:.1f}"
    return f"🔴 {val:.1f}"

def calcular_calificacion_progresiva(df_historial):
    """
    Calcula el descuento progresivo basándose en reincidencias.
    Reglas:
    - Leve: 1ra (-0.2), 2da (-0.4), 3ra+ (-0.5)
    - Grave: 1ra (-1.0), 2da (-1.2), 3ra+ (-1.5)
    - Crítica: Siempre (-5.0)
    """
    if df_historial.empty:
        return 10.0, 0.0

    # Ordenar por fecha para que la línea temporal de reincidencias sea exacta
    if 'Fecha' in df_historial.columns:
        df_historial = df_historial.sort_values('Fecha')
    
    conteo = {"Leve": 0, "Medio": 0, "Grave": 0, "Crítica": 0}
    total_descuento = 0.0
    
    for _, row in df_historial.iterrows():
        semaforo = str(row.get('Es_Grave', ''))
        
        if "Leve" in semaforo:
            conteo["Leve"] += 1
            if conteo["Leve"] == 1: total_descuento += 0.2
            elif conteo["Leve"] == 2: total_descuento += 0.4
            else: total_descuento += 0.5
                
        elif "Grave" in semaforo:
            conteo["Grave"] += 1
            if conteo["Grave"] == 1: total_descuento += 1.0
            elif conteo["Grave"] == 2: total_descuento += 1.2
            else: total_descuento += 1.5
                
        elif "Crítica" in semaforo:
            conteo["Crítica"] += 1
            total_descuento += 5.0
            
        elif "Medio" in semaforo:
            conteo["Medio"] += 1
            total_descuento += 0.5 # Valor fijo temporal para las faltas medias
            
    # La calificación topa en 0.0 (no hay calificaciones negativas)
    calificacion_final = max(0.0, 10.0 - total_descuento)
    
    return calificacion_final, total_descuento