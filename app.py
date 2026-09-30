import os
import re
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
MKT_USER = os.getenv('MARKETING_USERNAME', 'marketing')
MKT_PASS = os.getenv('MARKETING_PASSWORD', 'marketing2026')
MANT_USER = os.getenv('MANT_USERNAME', 'mantenimiento')
MANT_PASS = os.getenv('MANT_PASSWORD', 'mantenimiento2026')

USER_CREDENTIALS = {
    TI_USER: TI_PASS,
    CONTA_USER: CONTA_PASS,
    MKT_USER: MKT_PASS,
    MANT_USER: MANT_PASS
}

USER_ROLES = {
    TI_USER: 'sistemas',
    CONTA_USER: 'contabilidad',
    MKT_USER: 'marketing',
    MANT_USER: 'mantenimiento'
}

# --- CONFIGURACIÓN DE CARPETAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_HISTORIAL = os.path.join(BASE_DIR, 'historial')

CARPETA_COMPRAS = os.path.join(CARPETA_HISTORIAL, 'compras')
CARPETA_BAJAS = os.path.join(CARPETA_HISTORIAL, 'bajas')
CARPETA_PAGOS = os.path.join(CARPETA_HISTORIAL, 'pagos')
CARPETA_SERVICIOS = os.path.join(CARPETA_HISTORIAL, 'servicios')
CARPETA_MANTENIMIENTO = os.path.join(CARPETA_HISTORIAL, 'mantenimiento')
CARPETA_COMPRAS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'compras_editadas')
CARPETA_BAJAS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'bajas_editadas')
CARPETA_PAGOS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'pagos_editadas')
CARPETA_SERVICIOS_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'servicios_editadas')
CARPETA_MANTENIMIENTO_EDITADAS = os.path.join(CARPETA_HISTORIAL, 'mantenimiento_editadas')
CARPETA_FACTURAS = os.path.join(CARPETA_HISTORIAL, 'facturas_oc')

os.makedirs(CARPETA_COMPRAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS, exist_ok=True)
os.makedirs(CARPETA_PAGOS, exist_ok=True)
os.makedirs(CARPETA_SERVICIOS, exist_ok=True)
os.makedirs(CARPETA_MANTENIMIENTO, exist_ok=True)
os.makedirs(CARPETA_COMPRAS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_BAJAS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_PAGOS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_SERVICIOS_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_MANTENIMIENTO_EDITADAS, exist_ok=True)
os.makedirs(CARPETA_FACTURAS, exist_ok=True)

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
        CREATE TABLE IF NOT EXISTS proveedores_conta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT,
            contacto TEXT,
            cuenta_soles TEXT,
            cci TEXT,
            cuenta_dolares TEXT,
            banco TEXT DEFAULT 'BCP',
            contacto_nombre TEXT DEFAULT '',
            contacto_telefono TEXT DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS proveedores_mkt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT,
            contacto TEXT,
            cuenta_soles TEXT,
            cci TEXT,
            cuenta_dolares TEXT,
            banco TEXT DEFAULT 'BCP',
            contacto_nombre TEXT DEFAULT '',
            contacto_telefono TEXT DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS proveedores_maint (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            ruc TEXT,
            direccion TEXT,
            contacto TEXT,
            cuenta_soles TEXT,
            cci TEXT,
            cuenta_dolares TEXT,
            banco TEXT DEFAULT 'BCP',
            contacto_nombre TEXT DEFAULT '',
            contacto_telefono TEXT DEFAULT ''
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
    ''', ('ONCO TEST S.A.C.', '20547642512', 'Av. Gral Alvarez de Arenales Nro. 630'))
    conn.execute('''
        INSERT OR IGNORE INTO mis_empresas (razon_social, ruc, direccion)
        VALUES (?, ?, ?)
    ''', ('MEDICAL DIAGNOSTIC S.A.C.', '20511431752', 'AV. ARENALES NRO. 630 LIMA - LIMA - JESUS MARIA'))
    
    # Crear e inicializar tabla de contadores
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contadores (
            tipo TEXT PRIMARY KEY,
            valor INTEGER
        )
    ''')
    cursor = conn.cursor()
    for tipo_contador in ['compras', 'bajas', 'pagos', 'servicios', 'mantenimiento']:
        cursor.execute('SELECT COUNT(*) FROM contadores WHERE tipo = ?', (tipo_contador,))
        if cursor.fetchone()[0] == 0:
            conn.execute('INSERT INTO contadores (tipo, valor) VALUES (?, ?)', (tipo_contador, 1))
    
    # Agregar columnas dinámicamente si no existen
    for query in [
        'ALTER TABLE proveedores ADD COLUMN banco TEXT DEFAULT "BCP"',
        'ALTER TABLE proveedores ADD COLUMN contacto_nombre TEXT DEFAULT ""',
        'ALTER TABLE proveedores ADD COLUMN contacto_telefono TEXT DEFAULT ""',
        'ALTER TABLE proveedores_conta ADD COLUMN cci TEXT DEFAULT ""',
        'ALTER TABLE proveedores_conta ADD COLUMN banco TEXT DEFAULT "BCP"',
        'ALTER TABLE proveedores_conta ADD COLUMN contacto_nombre TEXT DEFAULT ""',
        'ALTER TABLE proveedores_conta ADD COLUMN contacto_telefono TEXT DEFAULT ""'
    ]:
        try:
            conn.execute(query)
        except sqlite3.OperationalError:
            pass

    conn.commit()



def sincronizar_contadores_con_disco():
    # Sincronizar compras
    if os.path.exists(CARPETA_COMPRAS):
        max_val = 0
        for f in os.listdir(CARPETA_COMPRAS):
            if f.startswith('OC_') and f.endswith('.pdf'):
                match = re.search(r'-(\d+)\.pdf$', f)
                if match:
                    val = int(match.group(1))
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            with get_db_connection() as conn_db:
                conn_db.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('compras', max_val + 1))
                conn_db.commit()

    # Sincronizar bajas
    if os.path.exists(CARPETA_BAJAS):
        max_val = 0
        for f in os.listdir(CARPETA_BAJAS):
            if f.startswith('BAJA_') and f.endswith('.pdf'):
                match = re.search(r'-(\d+)\.pdf$', f)
                if match:
                    val = int(match.group(1))
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            with get_db_connection() as conn_db:
                conn_db.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('bajas', max_val + 1))
                conn_db.commit()

    # Sincronizar pagos
    if os.path.exists(CARPETA_PAGOS):
        max_val = 0
        for f in os.listdir(CARPETA_PAGOS):
            if f.startswith('OP_') and f.endswith('.pdf'):
                match = re.search(r'-(\d+)\.pdf$', f)
                if match:
                    val = int(match.group(1))
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            with get_db_connection() as conn_db:
                conn_db.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('pagos', max_val + 1))
                conn_db.commit()

    # Sincronizar servicios
    if os.path.exists(CARPETA_SERVICIOS):
        max_val = 0
        for f in os.listdir(CARPETA_SERVICIOS):
            if f.startswith('OS_') and f.endswith('.pdf'):
                match = re.search(r'-(\d+)\.pdf$', f)
                if match:
                    val = int(match.group(1))
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            with get_db_connection() as conn_db:
                conn_db.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('servicios', max_val + 1))
                conn_db.commit()

    # Sincronizar mantenimiento
    if os.path.exists(CARPETA_MANTENIMIENTO):
        max_val = 0
        for f in os.listdir(CARPETA_MANTENIMIENTO):
            if f.startswith('OCM_') and f.endswith('.pdf'):
                match = re.search(r'-(\d+)\.pdf$', f)
                if match:
                    val = int(match.group(1))
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            with get_db_connection() as conn_db:
                conn_db.execute('INSERT OR REPLACE INTO contadores (tipo, valor) VALUES (?, ?)', ('mantenimiento', max_val + 1))
                conn_db.commit()

# Ejecutar sincronización al inicio
try:
    sincronizar_contadores_con_disco()
except Exception as sync_err:
    print("Error sincronizando contadores al inicio:", sync_err)

# --- LÓGICA DE CONTADORES ---
def obtener_siguiente_numero(tipo):
    try:
        sincronizar_contadores_con_disco()
    except Exception as sync_err:
        print("Error al sincronizar contadores durante consulta:", sync_err)
        
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


# --- VALIDACIÓN Y PERMISOS DE DOCUMENTOS ---
def configuracion_documento(tipo):
    configuraciones = {
        'compras': ('sistemas', CARPETA_COMPRAS, CARPETA_COMPRAS_EDITADAS, r'OC_[0-9]{8}-[0-9]{4,12}\.pdf', r'OC_[0-9]{1,12}-[0-9]{1,12}\.pdf'),
        'bajas': ('sistemas', CARPETA_BAJAS, CARPETA_BAJAS_EDITADAS, r'BAJA_[0-9]{8}-[0-9]{4,12}\.pdf', r'BAJA_[0-9]{1,12}-[0-9]{1,12}\.pdf'),
        'pagos': ('contabilidad', CARPETA_PAGOS, CARPETA_PAGOS_EDITADAS, r'OP_(?:[A-Za-z]{1,12}_)?[0-9]{4}-[0-9]{4,12}\.pdf', r'OP_(?:[A-Za-z]{1,12}_)?[0-9]{1,12}-[0-9]{1,12}\.pdf'),
        'servicios': ('marketing', CARPETA_SERVICIOS, CARPETA_SERVICIOS_EDITADAS, r'OS_[0-9]{8}-[0-9]{4,12}\.pdf', r'OS_[0-9]{1,12}-[0-9]{1,12}\.pdf'),
        'mantenimiento': ('mantenimiento', CARPETA_MANTENIMIENTO, CARPETA_MANTENIMIENTO_EDITADAS, r'OCM_[0-9]{8}-[0-9]{4,12}\.pdf', r'OCM_[0-9]{1,12}-[0-9]{1,12}\.pdf')
    }
    return configuraciones.get(tipo)


def ruta_documento_segura(carpeta, nombre):
    # Rechazar rutas en lugar de renombrarlas: conservar la identidad del documento.
    if not isinstance(nombre, str) or not nombre or len(nombre) > 128:
        raise ValueError('Nombre de archivo no válido')
    if '/' in nombre or '\\' in nombre or '..' in nombre or any(ord(c) < 32 for c in nombre):
        raise ValueError('Nombre de archivo no válido')
    base = os.path.realpath(carpeta)
    historial = os.path.realpath(CARPETA_HISTORIAL)
    ruta = os.path.realpath(os.path.join(base, nombre))
    if os.path.commonpath([historial, base]) != historial or os.path.commonpath([base, ruta]) != base:
        raise ValueError('Ruta de archivo no válida')
    return ruta


def documento_existe(tipo, nombre):
    configuracion = configuracion_documento(tipo)
    if not configuracion:
        return False
    return any(os.path.isfile(ruta_documento_segura(carpeta, nombre)) for carpeta in configuracion[1:3])


def validar_nombre_documento(tipo, nombre, permitir_historico=False):
    configuracion = configuracion_documento(tipo)
    if not configuracion or not isinstance(nombre, str):
        raise ValueError('Tipo o nombre de documento no válido')
    # Validar ambas ubicaciones, incluidas posibles rutas simbólicas.
    for carpeta in configuracion[1:3]:
        ruta_documento_segura(carpeta, nombre)
    if re.fullmatch(configuracion[3], nombre):
        return
    # Los formatos antiguos solo se admiten si ya existen en su área.
    if permitir_historico and re.fullmatch(configuracion[4], nombre) and documento_existe(tipo, nombre):
        return
    raise ValueError('Nombre de documento no válido')


def ruta_metadatos_documento(tipo, nombre):
    configuracion = configuracion_documento(tipo)
    json_nombre = nombre[:-4] + '.json'
    ruta_editada = ruta_documento_segura(configuracion[2], json_nombre)
    if os.path.isfile(ruta_editada):
        return ruta_editada
    return ruta_documento_segura(configuracion[1], json_nombre)


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
        
    # Recuperar siempre el rol de la cuenta, también para cookies antiguas.
    rol = USER_ROLES.get(session['usuario'])
    if not rol:
        session.clear()
        return redirect(url_for('login'))
    session['rol'] = rol

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
        try:
            validar_nombre_documento('compras', edit, permitir_historico=True)
            if not documento_existe('compras', edit):
                return 'Documento no encontrado', 404
        except ValueError:
            return 'Referencia de documento no válida', 400
        numero_oc = edit.replace('OC_', '').replace('.pdf', '')
        return render_template('orden_de_compra.html', numero_oc=numero_oc, edit_mode=True, edit_filename=edit)
    
    numero_actual = obtener_siguiente_numero('compras')
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('orden_de_compra.html', numero_oc=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/servicios')
def servicios():
    if session.get('rol') != 'marketing':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        try:
            validar_nombre_documento('servicios', edit, permitir_historico=True)
            if not documento_existe('servicios', edit):
                return 'Documento no encontrado', 404
        except ValueError:
            return 'Referencia de documento no válida', 400
        numero_os = edit.replace('OS_', '').replace('.pdf', '')
        return render_template('orden_de_servicio.html', numero_os=numero_os, edit_mode=True, edit_filename=edit)
    
    numero_actual = obtener_siguiente_numero('servicios')
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('orden_de_servicio.html', numero_os=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/mantenimiento')
def mantenimiento():
    if session.get('rol') != 'mantenimiento':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        try:
            validar_nombre_documento('mantenimiento', edit, permitir_historico=True)
            if not documento_existe('mantenimiento', edit):
                return 'Documento no encontrado', 404
        except ValueError:
            return 'Referencia de documento no válida', 400
        numero_oc = edit.replace('OCM_', '').replace('.pdf', '')
        return render_template('orden_de_compra_mantenimiento.html', numero_oc=numero_oc, edit_mode=True, edit_filename=edit)
    
    numero_actual = obtener_siguiente_numero('mantenimiento')
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    numero_formateado = f"{fecha_hoy}-{numero_actual:04d}" 
    return render_template('orden_de_compra_mantenimiento.html', numero_oc=numero_formateado, edit_mode=False, edit_filename='')

@app.route('/bajas')
def bajas():
    if session.get('rol') != 'sistemas':
        return redirect(url_for('index'))
    edit = request.args.get('edit', '')
    if edit:
        try:
            validar_nombre_documento('bajas', edit, permitir_historico=True)
            if not documento_existe('bajas', edit):
                return 'Documento no encontrado', 404
        except ValueError:
            return 'Referencia de documento no válida', 400
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
        try:
            validar_nombre_documento('pagos', edit, permitir_historico=True)
            if not documento_existe('pagos', edit):
                return 'Documento no encontrado', 404
        except ValueError:
            return 'Referencia de documento no válida', 400
        match = re.search(r'OP_(?:[A-Za-z]+_)?(.+)\.pdf$', edit)
        numero_op = match.group(1) if match else edit.replace('OP_', '').replace('.pdf', '')
        return render_template('orden_de_pago.html', numero_op=numero_op, edit_mode=True, edit_filename=edit)
        
    return render_template('orden_de_pago.html', numero_op='', edit_mode=False, edit_filename='')

@app.route('/historial')
def historial():
    rol = session.get('rol', 'sistemas')
    archivos_compras = []
    archivos_bajas = []
    archivos_pagos = []
    archivos_servicios = []
    mapeo_facturas = {}
    
    mapeo_vinculos_oc = {}
    mapeo_facturas_oc = {}
    
    def obtener_numero_orden(filename):
        match = re.search(r'-(\d+)\.pdf$', filename)
        if match:
            return int(match.group(1))
        return 0
    
    archivos_mantenimiento = []
    
    if rol == 'sistemas':
        if os.path.exists(CARPETA_COMPRAS):
            archivos_compras = sorted([f for f in os.listdir(CARPETA_COMPRAS) if f.endswith('.pdf')], key=lambda f: (-obtener_numero_orden(f), f))
            for f in archivos_compras:
                factura_nombre = f"Factura_{f}"
                mapeo_facturas[f] = os.path.exists(os.path.join(CARPETA_FACTURAS, factura_nombre))
        if os.path.exists(CARPETA_BAJAS):
            archivos_bajas = sorted([f for f in os.listdir(CARPETA_BAJAS) if f.endswith('.pdf')], key=lambda f: (-obtener_numero_orden(f), f))
    elif rol == 'contabilidad':
        if os.path.exists(CARPETA_PAGOS):
            archivos_pagos = sorted([f for f in os.listdir(CARPETA_PAGOS) if f.endswith('.pdf')], key=lambda f: (-obtener_numero_orden(f), f))
            for f in archivos_pagos:
                json_nombre = f.replace('.pdf', '.json')
                ruta_json = os.path.join(CARPETA_PAGOS_EDITADAS, json_nombre)
                if not os.path.exists(ruta_json):
                    ruta_json = os.path.join(CARPETA_PAGOS, json_nombre)
                if os.path.exists(ruta_json):
                    try:
                        with open(ruta_json, 'r', encoding='utf-8') as file_json:
                            meta = json.load(file_json)
                            oc_ref = meta.get('orden_compra_referencia')
                            if oc_ref:
                                mapeo_vinculos_oc[f] = oc_ref
                                factura_nombre = f"Factura_{oc_ref}"
                                mapeo_facturas_oc[oc_ref] = os.path.exists(os.path.join(CARPETA_FACTURAS, factura_nombre))
                    except Exception:
                        pass
    elif rol == 'marketing':
        if os.path.exists(CARPETA_SERVICIOS):
            archivos_servicios = sorted([f for f in os.listdir(CARPETA_SERVICIOS) if f.endswith('.pdf')], key=lambda f: (-obtener_numero_orden(f), f))
    elif rol == 'mantenimiento':
        if os.path.exists(CARPETA_MANTENIMIENTO):
            archivos_mantenimiento = sorted([f for f in os.listdir(CARPETA_MANTENIMIENTO) if f.endswith('.pdf')], key=lambda f: (-obtener_numero_orden(f), f))
            
    return render_template('historial.html', compras=archivos_compras, bajas=archivos_bajas, pagos=archivos_pagos, servicios=archivos_servicios, mantenimiento=archivos_mantenimiento, mapeo_facturas=mapeo_facturas, mapeo_vinculos_oc=mapeo_vinculos_oc, mapeo_facturas_oc=mapeo_facturas_oc)


# --- RUTAS DE ARCHIVOS (PDF) ---
@app.route('/ver_pdf/<tipo>/<nombre>')
def ver_pdf(tipo, nombre):
    configuracion = configuracion_documento(tipo)
    if not configuracion or session.get('rol') != configuracion[0]:
        return "Archivo no encontrado o acceso no autorizado", 404
    try:
        validar_nombre_documento(tipo, nombre, permitir_historico=True)
        for carpeta in (configuracion[2], configuracion[1]):
            ruta = ruta_documento_segura(carpeta, nombre)
            if os.path.isfile(ruta):
                return send_from_directory(carpeta, nombre)
    except ValueError:
        return "Nombre de archivo no válido", 400
    return "Archivo no encontrado", 404

@app.route('/ver_factura/<nombre>')
def ver_factura(nombre):
    rol = session.get('rol')
    if rol not in ['sistemas', 'contabilidad']:
        return "Acceso no autorizado", 403
    try:
        if not nombre.startswith('Factura_'):
            raise ValueError('Nombre de factura no válido')
        validar_nombre_documento('compras', nombre[len('Factura_'):], permitir_historico=True)
        ruta_documento_segura(CARPETA_FACTURAS, nombre)
    except ValueError:
        return 'Nombre de factura no válido', 400
    return send_from_directory(CARPETA_FACTURAS, nombre, as_attachment=False)

@app.route('/subir_factura', methods=['POST'])
def subir_factura():
    rol = session.get('rol', 'sistemas')
    if rol != 'sistemas':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
        
    if 'pdf' not in request.files:
        return jsonify({'success': False, 'message': 'No se recibió ningún archivo'}), 400
        
    archivo_pdf = request.files['pdf']
    nombre_oc = request.form.get('nombre_oc', '')
    
    try:
        validar_nombre_documento('compras', nombre_oc, permitir_historico=True)
        if not documento_existe('compras', nombre_oc):
            return jsonify({'success': False, 'message': 'Orden de compra no encontrada'}), 404
        factura_nombre = f"Factura_{nombre_oc}"
        ruta_guardado = ruta_documento_segura(CARPETA_FACTURAS, factura_nombre)
    except ValueError:
        return jsonify({'success': False, 'message': 'Referencia de orden de compra no válida'}), 400
        
    if archivo_pdf.filename == '':
        return jsonify({'success': False, 'message': 'Archivo vacío'}), 400
        
    
    try:
        archivo_pdf.save(ruta_guardado)
        return jsonify({'success': True, 'message': 'Factura subida exitosamente'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al guardar el archivo: {str(e)}'}), 500

@app.route('/get_lista_compras')
def get_lista_compras():
    rol = session.get('rol', 'sistemas')
    if rol != 'contabilidad':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    
    compras = []
    if os.path.exists(CARPETA_COMPRAS):
        compras = [f for f in os.listdir(CARPETA_COMPRAS) if f.endswith('.pdf')]
    return jsonify(compras)


@app.route('/vincular_oc', methods=['POST'])
def vincular_oc():
    rol = session.get('rol', 'sistemas')
    if rol != 'contabilidad':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
        
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Datos no válidos'}), 400
    nombre_op = data.get('nombre_op', '')
    nombre_oc = data.get('nombre_oc', '')
    if not isinstance(nombre_oc, str):
        return jsonify({'success': False, 'message': 'Referencia de orden de compra no válida'}), 400
    nombre_oc = nombre_oc.strip()
    try:
        validar_nombre_documento('pagos', nombre_op, permitir_historico=True)
        if not documento_existe('pagos', nombre_op):
            return jsonify({'success': False, 'message': 'Orden de pago no encontrada'}), 404
        if nombre_oc:
            validar_nombre_documento('compras', nombre_oc, permitir_historico=True)
            if not documento_existe('compras', nombre_oc):
                return jsonify({'success': False, 'message': 'Orden de compra no encontrada'}), 404
        ruta_json = ruta_metadatos_documento('pagos', nombre_op)
    except ValueError:
        return jsonify({'success': False, 'message': 'Referencia de documento no válida'}), 400

    if not os.path.exists(ruta_json):
        return jsonify({'success': False, 'message': 'No se encontraron metadatos para esta orden de pago'}), 404
        
    try:
        with open(ruta_json, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            
        if nombre_oc:
            metadata['orden_compra_referencia'] = nombre_oc
        else:
            metadata.pop('orden_compra_referencia', None)
            
        with open(ruta_json, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        return jsonify({'success': True, 'message': 'Vínculo actualizado exitosamente'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al actualizar vínculo: {str(e)}'}), 500

@app.route('/get_metadata/<tipo>/<nombre>')
def get_metadata(tipo, nombre):
    configuracion = configuracion_documento(tipo)
    if not configuracion or session.get('rol') != configuracion[0]:
        return jsonify({'success': False, 'message': 'Tipo no válido o acceso no autorizado'}), 403
    try:
        validar_nombre_documento(tipo, nombre, permitir_historico=True)
        ruta = ruta_metadatos_documento(tipo, nombre)
    except ValueError:
        return jsonify({'success': False, 'message': 'Nombre de documento no válido'}), 400

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

    tipos_por_prefijo = {'OC_': 'compras', 'BAJA_': 'bajas', 'OP_': 'pagos', 'OS_': 'servicios', 'OCM_': 'mantenimiento'}
    tipo = next((tipo for prefijo, tipo in tipos_por_prefijo.items()
                 if isinstance(nombre_archivo, str) and nombre_archivo.startswith(prefijo)), None)
    configuracion = configuracion_documento(tipo)
    if not configuracion:
        return jsonify({'success': False, 'message': 'Tipo o nombre de documento no válido'}), 400
    if session.get('rol') != configuracion[0]:
        return jsonify({'success': False, 'message': 'Acceso no autorizado para este tipo de documento'}), 403
    try:
        validar_nombre_documento(tipo, nombre_archivo, permitir_historico=edit_mode)
        if edit_mode and not documento_existe(tipo, nombre_archivo):
            return jsonify({'success': False, 'message': 'Documento original no encontrado para editar'}), 404
        carpeta = configuracion[2] if edit_mode else configuracion[1]
        ruta_guardado = ruta_documento_segura(carpeta, nombre_archivo)
        ruta_json = ruta_documento_segura(carpeta, nombre_archivo[:-4] + '.json')
    except ValueError:
        return jsonify({'success': False, 'message': 'Nombre o ruta de documento no válido'}), 400
    if not edit_mode:
        incrementar_numero(tipo)

    # Evitar sobreescrituras accidentales al crear un nuevo documento
    if not edit_mode and os.path.exists(ruta_guardado):
        return jsonify({
            'success': False, 
            'message': f'Ya existe un documento con el nombre "{nombre_archivo}" en el historial. Por favor, usa otro número correlativo o edita el documento existente.'
        })
        
    # Guardar PDF
    archivo_pdf.save(ruta_guardado)

    # Guardar JSON de Metadatos
    if metadata_json:
        try:
            metadata_dict = json.loads(metadata_json)
            with open(ruta_json, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, ensure_ascii=False, indent=2)

            # Guardar automáticamente la Razón Social del emisor si es una Orden de Compra, Pago o Servicio
            if nombre_archivo.startswith('OC_') or nombre_archivo.startswith('OP_') or nombre_archivo.startswith('OS_') or nombre_archivo.startswith('OCM_'):
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
        elif nombre_archivo.startswith('OS_'):
            texto_busqueda = " ".join([f"{i.get('servicio','')}" for i in items]).lower()
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
    rol = session.get('rol', 'sistemas')
    if rol == 'contabilidad':
        table = 'proveedores_conta'
    elif rol == 'marketing':
        table = 'proveedores_mkt'
    else:
        table = 'proveedores'
    conn = get_db_connection()
    proveedores = conn.execute(f'SELECT * FROM {table} ORDER BY nombre ASC').fetchall()
    conn.close()
    return jsonify([dict(p) for p in proveedores])

@app.route('/guardar_proveedor', methods=['POST'])
def guardar_proveedor():
    rol = session.get('rol', 'sistemas')
    if rol == 'contabilidad':
        table = 'proveedores_conta'
    elif rol == 'marketing':
        table = 'proveedores_mkt'
    else:
        table = 'proveedores'
    data = request.json
    try:
        with get_db_connection() as conn:
            conn.execute(f'''
                INSERT OR REPLACE INTO {table} (nombre, ruc, direccion, contacto, cuenta_soles, cci, cuenta_dolares, banco, contacto_nombre, contacto_telefono)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    data.get('nombre'), 
                    data.get('ruc'), 
                    data.get('direccion', ''), 
                    data.get('contacto', ''), 
                    data.get('cuenta_soles', ''),   
                    data.get('cci', ''),            
                    data.get('cuenta_dolares', ''),
                    data.get('banco', 'BCP'),
                    data.get('contacto_nombre', ''),
                    data.get('contacto_telefono', '')
                ))
            conn.execute('COMMIT')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/get_mapeo_proveedores')
def get_mapeo_proveedores():
    mapeo = {}
    for carpeta in [CARPETA_COMPRAS, CARPETA_COMPRAS_EDITADAS, CARPETA_BAJAS, CARPETA_BAJAS_EDITADAS, CARPETA_PAGOS, CARPETA_PAGOS_EDITADAS, CARPETA_SERVICIOS, CARPETA_SERVICIOS_EDITADAS, CARPETA_MANTENIMIENTO, CARPETA_MANTENIMIENTO_EDITADAS]:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if f.endswith('.json'):
                    try:
                        with open(os.path.join(carpeta, f), 'r', encoding='utf-8') as file:
                            data = json.load(file)
                            prov = data.get('prov_nombre')
                            if prov:
                                mapeo[f.replace('.json', '.pdf')] = prov
                    except Exception:
                        pass
    return jsonify(mapeo)

@app.route('/get_mapeo_emisores')
def get_mapeo_emisores():
    mapeo = {}
    for carpeta in [CARPETA_COMPRAS, CARPETA_COMPRAS_EDITADAS, CARPETA_BAJAS, CARPETA_BAJAS_EDITADAS, CARPETA_PAGOS, CARPETA_PAGOS_EDITADAS, CARPETA_SERVICIOS, CARPETA_SERVICIOS_EDITADAS, CARPETA_MANTENIMIENTO, CARPETA_MANTENIMIENTO_EDITADAS]:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if f.endswith('.json'):
                    try:
                        with open(os.path.join(carpeta, f), 'r', encoding='utf-8') as file:
                            data = json.load(file)
                            emisor = data.get('razon_social')
                            if emisor:
                                mapeo[f.replace('.json', '.pdf')] = emisor
                    except Exception:
                        pass
    return jsonify(mapeo)

@app.route('/buscar_archivos')
def buscar_archivos():
    q = request.args.get('q', '').lower()
    conn = get_db_connection()
    resultados = conn.execute('SELECT DISTINCT nombre_archivo FROM items_pdf WHERE contenido LIKE ?', (f'%{q}%',)).fetchall()
    conn.close()
    return jsonify([r['nombre_archivo'] for r in resultados])

def normalizar_nombre_empresa(name):
    if not name:
        return ''
    import unicodedata
    text = name.lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^a-z0-9]', '', text)
    text = text.replace('sac', '').replace('srl', '').replace('group', '').replace('ventures', '').replace('consulting', '')
    return text.strip()

def obtener_siguiente_voucher_por_empresa(empresa_name):
    empresa_norm = normalizar_nombre_empresa(empresa_name)
    
    valores_inicio = {
        'medicaldiagnostic': 11,
        'oncotest': 12,
        'medicaloxxo': 14,
        'medicalmed': 10,
        'jrglobal': 8,
        'jl': 4
    }
    
    inicio = 1
    for k, v in valores_inicio.items():
        if k in empresa_norm:
            inicio = v
            break
            
    max_val = 0
    if os.path.exists(CARPETA_PAGOS):
        for f in os.listdir(CARPETA_PAGOS):
            if f.startswith('OP_') and f.endswith('.json'):
                try:
                    with open(os.path.join(CARPETA_PAGOS, f), 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        prov_empresa = data.get('razon_social', '')
                        if normalizar_nombre_empresa(prov_empresa) == empresa_norm:
                            match = re.search(r'-(\d+)\.json$', f)
                            if match:
                                val = int(match.group(1))
                                if val > max_val:
                                    max_val = val
                except Exception:
                    pass
                    
    siguiente = max(inicio, max_val + 1)
    return siguiente

@app.route('/get_siguiente_voucher')
def get_siguiente_voucher():
    empresa = request.args.get('empresa', '').strip()
    siguiente = obtener_siguiente_voucher_por_empresa(empresa)
    year = datetime.now().year
    voucher_formateado = f"{year}-{siguiente:04d}"
    return jsonify({'success': True, 'voucher': voucher_formateado, 'numero': siguiente})

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)