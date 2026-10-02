const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../templates/orden_de_pago.html'),'utf8');
const code=html.slice(html.indexOf('  // Ambos campos consultan'),html.indexOf('  // Autocompletado de Mis Empresas'));
function fixture(){
 const fields=new Map();
 function field(){return {value:'',style:{display:'none'},children:[],listeners:{},addEventListener(e,fn){this.listeners[e]=fn},appendChild(el){this.children.push(el)},set innerHTML(v){this.children=[]}};}
 for(const id of ['prov-nombre','prov-ruc','prov-banco','prov-contacto-nombre','prov-cta-soles','custom-dropdown','ruc-dropdown']) fields.set(id,field());
 const providers=[{nombre:'Empresa A',ruc:'20123456789',banco:'BBVA',contacto_nombre:'Titular A',cuenta_soles:'CUENTA-FICTICIA'},{nombre:'Empresa B',ruc:'12345678'},{nombre:'<img src=x>',ruc:20123456000},{nombre:'Sin documento',ruc:null}];
 const ctx=vm.createContext({document:{getElementById:id=>fields.get(id),createElement:()=>field()},inputProv:fields.get('prov-nombre'),dropdownMenu:fields.get('custom-dropdown'),listaProveedores:providers});vm.runInContext(code,ctx);
 return {fields,providers,ctx,input(id,v,event='input'){const el=fields.get(id);el.value=v;el.listeners[event].call(el)}};
}
test('RUC parcial muestra número y nombre y completa todos los datos al seleccionar',()=>{
 const f=fixture();f.input('prov-ruc','201234567');const menu=f.fields.get('ruc-dropdown');assert.equal(menu.children.length,1);assert.equal(menu.children[0].textContent,'20123456789 · Empresa A');menu.children[0].onclick();
 for(const [id,value] of [['prov-nombre','Empresa A'],['prov-ruc','20123456789'],['prov-banco','BBVA'],['prov-contacto-nombre','Titular A'],['prov-cta-soles','CUENTA-FICTICIA']]) assert.equal(f.fields.get(id).value,value);
 assert.equal(menu.style.display,'none');
});
test('DNI y proveedores sin banco conservan valores predeterminados',()=>{const f=fixture();f.input('prov-ruc','12345678');const m=f.fields.get('ruc-dropdown');const dni=m.children.find(el=>el.textContent==='12345678 · Empresa B');assert.ok(dni);dni.onclick();assert.equal(f.fields.get('prov-banco').value,'BCP');assert.equal(f.fields.get('prov-contacto-nombre').value,'Empresa B');assert.equal(f.fields.get('prov-cta-soles').value,'');});
test('Vaciar o escribir un documento nuevo cierra el menú sin sobrescribir datos',()=>{const f=fixture();f.input('prov-ruc','201');f.input('prov-ruc','99999999');assert.equal(f.fields.get('ruc-dropdown').style.display,'none');assert.equal(f.fields.get('prov-ruc').value,'99999999');assert.equal(f.fields.get('prov-nombre').value,'');f.input('prov-ruc','');assert.equal(f.fields.get('ruc-dropdown').children.length,0);});
test('Selección por nombre conserva los mismos datos y cierra ambas listas',()=>{const f=fixture();f.input('prov-ruc','201');f.input('prov-nombre','empresa a');assert.equal(f.fields.get('ruc-dropdown').style.display,'none');f.fields.get('custom-dropdown').children[0].onclick();assert.equal(f.fields.get('prov-ruc').value,'20123456789');});
test('RUC numérico, foco y nombres con HTML se muestran como texto',()=>{const f=fixture();f.input('prov-ruc','20123456000','focus');const m=f.fields.get('ruc-dropdown');assert.equal(m.children.length,1);assert.equal(m.children[0].textContent,'20123456000 · <img src=x>');assert.equal(m.children[0].children.length,0);});
