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
CONTA_USER = os.getenv('CONTA_USERNAME', 'conta')
CONTA_PASS = os.getenv('CONTA_PASSWORD', 'conta123')

USER_CREDENTIALS = {
    TI_USER: TI_PASS,
    CONTA_USER: CONTA_PASS
}

USER_ROLES = {
    TI_USER: 'sistemas',
    CONTA_USER: 'contabilidad'
}

# --- CONFIGURACIÓN DE CARPETAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_HISTORIAL = os.path.join(BASE_DIR, 'historial')

CARPETA_COMPRAS = os.path.join(CARPETA_HISTORIAL, 'compras')
CARPETA_BAJAS = os.path.join(CARPETA_HISTORIAL, 'bajas')
CARPETA_PAGOS = os.path.join(CARPETA_HISTORIAL, 'pagos')
CARPETA_COMPRAS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'compras_editadas')
CARPETA_BAJAS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'bajas_editadas')
CARPETA_PAGOS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'pagos_editadas')

os.makedirs(CARPETA_COMPRAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS, exist_ok=True)
os.makedirs(CARPETA_PAGOS, exist_ok=True)
os.makedirs(CARPETA_COMPRAS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_PAGOS_EDITADAS, exist_ok=True)

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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mis_empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            razon_social TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT
        )
    ''')
    # Insertar valores por defecto si no existen
    conn.execute('''
        INSERT OR IGNORE INTO mis_empresas (razon_social, ruc, direccion)
        VALUES (?, ?, ?)
    ''', ('MEDICAL DENT DIGITAL', '20553850330', 'AV. ARENALES NRO. 630 LIMA - LIMA - JESUS MARIA'))
    conn.execute('''
        INSERT OR IGNORE INTO mis_empresas (razon_social, ruc, direccion)
        VALUES (?, ?, ?)
    ''', ('ONCO TEST S.A.C.', '20547642512', 'Av. Gral Alvarez de Arenales Nro. 630'))
    
    # Crear e inicializar tabla de contadores
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contadores (
            tipo TEXT PRIMARY KEY,
            valor INTEGER
        )
    ''')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM contadores')
    if cursor.fetchone()[0] == 0:
        val_compras = 1
        if os.path.exists(ARCHIVO_CONTADOR):
            try:
                with open(ARCHIVO_CONTADOR, 'r') as f:
                    val_compras = int(f.read().strip())
            except Exception:
                pass
        conn.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('compras', val_compras))
        
        val_bajas = 1
        if os.path.exists(ARCHIVO_CONTADOR_BAJA):
            try:
                with open(ARCHIVO_CONTADOR_BAJA, 'r') as f:
                    val_bajas = int(f.read().strip())
            except Exception:
                pass
        conn.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('bajas', val_bajas))
    
    # Agregar columnas dinámicamente si no existen
    for query in [
        'ALTER TABLE proveedores ADD COLUMN banco TEXT DEFAULT "BCP"',
        'ALTER TABLE proveedores ADD COLUMN contacto_nombre TEXT DEFAULT ""',
        'ALTER TABLE proveedores ADD COLUMN contacto_telefono TEXT DEFAULT ""'
    ]:
        try:
            conn.execute(query)
        except sqlite3.OperationalError:
            pass

    # Inicializar contador de pagos si no existe
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM contadores WHERE tipo = ?', ('pagos',))
    if cursor.fetchone()[0] == 0:
        conn.execute('INSERT INTO contadores (tipo, valor) VALUES (?, ?)', ('pagos', 1))
            
    conn.commit()



# --- LÓGICA DE CONTADORES ---
def obtener_siguiente_numero(tipo):
    conn = get_db_connection()
    row = conn.execute('SELECT valor FROM contadores WHERE tipo = ?', (tipo,)).fetchone()
    conn.close()
    if row:
        return row['valor']
    return 1

def incrementar_numero(tipo):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT valor FROM contadores WHERE tipo = ?', (tipo,))
        row = cursor.fetchone()
        if row:
            nuevo = row[0] + 1
            conn.execute('UPDATE contadores SET valor = ? WHERE tipo = ?', (nuevo, tipo))
        else:
            nuevo = 2
            conn.execute('INSERT INTO contadores (tipo, valor) VALUES (?, ?)', (tipo, nuevo))
        conn.commit()
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
        
    # Si ya inició sesión pero no tiene rol asignado en la sesión (por cookies antiguas), asignarlo
    if 'rol' not in session:
        session['rol'] = USER_ROLES.get(session['usuario'], 'sistemas')

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
            session['rol'] = USER_ROLES.get(username, 'sistemas')
            return redirect(url_for('index'))
        else:
            error = 'Usuario o contraseña incorrectos.'
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    session.pop('rol', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compras')
def compras():
    if session.get('rol') != 'sistemas':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        numero_oc = edit.replace('OC_', '').replace('.pdf', '')
        return render_template('orden_de_compra.html', numero_oc=numero_oc, edit_mode=True, edit_filename=edit)
    
    numero_actual = obtener_siguiente_numero('compras')
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('orden_de_compra.html', numero_oc=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/bajas')
def bajas():
    if session.get('rol') != 'sistemas':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        numero_baja = edit.replace('BAJA_', '').replace('.pdf', '')
        return render_template('guia_de_baja.html', numero_baja=numero_baja, edit_mode=True, edit_filename=edit)
        
    numero_actual = obtener_siguiente_numero('bajas')
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('guia_de_baja.html', numero_baja=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/pagos')
def pagos():
    if session.get('rol') != 'contabilidad':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        numero_op = edit.replace('OP_', '').replace('.pdf', '')
        return render_template('orden_de_pago.html', numero_op=numero_op, edit_mode=True, edit_filename=edit)
        
    numero_actual = obtener_siguiente_numero('pagos')
    numero_formateado = f"00{datetime.now().year}-{numero_actual:06d}"
    return render_template('orden_de_pago.html', numero_op=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/historial')
def historial():
    rol = session.get('rol', 'sistemas')
    archivos_compras = []
    archivos_bajas = []
    archivos_pagos = []
    
    if rol == 'sistemas':
        if os.path.exists(CARPETA_COMPRAS):
            archivos_compras = sorted([f for f in os.listdir(CARPETA_COMPRAS) if f.endswith('.pdf')], reverse=True)
        if os.path.exists(CARPETA_BAJAS):
            archivos_bajas = sorted([f for f in os.listdir(CARPETA_BAJAS) if f.endswith('.pdf')], reverse=True)
    elif rol == 'contabilidad':
        if os.path.exists(CARPETA_PAGOS):
            archivos_pagos = sorted([f for f in os.listdir(CARPETA_PAGOS) if f.endswith('.pdf')], reverse=True)
            
    return render_template('historial.html', compras=archivos_compras, bajas=archivos_bajas, pagos=archivos_pagos)


# --- RUTAS DE ARCHIVOS (PDF) ---
@app.route('/ver_pdf/<tipo>/<nombre>')
def ver_pdf(tipo, nombre):
    rol = session.get('rol', 'sistemas')
    if tipo == 'compras' and rol == 'sistemas':
        return send_from_directory(CARPETA_COMPRAS, nombre)
    elif tipo == 'bajas' and rol == 'sistemas':
        return send_from_directory(CARPETA_BAJAS, nombre)
    elif tipo == 'pagos' and rol == 'contabilidad':
        return send_from_directory(CARPETA_PAGOS, nombre)
    return "Archivo no encontrado o acceso no autorizado", 404

@app.route('/get_metadata/<tipo>/<nombre>')
def get_metadata(tipo, nombre):
    json_nombre = nombre.replace('.pdf', '.json')
    rol = session.get('rol', 'sistemas')
    
    if tipo == 'compras' and rol == 'sistemas':
        ruta_editada = os.path.join(CARPETA_COMPRAS_EDITADAS, json_nombre)
        if os.path.exists(ruta_editada):
            ruta = ruta_editada
        else:
            ruta = os.path.join(CARPETA_COMPRAS, json_nombre)
    elif tipo == 'bajas' and rol == 'sistemas':
        ruta_editada = os.path.join(CARPETA_BAJAS_EDITADAS, json_nombre)
        if os.path.exists(ruta_editada):
            ruta = ruta_editada
        else:
            ruta = os.path.join(CARPETA_BAJAS, json_nombre)
    elif tipo == 'pagos' and rol == 'contabilidad':
        ruta_editada = os.path.join(CARPETA_PAGOS_EDITADAS, json_nombre)
        if os.path.exists(ruta_editada):
            ruta = ruta_editada
        else:
            ruta = os.path.join(CARPETA_PAGOS, json_nombre)
    else:
        return jsonify({'success': False, 'message': 'Tipo no válido o acceso no autorizado'}), 400
    
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify({'success': True, 'data': data})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error al leer los metadatos: {str(e)}'}), 500
    else:
        return jsonify({'success': False, 'message': 'No se encontraron metadatos para este archivo'}), 404

@app.route('/guardar_pdf', methods=['POST'])
def guardar_pdf():
    if 'pdf' not in request.files:
        return jsonify({'success': False, 'message': 'No se recibió ningún archivo'})

    archivo_pdf = request.files['pdf']
    nombre_archivo = archivo_pdf.filename
    edit_mode = request.form.get('edit_mode', 'false') == 'true'
    metadata_json = request.form.get('metadata', '')

    if nombre_archivo == '':
        return jsonify({'success': False, 'message': 'Nombre de archivo vacío'})

    if nombre_archivo.startswith('OC_'):
        if edit_mode:
            ruta_guardado = os.path.join(CARPETA_COMPRAS_EDITADAS, nombre_archivo)
        else:
            ruta_guardado = os.path.join(CARPETA_COMPRAS, nombre_archivo)
            incrementar_numero('compras')
    elif nombre_archivo.startswith('BAJA_'):
        if edit_mode:
            ruta_guardado = os.path.join(CARPETA_BAJAS_EDITADAS, nombre_archivo)
        else:
            ruta_guardado = os.path.join(CARPETA_BAJAS, nombre_archivo)
            incrementar_numero('bajas')
    elif nombre_archivo.startswith('OP_'):
        if edit_mode:
            ruta_guardado = os.path.join(CARPETA_PAGOS_EDITADAS, nombre_archivo)
        else:
            ruta_guardado = os.path.join(CARPETA_PAGOS, nombre_archivo)
            incrementar_numero('pagos')
    else:
        ruta_guardado = os.path.join(CARPETA_HISTORIAL, nombre_archivo)
    
    # Guardar PDF
    archivo_pdf.save(ruta_guardado)

    # Guardar JSON de Metadatos
    if metadata_json:
        ruta_json = ruta_guardado.replace('.pdf', '.json')
        try:
            metadata_dict = json.loads(metadata_json)
            with open(ruta_json, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)

            # Guardar automáticamente la Razón Social del emisor si es una Orden de Compra o de Pago
            if nombre_archivo.startswith('OC_') or nombre_archivo.startswith('OP_'):
                razon_social = metadata_dict.get('razon_social')
                ruc = metadata_dict.get('ruc')
                direccion = metadata_dict.get('direccion')
                if razon_social and razon_social.strip():
                    try:
                        with get_db_connection() as conn:
                            conn.execute('''
                                INSERT OR REPLACE INTO mis_empresas (razon_social, ruc, direccion)
                                VALUES (?, ?, ?)
                            ''', (razon_social.strip(), (ruc or '').strip(), (direccion or '').strip()))
                            conn.commit()
                    except Exception as db_err:
                        print("Error guardando mi empresa automáticamente:", db_err)
        except Exception as e:
            print("Error al guardar metadatos:", e)

    # Guardar/Actualizar términos de búsqueda
    items_json = request.form.get('items', '[]')
    try:
        items = json.loads(items_json)
        if nombre_archivo.startswith('OP_'):
            texto_busqueda = " ".join([f"{i.get('detalle','')} {i.get('comprobante','')}" for i in items]).lower()
        else:
            texto_busqueda = " ".join([f"{i.get('desc','')} {i.get('marca','')} {i.get('modelo','')}" for i in items]).lower()
        
        with get_db_connection() as conn:
            if edit_mode:
                conn.execute('DELETE FROM items_pdf WHERE nombre_archivo = ?', (nombre_archivo,))
            if texto_busqueda.strip():
                conn.execute('INSERT INTO items_pdf (nombre_archivo, contenido) VALUES (?, ?)', (nombre_archivo, texto_busqueda))
            conn.commit()
    except Exception as e:
        print("Error procesando items:", e)

    return jsonify({'success': True, 'message': 'Documento guardado exitosamente'})


# --- RUTAS DE BASE DE DATOS ---
@app.route('/get_mis_empresas')
def get_mis_empresas():
    conn = get_db_connection()
    empresas = conn.execute('SELECT * FROM mis_empresas ORDER BY razon_social ASC').fetchall()
    conn.close()
    return jsonify([dict(e) for e in empresas])

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
                INSERT OR REPLACE INTO proveedores (nombre, ruc, direccion, contacto, cuenta_soles, cci, cuenta_dolares, banco, contacto_nombre, contacto_telefono)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    data.get('nombre'), 
                    data.get('ruc'), 
                    data.get('direccion'), 
                    data.get('contacto', ''), 
                    data.get('cuenta_soles', ''),   
                    data.get('cci', ''),            
                    data.get('cuenta_dolares', ''),
                    data.get('banco', 'BCP'),
                    data.get('contacto_nombre', ''),
                    data.get('contacto_telefono', '')
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