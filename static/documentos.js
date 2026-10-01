// Utilidades internas: conservar los mismos botones, confirmaciones y formularios.
let guardadoEnCurso = false;
let documentoNuevoGuardado = false;
const reservasPendientes = new Map();
let edicionRequiereCarga = false;
let datosEdicionCargados = false;

function actualizarBotonesGuardado() {
  document.querySelectorAll('button[onclick="guardarEnHistorial()"]')
    .forEach(boton => { boton.disabled = guardadoEnCurso || (edicionRequiereCarga && !datosEdicionCargados); });
}

function configurarEdicionDocumento(editMode) {
  edicionRequiereCarga = Boolean(editMode);
  datosEdicionCargados = false;
  actualizarBotonesGuardado();
}

function iniciarCargaEdicionDocumento() {
  datosEdicionCargados = false;
  actualizarBotonesGuardado();
}

function completarCargaEdicionDocumento() {
  datosEdicionCargados = true;
  actualizarBotonesGuardado();
}

function datosEdicionValidos(respuesta, resultado) {
  const datos = resultado?.data;
  return respuesta.ok && resultado?.success === true && datos !== null &&
    typeof datos === 'object' && !Array.isArray(datos) &&
    (datos.items === undefined || (Array.isArray(datos.items) &&
      datos.items.every(item => item !== null && typeof item === 'object' && !Array.isArray(item))));
}

function escaparTextoHTML(valor) {
  return String(valor ?? '').replace(/[&<>"']/g, caracter => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[caracter]));
}

function iniciarGuardadoDocumento(editMode) {
  if (editMode && !datosEdicionCargados) {
    alert('No se cargaron completamente los datos originales. Recarga la página antes de guardar. El documento original sigue intacto.');
    return false;
  }
  if (guardadoEnCurso) return false;
  if (!editMode && documentoNuevoGuardado) {
    alert('Ya guardaste este documento. Recarga la página para crear uno nuevo.');
    return false;
  }
  guardadoEnCurso = true;
  actualizarBotonesGuardado();
  return true;
}

function finalizarGuardadoDocumento(exito, editMode) {
  guardadoEnCurso = false;
  if (exito && !editMode) documentoNuevoGuardado = true;
  if (exito) reservasPendientes.clear();
  actualizarBotonesGuardado();
}

async function reservarNumeroDocumento(tipo, nombre, editMode) {
  if (editMode) {
    return { nombre, numero: nombre.match(/([0-9]+-[0-9]+)\.pdf$/)?.[1] || '', reserva: '' };
  }
  const empresa = document.getElementById('razon-social')?.value || '';
  const clave = `${tipo}|${empresa}|${nombre}`;
  if (reservasPendientes.has(clave)) return reservasPendientes.get(clave);
  const respuesta = await fetchSeguro('/reservar_documento', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tipo, nombre, empresa })
  });
  const resultado = await respuesta.json();
  if (!respuesta.ok || !resultado.success) {
    throw new Error(resultado.message || 'No se pudo reservar el número del documento.');
  }
  reservasPendientes.set(clave, resultado);
  reservasPendientes.set(`${tipo}|${empresa}|${resultado.nombre}`, resultado);
  return resultado;
}
