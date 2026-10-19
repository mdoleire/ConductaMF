# inspeccionar_db.py
import sqlite3
import pandas as pd

conn = sqlite3.connect('miraflores.db')

# Consultamos todas las tablas creadas en SQLite
tablas_df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)

print("=" * 50)
print("📊 ESTADO ACTUAL DE MIRAFLORES.DB:")
print("=" * 50)

for nombre_tabla in tablas_df['name']:
    conteo = pd.read_sql(f"SELECT COUNT(*) as total FROM [{nombre_tabla}]", conn)['total'].iloc[0]
    print(f"  📁 {nombre_tabla.ljust(25)} ➔ {conteo} registros")

print("=" * 50)
conn.close()