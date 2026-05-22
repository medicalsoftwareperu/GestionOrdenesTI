import os
import sqlite3
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from datetime import datetime
import json

# Intentar cargar variables de entorno desde un archivo .env local de forma manual (sin dependencias de pip)
ruta_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(ruta_env):
    try:
        with open(ruta_env, 'r', encoding='utf-8') as f:
            for linea in f:
                linea = linea.strip()
                # Ignorar líneas vacías y comentarios
                if linea and not linea.startswith('#') and '=' in linea:
                    clave, valor = linea.split('=', 1)
                    os.environ[clave.strip()] = valor.strip()
    except Exception as e:
        print("Error leyendo el archivo .env:", e)

app = Flask(__name__)

# Configurar la clave secreta desde variables de entorno
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'gestion_ordenes_ti_secret_key')

# Credenciales de inicio de sesión leídas de forma segura desde variables de entorno
TI_USER = os.getenv('TI_USERNAME', 'admin')
TI_PASS = os.getenv('TI_PASSWORD', 'sistemas')

USER_CREDENTIALS = {
    TI_USER: TI_PASS
}

# --- CONFIGURACIÓN DE CARPETAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_HISTORIAL = os.path.join(BASE_DIR, 'historial')

CARPETA_COMPRAS = os.path.join(CARPETA_HISTORIAL, 'compras')
CARPETA_BAJAS = os.path.join(CARPETA_HISTORIAL, 'bajas')

os.makedirs(CARPETA_COMPRAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS, exist_ok=True)

ARCHIVO_CONTADOR = os.path.join(BASE_DIR, 'contador_oc.txt')
ARCHIVO_CONTADOR_BAJA = os.path.join(BASE_DIR, 'contador_baja.txt')

# --- CONFIGURACIÓN DE BASE DE DATOS ---
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ¡AQUÍ ES DONDE DEBEN IR LAS CREACIONES DE TABLAS! (Al arrancar la app)
with get_db_connection() as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT,
            contacto TEXT,
            cuenta_soles TEXT,      -- N° CTA. SOLES BCP
            cci TEXT,               -- N° CCI BCP
            cuenta_dolares TEXT     -- N° CTA. DÓLARES BCP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items_pdf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_archivo TEXT,
            contenido TEXT
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

@app.before_request
def verificar_autenticacion():
    # Rutas públicas (no requieren login)
    rutas_publicas = ['login', 'static']
    
    # Si no hay endpoint (ej. 404) o es ruta pública, permitir el acceso
    if not request.endpoint or request.endpoint in rutas_publicas:
        return
        
    # Si no ha iniciado sesión, redirigir al login
    if 'usuario' not in session:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Si ya está logueado, redirigir al index
    if 'usuario' in session:
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session['usuario'] = username
            return redirect(url_for('index'))
        else:
            error = 'Usuario o contraseña incorrectos.'
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compras')
def compras():
    numero_actual = obtener_siguiente_numero(ARCHIVO_CONTADOR)
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('orden_de_compra.html', numero_oc=numero_formateado)

@app.route('/bajas')
def bajas():
    numero_actual = obtener_siguiente_numero(ARCHIVO_CONTADOR_BAJA)
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('guia_de_baja.html', numero_baja=numero_formateado)

@app.route('/historial')
def historial():
    archivos_compras = []
    if os.path.exists(CARPETA_COMPRAS):
        archivos_compras = sorted(os.listdir(CARPETA_COMPRAS), reverse=True)

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

    if nombre_archivo.startswith('OC_'):
        ruta_guardado = os.path.join(CARPETA_COMPRAS, nombre_archivo)
        incrementar_numero(ARCHIVO_CONTADOR)
    elif nombre_archivo.startswith('BAJA_'):
        ruta_guardado = os.path.join(CARPETA_BAJAS, nombre_archivo)
        incrementar_numero(ARCHIVO_CONTADOR_BAJA)
    else:
        ruta_guardado = os.path.join(CARPETA_HISTORIAL, nombre_archivo)
    
    archivo_pdf.save(ruta_guardado)

    items_json = request.form.get('items', '[]')
    try:
        items = json.loads(items_json)
        texto_busqueda = " ".join([f"{i.get('desc','')} {i.get('marca','')} {i.get('modelo','')}" for i in items]).lower()
        
        if texto_busqueda.strip():
            with get_db_connection() as conn:
                conn.execute('INSERT INTO items_pdf (nombre_archivo, contenido) VALUES (?, ?)', (nombre_archivo, texto_busqueda))
                conn.commit()
    except Exception as e:
        print("Error procesando items:", e)

    return jsonify({'success': True, 'message': f'PDF guardado en su carpeta correspondiente'})


# --- RUTAS DE BASE DE DATOS ---
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
                INSERT OR REPLACE INTO proveedores (nombre, ruc, direccion, contacto, cuenta_soles, cci, cuenta_dolares)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (
                    data.get('nombre'), 
                    data.get('ruc'), 
                    data.get('direccion'), 
                    data.get('contacto'), 
                    data.get('cuenta_soles', ''),   
                    data.get('cci', ''),            
                    data.get('cuenta_dolares', '')
                ))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/buscar_archivos')
def buscar_archivos():
    q = request.args.get('q', '').lower()
    conn = get_db_connection()
    resultados = conn.execute('SELECT DISTINCT nombre_archivo FROM items_pdf WHERE contenido LIKE ?', (f'%{q}%',)).fetchall()
    conn.close()
    return jsonify([r['nombre_archivo'] for r in resultados])

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)