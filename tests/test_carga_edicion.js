// Ejecutar: node tests/test_carga_edicion.js. Sin archivos ni datos de producción.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const shared = fs.readFileSync(path.join(root, 'static/documentos.js'), 'utf8');
const templates = ['orden_de_compra.html', 'orden_de_compra_mantenimiento.html', 'orden_de_pago.html', 'orden_de_servicio.html', 'guia_de_baja.html'];

function fixture(name, response, failDuringFill=false) {
  const html = fs.readFileSync(path.join(root, 'templates', name), 'utf8');
  const start = html.indexOf('  async function cargarMetadatosDeEdicion() {');
  const loader = html.slice(start, html.indexOf('\n  }', start)+4);
  const button = {disabled:false}, fields = new Map(), alerts = [], requests = [];
  const context = vm.createContext({
    document:{querySelectorAll:()=>[button], getElementById:id=>{
      if (!fields.has(id)) fields.set(id, {value:'',innerHTML:'',style:{},textContent:'',className:''});
      return fields.get(id);
    }}, alert:message=>alerts.push(message), console:{error:()=>{}},
    EDIT_FILENAME:'documento-de-prueba.pdf', initialItems:[], imagenesBase64:[],
    addRow:()=>{}, autoExpand:()=>{}, renderizarGaleriaImagenes:()=>{},
    recalc:()=>{if(failDuringFill) throw Error('Fallo simulado al completar el formulario');},
    fetchSeguro:async url=>{requests.push(url);return await response();}
  });
  vm.runInContext(shared+'\n'+loader, context);
  context.configurarEdicionDocumento(true);
  return {context,button,alerts,requests,html};
}
const good = () => ({ok:true,json:async()=>({success:true,data:{items:[{desc:'Equipo de prueba'}],imagenes:[]}})});

for (const name of templates) {
  test(name+': mientras carga no permite guardar; al terminar sí', async()=>{
    let resolve;
    const pending = new Promise(done=>{resolve=done;});
    const f=fixture(name,()=>pending);
    assert.ok(f.html.includes('configurarEdicionDocumento(EDIT_MODE);'));
    assert.ok(f.html.includes('documentos.js\') }}?v=20261001-1'));
    assert.equal(f.button.disabled,true);
    const loading=f.context.cargarMetadatosDeEdicion();
    assert.equal(f.context.iniciarGuardadoDocumento(true),false);
    resolve(good());await loading;
    assert.equal(f.button.disabled,false);
    assert.equal(f.context.iniciarGuardadoDocumento(true),true);
    f.context.finalizarGuardadoDocumento(false,true);
    assert.equal(f.button.disabled,false);
  });
  const failures = {
    'error de red':()=>Promise.reject(Error('Red de prueba')),
    'respuesta JSON inválida':()=>({ok:true,json:async()=>{throw SyntaxError('JSON de prueba');}}),
    'documento no encontrado':()=>({ok:false,json:async()=>({success:false,message:'No encontrado'})}),
    'HTTP fallido con success true':()=>({ok:false,json:async()=>({success:true,data:{items:[]}})}),
    'metadatos con estructura inválida':()=>({ok:true,json:async()=>({success:true,data:[]})}),
    'ítems con estructura inválida':()=>({ok:true,json:async()=>({success:true,data:{items:[null]}})})
  };
  for (const [reason,response] of Object.entries(failures)) {
    test(name+': '+reason+' conserva bloqueado el guardado',async()=>{
      const f=fixture(name,response);await f.context.cargarMetadatosDeEdicion();
      assert.equal(f.button.disabled,true);
      assert.ok(f.alerts.some(message=>message.includes('Recarga la página')));
      assert.equal(f.context.iniciarGuardadoDocumento(true),false);
      f.context.finalizarGuardadoDocumento(false,true);
      assert.equal(f.button.disabled,true);
      assert.equal(f.requests.length,1);
      assert.ok(f.requests[0].startsWith('/get_metadata/'));
    });
  }
  test(name+': un error al rellenar campos no habilita un guardado incompleto',async()=>{
    const f=fixture(name,good,true);await f.context.cargarMetadatosDeEdicion();
    assert.equal(f.button.disabled,true);
    assert.equal(f.context.iniciarGuardadoDocumento(true),false);
  });
  test(name+': una recarga de datos fallida revoca el permiso anterior',async()=>{
    let fails=false;
    const f=fixture(name,()=>fails?Promise.reject(Error('Red de prueba')):good());
    await f.context.cargarMetadatosDeEdicion();assert.equal(f.button.disabled,false);
    fails=true;await f.context.cargarMetadatosDeEdicion();
    assert.equal(f.button.disabled,true);
    assert.equal(f.context.iniciarGuardadoDocumento(true),false);
  });
}
test('un documento nuevo mantiene el guardado habitual sin cargar una edición',()=>{
  const f=fixture(templates[0],good);f.context.configurarEdicionDocumento(false);
  assert.equal(f.button.disabled,false);
  assert.equal(f.context.iniciarGuardadoDocumento(false),true);
  f.context.finalizarGuardadoDocumento(false,false);
  assert.equal(f.button.disabled,false);
});
