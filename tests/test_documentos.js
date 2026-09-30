// Ejecutar: node --test tests/test_documentos.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function fixture() {
  const button = { disabled: false }, company = { value: 'Empresa A' };
  const calls = [], alerts = [];
  const context = vm.createContext({ document: {
    querySelectorAll: () => [button], getElementById: () => company
  }, alert: text => alerts.push(text), fetchSeguro: async (url, options) => {
    calls.push({url, body: JSON.parse(options.body)});
    return {ok: true, json: async () => ({success: true, nombre: 'OC_20260930-0002.pdf', numero: '20260930-0002', reserva: 'token'})};
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/documentos.js'), 'utf8'), context);
  return {context, button, company, calls, alerts};
}
test('el contenido de entradas se conserva como texto, sin crear HTML', () => {
  const {context:c} = fixture();
  assert.equal(c.escaparTextoHTML('"/><img src=x onerror=alert(1)> & O\'Brien'), '&quot;/&gt;&lt;img src=x onerror=alert(1)&gt; &amp; O&#39;Brien');
  assert.equal(c.escaparTextoHTML('Equipo 12 / S.A.C.'), 'Equipo 12 / S.A.C.');
  assert.equal(c.escaparTextoHTML(12), '12');
  assert.equal(c.escaparTextoHTML(null), '');
});
test('doble clic se ignora; el fallo libera el botón y permite reintentar', () => {
  const {context:c, button} = fixture();
  assert.equal(c.iniciarGuardadoDocumento(false), true);assert.equal(button.disabled, true);
  assert.equal(c.iniciarGuardadoDocumento(false), false);
  c.finalizarGuardadoDocumento(false, false);assert.equal(button.disabled, false);
  assert.equal(c.iniciarGuardadoDocumento(false), true);
});
test('el éxito evita duplicar una creación y permite continuar editando', () => {
  const {context:c, alerts} = fixture();
  c.iniciarGuardadoDocumento(false);c.finalizarGuardadoDocumento(true, false);
  assert.equal(c.iniciarGuardadoDocumento(false), false);assert.equal(alerts.length, 1);
  assert.equal(c.iniciarGuardadoDocumento(true), true);
});
test('el reintento reutiliza la reserva tanto con el nombre propuesto como con el asignado', async () => {
  const {context:c, calls} = fixture();
  const first = await c.reservarNumeroDocumento('compras', 'OC_20260930-0001.pdf', false);
  c.finalizarGuardadoDocumento(false, false);
  assert.equal(await c.reservarNumeroDocumento('compras', 'OC_20260930-0001.pdf', false), first);
  assert.equal(await c.reservarNumeroDocumento('compras', first.nombre, false), first);
  assert.equal(calls.length, 1);
});
test('cambiar empresa requiere otra reserva; una edición conserva el número sin reservar', async () => {
  const {context:c, calls, company} = fixture();
  await c.reservarNumeroDocumento('compras', 'OC_20260930-0001.pdf', false);
  company.value = 'Empresa B';await c.reservarNumeroDocumento('compras', 'OC_20260930-0001.pdf', false);
  const edited = await c.reservarNumeroDocumento('compras', 'OC_000-0118.pdf', true);
  assert.equal(edited.nombre, 'OC_000-0118.pdf');assert.equal(edited.numero, '000-0118');assert.equal(edited.reserva, '');assert.equal(calls.length, 2);
});
test('una reserva rechazada produce un error y se puede reintentar', async () => {
  const {context:c} = fixture();
  c.fetchSeguro = async () => ({ok: false, json: async () => ({success: false, message: 'Intenta nuevamente'})});
  await assert.rejects(c.reservarNumeroDocumento('compras', 'OC_20260930-0001.pdf', false), /Intenta nuevamente/);
});
