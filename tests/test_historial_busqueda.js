const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../templates/historial.html'), 'utf8');
const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map(match => match[1]).find(code => code.includes('let mapeoProveedores'));
assert.ok(script, 'Prueba el script real del historial');
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };

function setup() {
    let time = 0, timerId = 0;
    const timers = new Map(), calls = [], events = {}, errors = [];
    const controls = Object.fromEntries(['buscador', 'filtro-proveedor', 'filtro-razon-social'].map(id => [id, {
        value: '', children: [], appendChild(option) { this.children.push(option); }
    }]));
    const items = ['OC_A.pdf', 'OC_B.pdf', 'GB_2026.pdf'].map(name => ({
        name, style: {display: 'flex'}, querySelector: () => ({textContent: name})
    }));
    const context = vm.createContext({
        document: {
            getElementById: id => controls[id] || null,
            querySelectorAll: () => items,
            createElement: () => ({}),
            addEventListener: (name, callback) => { events[name] = callback; }
        },
        AbortController, console: {error: (...args) => errors.push(args)},
        setTimeout: (fn, ms) => { const id = ++timerId; timers.set(id, {at: time + ms, fn}); return id; },
        clearTimeout: id => timers.delete(id),
        fetchSeguro: (url, options = {}) => new Promise((resolve, reject) => {
            calls.push({url, options, resolve: data => resolve({ok: true, json: async () => data}), reject});
        })
    });
    vm.runInContext(script, context);
    return {
        controls, items, calls, context, events, errors,
        run: code => vm.runInContext(code, context),
        advance: async ms => {
            time += ms;
            for (const [id, timer] of [...timers]) if (timer.at <= time) { timers.delete(id); timer.fn(); }
            await flush();
        },
        setMaps: () => vm.runInContext(`mapeoProveedores = {'OC_A.pdf': 'Ácme S.A.C.', 'OC_B.pdf': 'Otro', 'GB_2026.pdf': 'Acme SAC'};
            mapeoEmisores = {'OC_A.pdf': 'Médical S.A.', 'OC_B.pdf': 'Medical SA', 'GB_2026.pdf': 'Otra Empresa'};`, context),
        visible: () => items.filter(item => item.style.display !== 'none').map(item => item.name)
    };
}

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

test('Escritura rápida produce una única búsqueda con el último texto', async () => {
    const env = setup();
    for (const text of ['s', 'ss', 'ssd']) {
        env.controls.buscador.value = text; env.run('programarBusquedaHistorial()'); await env.advance(80);
    }
    assert.equal(env.calls.length, 0);
    await env.advance(169); assert.equal(env.calls.length, 0);
    await env.advance(1); assert.equal(env.calls.length, 1);
    assert.equal(new URL(env.calls[0].url, 'http://localhost').searchParams.get('q'), 'ssd');
});

test('Respuesta vieja no reemplaza resultados nuevos aunque la red ignore abort', async () => {
    const env = setup();
    env.controls.buscador.value = 'viejo'; env.run('filtrarHistorial()');
    env.controls.buscador.value = 'nuevo'; env.run('filtrarHistorial()');
    assert.equal(env.calls[0].options.signal.aborted, true);
    env.calls[1].resolve(['OC_B.pdf']); await flush();
    assert.deepEqual(env.visible(), ['OC_B.pdf']);
    env.calls[0].resolve(['OC_A.pdf']); await flush();
    assert.deepEqual(env.visible(), ['OC_B.pdf']);
});

test('Una tecla invalida la petición anterior antes de vencer los 250 ms', async () => {
    const env = setup();
    env.controls.buscador.value = 'antiguo'; env.run('filtrarHistorial()');
    env.controls.buscador.value = 'nuevo'; env.run('programarBusquedaHistorial()');
    assert.equal(env.calls[0].options.signal.aborted, true);
    env.calls[0].resolve(['OC_A.pdf']); await flush();
    assert.deepEqual(env.visible(), ['OC_A.pdf', 'OC_B.pdf', 'GB_2026.pdf']);
    await env.advance(250); assert.equal(env.calls.length, 2);
});

test('Vaciar texto cancela espera y restaura inmediatamente filtros seleccionados', async () => {
    const env = setup(); env.setMaps();
    env.controls['filtro-proveedor'].value = 'ACME S.A.C.';
    env.controls.buscador.value = 'ssd'; env.run('programarBusquedaHistorial()');
    env.controls.buscador.value = ''; env.run('programarBusquedaHistorial()'); await flush();
    assert.deepEqual(env.visible(), ['OC_A.pdf', 'GB_2026.pdf']);
    await env.advance(1000); assert.equal(env.calls.length, 0);
});

test('Vaciar texto invalida resultado en vuelo y conserva filtro emisor', async () => {
    const env = setup(); env.setMaps();
    env.controls.buscador.value = 'ssd'; env.run('filtrarHistorial()');
    env.controls['filtro-razon-social'].value = 'MEDICAL SA';
    env.controls.buscador.value = ''; env.run('programarBusquedaHistorial()'); await flush();
    assert.deepEqual(env.visible(), ['OC_A.pdf', 'OC_B.pdf']);
    env.calls[0].resolve(['GB_2026.pdf']); await flush();
    assert.deepEqual(env.visible(), ['OC_A.pdf', 'OC_B.pdf']);
});

test('Select filtra inmediatamente combinando texto, proveedor y emisor normalizados', async () => {
    const env = setup(); env.setMaps();
    env.controls.buscador.value = 'ssd'; env.run('programarBusquedaHistorial()');
    env.controls['filtro-proveedor'].value = 'acme sac';
    env.controls['filtro-razon-social'].value = 'MEDICAL S.A.';
    env.run('filtrarHistorial()'); assert.equal(env.calls.length, 1);
    env.calls[0].resolve(['OC_A.pdf', 'OC_B.pdf', 'GB_2026.pdf']); await flush();
    assert.deepEqual(env.visible(), ['OC_A.pdf']);
    await env.advance(500); assert.equal(env.calls.length, 1);
});

test('Nombre de archivo coincide aunque backend no devuelva contenido', async () => {
    const env = setup(); env.controls.buscador.value = '2026'; env.run('filtrarHistorial()');
    env.calls[0].resolve([]); await flush(); assert.deepEqual(env.visible(), ['GB_2026.pdf']);
});

test('Error de petición vieja no altera el resultado vigente', async () => {
    const env = setup();
    env.controls.buscador.value = 'antiguo'; env.run('filtrarHistorial()');
    env.controls.buscador.value = 'actual'; env.run('filtrarHistorial()');
    env.calls[1].resolve(['OC_B.pdf']); await flush();
    env.calls[0].reject(new Error('Fallo de red antiguo')); await flush();
    assert.deepEqual(env.visible(), ['OC_B.pdf']);
});

test('Carga de mapeos reaplica filtro elegido mientras se cargaban datos', async () => {
    const env = setup(); env.events.DOMContentLoaded(); await flush();
    const handled = new Set();
    for (let pass = 0; pass < 12; pass++) {
        for (const call of env.calls) {
            if (handled.has(call)) continue;
            handled.add(call);
            if (call.url.includes('mapeo')) {
                env.controls['filtro-proveedor'].value = 'ACME SAC';
                env.run('filtrarHistorial()');
                call.resolve({proveedores: {'OC_A.pdf': 'Ácme S.A.C.', 'OC_B.pdf': 'Otro'}, emisores: {}});
            } else if (call.url.includes('mis_empresas')) call.resolve([]);
            else if (call.url.includes('get_proveedores')) call.resolve([]);
            else throw new Error('Petición inesperada: ' + call.url);
        }
        await flush();
    }
    assert.ok(env.calls.some(call => call.url.includes('mapeo')), 'Se cargan mapeos');
    assert.deepEqual(env.visible(), ['OC_A.pdf']);
});

(async () => {
    for (const [name, fn] of tests) {
        await fn(); console.log('OK: ' + name);
    }
    console.log(`${tests.length} pruebas del historial satisfactorias.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
