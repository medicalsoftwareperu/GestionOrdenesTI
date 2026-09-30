import os
import re
import sqlite3
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from datetime import datetime
import json
import hashlib
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from functools import wraps

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
app.secret_key = os.getenv('FLASK_SECRET_KEY') or os.urandom(32)

# Credenciales de inicio de sesión leídas de forma segura desde variables de entorno
TI_USER = os.getenv('TI_USERNAME', 'admin')
TI_PASS = os.getenv('TI_PASSWORD')
CONTA_USER = os.getenv('CONTA_USERNAME', 'conta')
CONTA_PASS = os.getenv('CONTA_PASSWORD')
MKT_USER = os.getenv('MARKETING_USERNAME', 'marketing')
MKT_PASS = os.getenv('MARKETING_PASSWORD')
MANT_USER = os.getenv('MANT_USERNAME', 'mantenimiento')
MANT_PASS = os.getenv('MANT_PASSWORD')

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
    conn = sqlite3.connect(DB_PATH, timeout=30)
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
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS reservas_documentos (
            token TEXT PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            tipo TEXT NOT NULL,
            empresa TEXT NOT NULL DEFAULT '',
            numero INTEGER NOT NULL,
            usuario TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            huella TEXT,
            creado TEXT NOT NULL,
            UNIQUE(tipo, empresa, numero)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS guardados_pendientes (
            id TEXT PRIMARY KEY,
            plan TEXT NOT NULL
        )
    ''')

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

    # Conservar la lista que Mantenimiento veía antes de separar sus proveedores.
    # La copia se realiza una sola vez y no reemplaza proveedores propios existentes.
    conn.execute('CREATE TABLE IF NOT EXISTS migraciones_sistema '
                 '(id TEXT PRIMARY KEY, fecha TEXT NOT NULL)')
    migracion = 'separar_proveedores_mantenimiento_v1'
    if not conn.execute('SELECT 1 FROM migraciones_sistema WHERE id = ?', (migracion,)).fetchone():
        columnas = ('nombre, ruc, direccion, contacto, cuenta_soles, cci, cuenta_dolares, '
                    'banco, contacto_nombre, contacto_telefono')
        conn.execute(f'INSERT OR IGNORE INTO proveedores_maint ({columnas}) '
                     f'SELECT {columnas} FROM proveedores')
        conn.execute('INSERT INTO migraciones_sistema (id, fecha) VALUES (?, ?)',
                     (migracion, datetime.now().isoformat()))

    conn.commit()



def sincronizar_contadores_con_disco():
    with bloqueo_documentos():
        recuperar_guardados_pendientes()
        carpetas = {'compras': CARPETA_COMPRAS, 'bajas': CARPETA_BAJAS,
                    'pagos': CARPETA_PAGOS, 'servicios': CARPETA_SERVICIOS,
                    'mantenimiento': CARPETA_MANTENIMIENTO}
        conn = get_db_connection()
        try:
            for tipo, carpeta in carpetas.items():
                numeros = [int(match.group(1)) for nombre in os.listdir(carpeta)
                           if (match := re.search(r'-([0-9]+)\.pdf$', nombre))]
                siguiente = max(numeros, default=0) + 1
                conn.execute('INSERT INTO contadores (tipo, valor) VALUES (?, ?) '
                             'ON CONFLICT(tipo) DO UPDATE SET valor = MAX(valor, excluded.valor)',
                             (tipo, siguiente))
            conn.commit()
        finally:
            conn.close()

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
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE contadores SET valor = valor + 1 WHERE tipo = ?', (tipo,))
        row = conn.execute('SELECT valor FROM contadores WHERE tipo = ?', (tipo,)).fetchone()
        conn.commit()
        return row['valor'] if row else 2
    finally:
        conn.close()


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


# --- GUARDADO CONSISTENTE ---
@contextmanager
def bloqueo_documentos():
    # El mismo bloqueo funciona entre hilos y procesos, incluido IIS/Windows.
    archivo = open(os.path.join(CARPETA_HISTORIAL, '.documentos.lock'), 'a+b')
    adquirido = False
    try:
        archivo.seek(0, os.SEEK_END)
        if archivo.tell() == 0:
            archivo.write(b'\0')
            archivo.flush()
        limite = time.monotonic() + 30
        while not adquirido:
            try:
                if os.name == 'nt':
                    import msvcrt
                    archivo.seek(0)
                    msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                adquirido = True
            except OSError:
                if time.monotonic() >= limite:
                    raise TimeoutError('Hay otro documento guardándose. Intenta nuevamente.')
                time.sleep(0.05)
        yield
    finally:
        if adquirido:
            if os.name == 'nt':
                import msvcrt
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
        archivo.close()


def documentos_bloqueados(funcion):
    @wraps(funcion)
    def protegida(*args, **kwargs):
        try:
            with bloqueo_documentos():
                recuperar_guardados_pendientes()
                return funcion(*args, **kwargs)
        except TimeoutError as error:
            return jsonify({'success': False, 'message': str(error)}), 503
    return protegida


def restaurar_plan_guardado(plan):
    for archivo in plan['archivos']:
        if archivo['respaldo']:
            # Si ya se restauró antes de una interrupción, el respaldo no estará.
            if os.path.exists(archivo['respaldo']):
                os.replace(archivo['respaldo'], archivo['destino'])
        elif os.path.exists(archivo['destino']):
            os.remove(archivo['destino'])


def recuperar_guardados_pendientes():
    conn = get_db_connection()
    try:
        for row in conn.execute('SELECT id, plan FROM guardados_pendientes').fetchall():
            plan = json.loads(row['plan'])
            restaurar_plan_guardado(plan)
            conn.execute('DELETE FROM guardados_pendientes WHERE id = ?', (row['id'],))
            conn.commit()
            shutil.rmtree(plan['temporal'], ignore_errors=True)
    finally:
        conn.close()


def guardar_archivo_recuperable(destino, contenido):
    """Publicar un archivo completo bajo bloqueo_documentos y recuperar un reinicio."""
    conn = get_db_connection()
    temporal = None
    registrado = False
    terminado = False
    restaurado = False
    try:
        temporal = tempfile.mkdtemp(prefix='.guardado-', dir=CARPETA_HISTORIAL)
        preparado = os.path.join(temporal, os.path.basename(destino))
        with open(preparado, 'wb') as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        respaldo = preparado + '.anterior' if os.path.exists(destino) else None
        if respaldo:
            shutil.copy2(destino, respaldo)
        plan = {'temporal': temporal, 'archivos': [
            {'destino': destino, 'preparado': preparado, 'respaldo': respaldo}]}
        operacion = uuid.uuid4().hex
        conn.execute('INSERT INTO guardados_pendientes (id, plan) VALUES (?, ?)',
                     (operacion, json.dumps(plan)))
        registrado = True
        conn.commit()
        os.replace(preparado, destino)
        conn.execute('DELETE FROM guardados_pendientes WHERE id = ?', (operacion,))
        conn.commit()
        terminado = True
    except Exception:
        conn.rollback()
        if registrado:
            try:
                restaurar_plan_guardado(plan)
                conn.execute('DELETE FROM guardados_pendientes WHERE id = ?', (operacion,))
                conn.commit()
                restaurado = True
            except Exception:
                app.logger.exception('Recuperación pendiente; se conservan diario y respaldo')
        raise
    finally:
        conn.close()
        if temporal and (terminado or restaurado or not registrado):
            shutil.rmtree(temporal, ignore_errors=True)


# Recuperar una operación interrumpida por un reinicio antes de atender usuarios.
with bloqueo_documentos():
    recuperar_guardados_pendientes()

# Ejecutar sincronización al inicio
try:
    sincronizar_contadores_con_disco()
except Exception as sync_err:
    print("Error sincronizando contadores al inicio:", sync_err)



def persistir_datos_documento(conn, tipo, nombre, metadata, texto_busqueda):
    conn.execute('DELETE FROM items_pdf WHERE nombre_archivo = ?', (nombre,))
    if texto_busqueda.strip():
        conn.execute('INSERT INTO items_pdf (nombre_archivo, contenido) VALUES (?, ?)',
                     (nombre, texto_busqueda))
    if tipo != 'bajas' and (metadata.get('razon_social') or '').strip():
        conn.execute('INSERT INTO mis_empresas (razon_social, ruc, direccion) VALUES (?, ?, ?) '
                     'ON CONFLICT(razon_social) DO UPDATE SET ruc = excluded.ruc, direccion = excluded.direccion',
                     (metadata['razon_social'].strip(), (metadata.get('ruc') or '').strip(),
                      (metadata.get('direccion') or '').strip()))


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
@documentos_bloqueados
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
@documentos_bloqueados
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
@documentos_bloqueados
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
@documentos_bloqueados
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
        contenido = archivo_pdf.read()
        if not contenido.startswith(b'%PDF-'):
            return jsonify({'success': False, 'message': 'El archivo recibido no es un PDF válido'}), 400
        guardar_archivo_recuperable(ruta_guardado, contenido)
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
@documentos_bloqueados
def vincular_oc():
    rol = session.get('rol', 'sistemas')
    if rol != 'contabilidad':
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
        
    data = request.get_json(silent=True)
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
            
        guardar_archivo_recuperable(ruta_json,
            json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8'))
            
        return jsonify({'success': True, 'message': 'Vínculo actualizado exitosamente'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al actualizar vínculo: {str(e)}'}), 500

@app.route('/get_metadata/<tipo>/<nombre>')
@documentos_bloqueados
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

@app.route('/reservar_documento', methods=['POST'])
@documentos_bloqueados
def reservar_documento():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Datos no válidos'}), 400
    tipo = data.get('tipo')
    if not isinstance(tipo, str):
        return jsonify({'success': False, 'message': 'Tipo no válido'}), 400
    configuracion = configuracion_documento(tipo)
    if not configuracion or session.get('rol') != configuracion[0]:
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    nombre = data.get('nombre', '')
    empresa = data.get('empresa', '')
    if not isinstance(empresa, str):
        return jsonify({'success': False, 'message': 'Empresa no válida'}), 400
    try:
        validar_nombre_documento(tipo, nombre)
    except ValueError:
        return jsonify({'success': False, 'message': 'Nombre no válido'}), 400
    recuperar_guardados_pendientes()
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        grupo = normalizar_nombre_empresa(empresa) if tipo == 'pagos' else ''
        if tipo == 'pagos':
            siguiente = obtener_siguiente_voucher_por_empresa(empresa)
        else:
            numeros = [int(match.group(1)) for f in os.listdir(configuracion[1])
                       if (match := re.search(r'-([0-9]+)\.pdf$', f))]
            row = conn.execute('SELECT valor FROM contadores WHERE tipo = ?', (tipo,)).fetchone()
            siguiente = max(max(numeros, default=0) + 1, row['valor'] if row else 1)
        reservado = conn.execute('SELECT MAX(numero) FROM reservas_documentos WHERE tipo = ? AND empresa = ?',
                                 (tipo, grupo)).fetchone()[0]
        siguiente = max(siguiente, (reservado or 0) + 1)
        prefijo_fecha = nombre.rsplit('-', 1)[0]
        while True:
            asignado = f'{prefijo_fecha}-{siguiente:04d}.pdf'
            validar_nombre_documento(tipo, asignado)
            if not documento_existe(tipo, asignado) and not conn.execute(
                    'SELECT 1 FROM reservas_documentos WHERE nombre = ?', (asignado,)).fetchone():
                break
            siguiente += 1
        token = uuid.uuid4().hex
        conn.execute('INSERT INTO reservas_documentos (token, nombre, tipo, empresa, numero, usuario, creado) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (token, asignado, tipo, grupo, siguiente, session['usuario'], datetime.now().isoformat()))
        conn.commit()
        numero = re.search(r'([0-9]+-[0-9]+)\.pdf$', asignado).group(1)
        return jsonify({'success': True, 'nombre': asignado, 'numero': numero, 'reserva': token})
    except Exception:
        conn.rollback()
        app.logger.exception('No se pudo reservar el documento')
        return jsonify({'success': False, 'message': 'No se pudo reservar el número. Intenta nuevamente.'}), 500
    finally:
        conn.close()


@app.route('/guardar_pdf', methods=['POST'])
@documentos_bloqueados
def guardar_pdf():
    if 'pdf' not in request.files:
        return jsonify({'success': False, 'message': 'No se recibió ningún archivo'}), 400
    archivo_pdf = request.files['pdf']
    nombre = archivo_pdf.filename
    edit_mode = request.form.get('edit_mode', 'false') == 'true'
    tipo = next((tipo for prefijo, tipo in {'OC_': 'compras', 'BAJA_': 'bajas', 'OP_': 'pagos',
                'OS_': 'servicios', 'OCM_': 'mantenimiento'}.items()
                if isinstance(nombre, str) and nombre.startswith(prefijo)), None)
    configuracion = configuracion_documento(tipo)
    if not configuracion:
        return jsonify({'success': False, 'message': 'Tipo o nombre de documento no válido'}), 400
    if session.get('rol') != configuracion[0]:
        return jsonify({'success': False, 'message': 'Acceso no autorizado para este tipo de documento'}), 403
    try:
        validar_nombre_documento(tipo, nombre, permitir_historico=edit_mode)
        if edit_mode and not documento_existe(tipo, nombre):
            return jsonify({'success': False, 'message': 'Documento original no encontrado para editar'}), 404
        carpeta = configuracion[2] if edit_mode else configuracion[1]
        ruta_pdf = ruta_documento_segura(carpeta, nombre)
        ruta_json = ruta_documento_segura(carpeta, nombre[:-4] + '.json')
        metadata = json.loads(request.form.get('metadata', ''))
        items = json.loads(request.form.get('items', '[]'))
        if not isinstance(metadata, dict) or not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
            raise ValueError('Metadatos o ítems no válidos')
        if 'items' in metadata and (not isinstance(metadata['items'], list) or
                                    any(not isinstance(i, dict) for i in metadata['items'])):
            raise ValueError('Ítems de edición no válidos')
        for campo in ['razon_social', 'ruc', 'direccion']:
            if metadata.get(campo) is not None and not isinstance(metadata.get(campo), str):
                raise ValueError('Datos de empresa no válidos')
        campos = ('detalle', 'comprobante') if tipo == 'pagos' else ('servicio',) if tipo == 'servicios' else ('desc', 'marca', 'modelo')
        if any(i.get(campo) is not None and not isinstance(i.get(campo), str) for i in items for campo in campos):
            raise ValueError('Términos de búsqueda no válidos')
        texto_busqueda = ' '.join(' '.join(i.get(campo) or '' for campo in campos) for i in items).lower()
        contenido_pdf = archivo_pdf.read()
        if not contenido_pdf.startswith(b'%PDF-'):
            raise ValueError('El archivo recibido no es un PDF válido')
        token = request.form.get('reserva', '')
        huella = hashlib.sha256(contenido_pdf + json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()
                                + json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Documento o metadatos no válidos. No se guardaron cambios.'}), 400

    recuperar_guardados_pendientes()
    conn = get_db_connection()
    temporal = None
    plan = None
    registrado = False
    terminado = False
    restaurado = False
    try:
        conn.execute('BEGIN IMMEDIATE')
        reserva = conn.execute('SELECT * FROM reservas_documentos WHERE token = ?', (token,)).fetchone() if token else None
        if token and (not reserva or reserva['usuario'] != session['usuario'] or reserva['nombre'] != nombre or
                      reserva['tipo'] != tipo or edit_mode or (tipo == 'pagos' and reserva['empresa'] !=
                      normalizar_nombre_empresa(metadata.get('razon_social') or ''))):
            return jsonify({'success': False, 'message': 'Reserva de documento no válida'}), 400
        if reserva and reserva['estado'] == 'guardado':
            if reserva['huella'] == huella:
                return jsonify({'success': True, 'message': 'Documento guardado exitosamente', 'nombre': nombre})
            return jsonify({'success': False, 'message': 'La reserva ya se utilizó para otro contenido'}), 409
        if not edit_mode and (os.path.exists(ruta_pdf) or os.path.exists(ruta_json) or
                (not token and conn.execute('SELECT 1 FROM reservas_documentos WHERE nombre = ?', (nombre,)).fetchone())):
            return jsonify({'success': False, 'message': f'Ya existe o está reservado el documento "{nombre}". '
                            'Recarga la página para crear otro documento o edita el existente.'}), 409
        if edit_mode and tipo == 'pagos':
            anterior = ruta_metadatos_documento(tipo, nombre)
            if os.path.isfile(anterior):
                with open(anterior, encoding='utf-8') as f:
                    referencia = json.load(f).get('orden_compra_referencia')
                if referencia:
                    metadata['orden_compra_referencia'] = referencia
        # Preparar ambos archivos antes de sustituir cualquier documento existente.
        temporal = tempfile.mkdtemp(prefix='.guardado-', dir=CARPETA_HISTORIAL)
        archivos = []
        for destino, contenido in [(ruta_pdf, contenido_pdf), (ruta_json,
                json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8'))]:
            preparado = os.path.join(temporal, os.path.basename(destino))
            with open(preparado, 'wb') as f:
                f.write(contenido)
                f.flush()
                os.fsync(f.fileno())
            respaldo = preparado + '.anterior' if os.path.exists(destino) else None
            if respaldo:
                shutil.copy2(destino, respaldo)
            archivos.append({'destino': destino, 'preparado': preparado, 'respaldo': respaldo})
        plan = {'temporal': temporal, 'archivos': archivos}
        operacion = uuid.uuid4().hex
        # El diario persiste antes de publicar archivos; permite recuperar un reinicio abrupto.
        conn.execute('INSERT INTO guardados_pendientes (id, plan) VALUES (?, ?)',
                     (operacion, json.dumps(plan)))
        conn.commit()
        registrado = True
        conn.execute('BEGIN IMMEDIATE')
        for archivo in archivos:
            os.replace(archivo['preparado'], archivo['destino'])
        persistir_datos_documento(conn, tipo, nombre, metadata, texto_busqueda)
        if not edit_mode:
            siguiente = int(re.search(r'-([0-9]+)\.pdf$', nombre).group(1)) + 1
            conn.execute('UPDATE contadores SET valor = MAX(valor, ?) WHERE tipo = ?', (siguiente, tipo))
        if reserva:
            conn.execute("UPDATE reservas_documentos SET estado = 'guardado', huella = ? WHERE token = ?", (huella, token))
        conn.execute('DELETE FROM guardados_pendientes WHERE id = ?', (operacion,))
        conn.commit()
        terminado = True
        return jsonify({'success': True, 'message': 'Documento guardado exitosamente', 'nombre': nombre})
    except Exception:
        conn.rollback()
        app.logger.exception('Error al guardar el documento; recuperando la versión anterior')
        try:
            if registrado:
                restaurar_plan_guardado(plan)
                conn.execute('DELETE FROM guardados_pendientes WHERE id = ?', (operacion,))
                conn.commit()
            restaurado = True
        except Exception:
            app.logger.exception('Recuperación pendiente; se conserva el diario y los respaldos')
        return jsonify({'success': False, 'message': 'No se pudo completar el guardado. '
                        'Tus datos siguen en el formulario; intenta nuevamente.'}), 500
    finally:
        conn.close()
        if temporal and (terminado or restaurado or not registrado):
            shutil.rmtree(temporal, ignore_errors=True)


# --- RUTAS DE BASE DE DATOS ---
@app.route('/get_mis_empresas')
def get_mis_empresas():
    conn = get_db_connection()
    empresas = conn.execute('SELECT * FROM mis_empresas ORDER BY razon_social ASC').fetchall()
    conn.close()
    return jsonify([dict(e) for e in empresas])

def tabla_proveedores_por_rol(rol):
    return {'sistemas': 'proveedores', 'contabilidad': 'proveedores_conta',
            'marketing': 'proveedores_mkt', 'mantenimiento': 'proveedores_maint'}.get(rol)


@app.route('/get_proveedores')
def get_proveedores():
    table = tabla_proveedores_por_rol(session.get('rol'))
    if not table:
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
    conn = get_db_connection()
    proveedores = conn.execute(f'SELECT * FROM {table} ORDER BY nombre ASC').fetchall()
    conn.close()
    return jsonify([dict(p) for p in proveedores])

@app.route('/guardar_proveedor', methods=['POST'])
def guardar_proveedor():
    table = tabla_proveedores_por_rol(session.get('rol'))
    if not table:
        return jsonify({'success': False, 'message': 'Acceso no autorizado'}), 403
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

def tipos_documentos_por_rol(rol):
    return [tipo for tipo in ('compras', 'bajas', 'pagos', 'servicios', 'mantenimiento')
            if configuracion_documento(tipo)[0] == rol]


def documentos_visibles_por_rol(rol):
    # Comprobar el área, el nombre y la existencia real; no basta con el índice SQLite.
    documentos = {}
    for tipo in tipos_documentos_por_rol(rol):
        for carpeta in configuracion_documento(tipo)[1:3]:
            for nombre in os.listdir(carpeta):
                if not nombre.endswith('.pdf'):
                    continue
                try:
                    validar_nombre_documento(tipo, nombre, permitir_historico=True)
                    if os.path.isfile(ruta_documento_segura(carpeta, nombre)):
                        documentos[nombre] = tipo
                except ValueError:
                    continue
    return documentos


def mapeo_documentos_por_rol(campo, rol):
    documentos = documentos_visibles_por_rol(rol)
    mapeo = {}
    for tipo in tipos_documentos_por_rol(rol):
        # Conservar la prioridad de la información editada sobre la original.
        for carpeta in configuracion_documento(tipo)[1:3]:
            for nombre in os.listdir(carpeta):
                if not nombre.endswith('.json'):
                    continue
                nombre_pdf = nombre[:-5] + '.pdf'
                if documentos.get(nombre_pdf) != tipo:
                    continue
                try:
                    ruta = ruta_documento_segura(carpeta, nombre)
                    with open(ruta, encoding='utf-8') as archivo:
                        datos = json.load(archivo)
                    valor = datos.get(campo)
                    if valor:
                        mapeo[nombre_pdf] = valor
                except (OSError, ValueError, AttributeError):
                    continue
    return mapeo


@app.route('/get_mapeo_proveedores')
@documentos_bloqueados
def get_mapeo_proveedores():
    return jsonify(mapeo_documentos_por_rol('prov_nombre', session.get('rol')))


@app.route('/get_mapeo_emisores')
@documentos_bloqueados
def get_mapeo_emisores():
    return jsonify(mapeo_documentos_por_rol('razon_social', session.get('rol')))


@app.route('/buscar_archivos')
@documentos_bloqueados
def buscar_archivos():
    rol = session.get('rol')
    tipos = tipos_documentos_por_rol(rol)
    if not tipos:
        return jsonify([])
    q = request.args.get('q', '').lower()
    patrones = [configuracion_documento(tipo)[3].split('_', 1)[0] + '_*.pdf' for tipo in tipos]
    filtros = ' OR '.join('nombre_archivo GLOB ?' for _ in patrones)
    conn = get_db_connection()
    try:
        resultados = conn.execute('SELECT DISTINCT nombre_archivo FROM items_pdf '
            f'WHERE contenido LIKE ? AND ({filtros})', (f'%{q}%', *patrones)).fetchall()
    finally:
        conn.close()
    documentos = documentos_visibles_por_rol(rol)
    return jsonify([r['nombre_archivo'] for r in resultados if r['nombre_archivo'] in documentos])

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
@documentos_bloqueados
def get_siguiente_voucher():
    empresa = request.args.get('empresa', '').strip()
    siguiente = obtener_siguiente_voucher_por_empresa(empresa)
    year = datetime.now().year
    voucher_formateado = f"{year}-{siguiente:04d}"
    return jsonify({'success': True, 'voucher': voucher_formateado, 'numero': siguiente})

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)