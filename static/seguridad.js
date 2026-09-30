// Validación interna: los mismos formularios y botones envían el token automáticamente.
async function fetchSeguro(url, opciones = {}) {
  const destino = new URL(url, window.location.href);
  const metodo = (opciones.method || 'GET').toUpperCase();
  if (destino.origin !== window.location.origin || ['GET', 'HEAD', 'OPTIONS'].includes(metodo)) {
    return fetch(url, opciones);
  }
  const meta = document.querySelector('meta[name="csrf-token"]');
  const cabeceras = new Headers(opciones.headers || {});
  cabeceras.set('X-CSRF-Token', meta?.content || '');
  const enviar = () => fetch(url, { ...opciones, headers: cabeceras });
  const respuesta = await enviar();
  if (respuesta.status === 403) {
    let datos;
    try { datos = await respuesta.clone().json(); } catch (_) { return respuesta; }
    if (datos.code === 'csrf_invalido') {
      // Reintentar solo si el servidor rechazó antes de modificar datos.
      try {
        const renovacion = await fetch('/csrf-token', { cache: 'no-store', credentials: 'same-origin' });
        if (!renovacion.ok) return respuesta;
        const token = (await renovacion.json()).csrf_token;
        if (typeof token !== 'string' || !token) return respuesta;
        if (meta) meta.content = token;
        cabeceras.set('X-CSRF-Token', token);
      } catch (_) { return respuesta; }
      return enviar();
    }
  }
  return respuesta;
}

document.addEventListener('click', async evento => {
  const enlace = evento.target.closest?.('a[href="/logout"]');
  if (!enlace || evento.button > 0 || evento.ctrlKey || evento.metaKey) return;
  evento.preventDefault();
  try {
    const respuesta = await fetchSeguro('/logout', { method: 'POST' });
    if (!respuesta.ok) throw new Error('No se pudo cerrar la sesión. Intenta nuevamente.');
    window.location.href = '/login';
  } catch (error) {
    alert(error.message);
  }
});
