import pandas as pd

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
# Cargar el archivo CSV
df = pd.read_csv(CSV_FILENAME)

# Calcular la diferencia entre los tiempos
df['diferencia_tiempo'] = df['tiempo'].diff()

# Eliminar la primera fila que tendrá un valor NaN
diferencias = df['diferencia_tiempo'].dropna()

# Calcular estadísticas básicas
media = diferencias.mean()
mediana = diferencias.median()
desviacion_estandar = diferencias.std()
minimo = diferencias.min()
maximo = diferencias.max()
count = diferencias.count()

print("Resultados Servidor")
print(f"Media: {media}")
print(f"Mediana: {mediana}")
print(f"Desviación estándar: {desviacion_estandar}")
print(f"Mínimo: {minimo}")
print(f"Máximo: {maximo}")
print(f"Cuantos: {count}")
