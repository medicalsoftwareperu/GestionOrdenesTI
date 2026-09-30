// Ejecutar: node tests/test_seguridad.js; datos y tokens exclusivamente ficticios.
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
function fixture(responses=[]) {
  const meta={content:'token-ficticio-local'},calls=[],listeners={};
  const context=vm.createContext({URL,Headers,window:{location:{href:'https://192.168.10.225/historial',origin:'https://192.168.10.225'}},
    document:{querySelector:()=>meta,addEventListener:(name,fn)=>listeners[name]=fn},alert:()=>{},
    fetch:async(url,options={})=>{
      calls.push({url,options:{...options,headers:new Headers(options.headers)}});
      const next=responses.shift();if(next instanceof Error)throw next;
      return next||new Response(JSON.stringify({success:true}),{status:200});
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/seguridad.js'),'utf8'),context);
  return {context,meta,calls,listeners};
}
const response=(body,status)=>new Response(JSON.stringify(body),{status});
test('envía token en POST interno y conserva cuerpo y cabeceras del formulario',async()=>{
  const {context:c,calls}=fixture();const body={pdf:'contenido-ficticio'};const headers={'Content-Type':'application/json'};
  await c.fetchSeguro('/guardar_pdf',{method:'POST',body,headers});
  assert.equal(calls[0].options.headers.get('X-CSRF-Token'),'token-ficticio-local');
  assert.equal(calls[0].options.headers.get('Content-Type'),'application/json');
  assert.equal(calls[0].options.body,body);assert.equal(headers['X-CSRF-Token'],undefined);
});
test('no añade token a GET ni a solicitudes dirigidas a otro origen',async()=>{
  const {context:c,calls}=fixture();
  await c.fetchSeguro('/buscar_archivos?q=equipo');await c.fetchSeguro('https://otro.example/guardar',{method:'POST'});
  assert.equal(calls.length,2);for(const call of calls)assert.equal(call.options.headers.get('X-CSRF-Token'),null);
});
test('renueva una sesión cambiada y reintenta solo una vez después de un rechazo CSRF',async()=>{
  const {context:c,meta,calls}=fixture([response({code:'csrf_invalido'},403),response({csrf_token:'token-ficticio-renovado'},200),response({success:true},200)]);
  const result=await c.fetchSeguro('/guardar_pdf',{method:'POST',body:'cuerpo'});
  assert.equal((await result.json()).success,true);assert.equal(calls.length,3);
  assert.equal(calls[1].url,'/csrf-token');assert.equal(calls[1].options.cache,'no-store');
  assert.equal(calls[0].options.headers.get('X-CSRF-Token'),'token-ficticio-local');
  assert.equal(calls[2].options.headers.get('X-CSRF-Token'),'token-ficticio-renovado');
  assert.equal(calls[2].options.body,'cuerpo');assert.equal(meta.content,'token-ficticio-renovado');
});
test('no reintenta errores de permisos, guardado o conexión',async()=>{
  for(const result of [response({message:'Acceso no autorizado'},403),response({success:false},500),new Error('Fallo de red')]) {
    const {context:c,calls}=fixture([result]);
    if(result instanceof Error)await assert.rejects(c.fetchSeguro('/guardar_pdf',{method:'POST'}),/Fallo de red/);
    else await c.fetchSeguro('/guardar_pdf',{method:'POST'});
    assert.equal(calls.length,1);
  }
});
test('una renovación fallida conserva la respuesta original sin repetir la escritura',async()=>{
  const {context:c,calls}=fixture([response({code:'csrf_invalido'},403),response({},403)]);
  const result=await c.fetchSeguro('/guardar_pdf',{method:'POST'});assert.equal(result.status,403);assert.equal(calls.length,2);
});
test('el botón existente de salir hace POST protegido y vuelve al login',async()=>{
  const {context:c,calls,listeners}=fixture();let prevented=false;
  await listeners.click({target:{closest:()=>({})},button:0,preventDefault:()=>prevented=true});
  assert.equal(prevented,true);assert.equal(calls[0].url,'/logout');assert.equal(calls[0].options.method,'POST');
  assert.equal(calls[0].options.headers.get('X-CSRF-Token'),'token-ficticio-local');assert.equal(c.window.location.href,'/login');
});
