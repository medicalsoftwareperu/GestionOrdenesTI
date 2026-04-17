import os
import sqlite3 # NUEVO IMPORT PARA LA BASE DE DATOS
from flask import Flask, render_template, request, jsonify, send_from_directory # Movi send_from_directory aquí arriba

app = Flask(__name__)

# --- CONFIGURACIÓN DE CARPETAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_HISTORIAL = os.path.join(BASE_DIR, 'historial')

# Definimos las subcarpetas específicas
CARPETA_COMPRAS = os.path.join(CARPETA_HISTORIAL, 'compras')
CARPETA_BAJAS = os.path.join(CARPETA_HISTORIAL, 'bajas')

# Creamos la estructura completa (esto crea historial, compras y bajas de un solo golpe)
os.makedirs(CARPETA_COMPRAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS, exist_ok=True)

# Tenemos los dos archivos definidos para los contadores
ARCHIVO_CONTADOR = os.path.join(BASE_DIR, 'contador_oc.txt')
ARCHIVO_CONTADOR_BAJA = os.path.join(BASE_DIR, 'contador_baja.txt')

# --- NUEVA CONFIGURACIÓN DE BASE DE DATOS (PROVEEDORES) ---
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Crear la tabla de proveedores si no existe al arrancar la app
with get_db_connection() as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT,
            contacto TEXT,
            telefono TEXT
        )
    ''')


# --- LÓGICA DE CONTADORES ---
def obtener_siguiente_numero(archivo_txt):
    if not os.path.exists(archivo_txt):
        with open(archivo_txt, 'w') as f:
            f.write('1')
        return 1
    with open(archivo_txt, 'r') as f:
        numero = f.read().strip()
        if not numero:
            return 1
        return int(numero)

def incrementar_numero(archivo_txt):
    actual = obtener_siguiente_numero(archivo_txt)
    nuevo = actual + 1
    with open(archivo_txt, 'w') as f:
        f.write(str(nuevo))
    return nuevo


# --- RUTAS PRINCIPALES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compras')
def compras():
    numero_actual = obtener_siguiente_numero(ARCHIVO_CONTADOR)
    numero_formateado = f"000-{numero_actual:04d}" 
    return render_template('orden_de_compra.html', numero_oc=numero_formateado)

@app.route('/bajas')
def bajas():
    numero_actual = obtener_siguiente_numero(ARCHIVO_CONTADOR_BAJA)
    numero_formateado = f"000-{numero_actual:04d}" 
    return render_template('guia_de_baja.html', numero_baja=numero_formateado)

@app.route('/historial')
def historial():
    # Escaneamos la carpeta de compras
    archivos_compras = []
    if os.path.exists(CARPETA_COMPRAS):
        # Listamos archivos y los ordenamos (el más nuevo primero)
        archivos_compras = sorted(os.listdir(CARPETA_COMPRAS), reverse=True)

    # Escaneamos la carpeta de bajas
    archivos_bajas = []
    if os.path.exists(CARPETA_BAJAS):
        archivos_bajas = sorted(os.listdir(CARPETA_BAJAS), reverse=True)

    return render_template('historial.html', compras=archivos_compras, bajas=archivos_bajas)


# --- RUTAS DE ARCHIVOS (PDF) ---
@app.route('/ver_pdf/<tipo>/<nombre>')
def ver_pdf(tipo, nombre):
    if tipo == 'compras':
        return send_from_directory(CARPETA_COMPRAS, nombre)
    elif tipo == 'bajas':
        return send_from_directory(CARPETA_BAJAS, nombre)
    return "Archivo no encontrado", 404

@app.route('/guardar_pdf', methods=['POST'])
def guardar_pdf():
    if 'pdf' not in request.files:
        return jsonify({'success': False, 'message': 'No se recibió ningún archivo'})

    archivo_pdf = request.files['pdf']
    nombre_archivo = archivo_pdf.filename

    if nombre_archivo == '':
        return jsonify({'success': False, 'message': 'Nombre de archivo vacío'})

    # --- LÓGICA DE SEPARACIÓN POR CARPETAS ---
    if nombre_archivo.startswith('OC_'):
        ruta_guardado = os.path.join(CARPETA_COMPRAS, nombre_archivo)
        incrementar_numero(ARCHIVO_CONTADOR)
    elif nombre_archivo.startswith('BAJA_'):
        ruta_guardado = os.path.join(CARPETA_BAJAS, nombre_archivo)
        incrementar_numero(ARCHIVO_CONTADOR_BAJA)
    else:
        # Por si acaso subes algo que no sea OC o BAJA
        ruta_guardado = os.path.join(CARPETA_HISTORIAL, nombre_archivo)
    
    # Guardar el archivo en la subcarpeta elegida
    archivo_pdf.save(ruta_guardado)

    return jsonify({'success': True, 'message': f'PDF guardado en su carpeta correspondiente'})


# --- NUEVAS RUTAS PARA LA BASE DE DATOS (PROVEEDORES) ---
@app.route('/get_proveedores')
def get_proveedores():
    conn = get_db_connection()
    proveedores = conn.execute('SELECT * FROM proveedores ORDER BY nombre ASC').fetchall()
    conn.close()
    return jsonify([dict(p) for p in proveedores])

@app.route('/guardar_proveedor', methods=['POST'])
def guardar_proveedor():
    data = request.json
    try:
        with get_db_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO proveedores (nombre, ruc, direccion, contacto, telefono)
                VALUES (?, ?, ?, ?, ?)''', 
                (data.get('nombre'), data.get('ruc'), data.get('direccion'), data.get('contacto'), data.get('telefono', '')))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)