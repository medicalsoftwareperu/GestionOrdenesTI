"""Pruebas aisladas: CSRF real, acciones auditadas y rollback de registros."""
import importlib.util
import io
import json
import re
import sqlite3
import unittest
from unittest.mock import patch
import test_document_access as access


class CsrfAuditTests(unittest.TestCase):
    setUp = access.DocumentAccessTests.setUp
    login = access.DocumentAccessTests.login
    existing = access.DocumentAccessTests.existing
    storage_state = access.DocumentAccessTests.storage_state

    def token(self):
        response=self.client.get('/csrf-token');self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        return response.json['csrf_token']

    def events(self):
        with sqlite3.connect(self.root/'database.db') as conn:
            conn.row_factory=sqlite3.Row
            return [dict(r) for r in conn.execute('SELECT * FROM auditoria ORDER BY id')]

    def save(self, kind='compras', edit=False, token='', client=None):
        return (client or self.client).post('/guardar_pdf',data={
            'pdf':(io.BytesIO(b'%PDF-1.4\nfixture'),self.names[kind]),'edit_mode':str(edit).lower(),
            'metadata':json.dumps({'items':[]}), 'items':'[]','reserva':token})

    def test_all_mutations_reject_missing_or_invalid_tokens_before_writing(self):
        self.existing('compras');self.existing('pagos')
        routes=[('/reservar_documento','sistemas'),('/guardar_pdf','sistemas'),
                ('/subir_factura','sistemas'),('/guardar_proveedor','sistemas'),
                ('/vincular_oc','contabilidad'),('/logout','sistemas')]
        for route,role in routes:
            self.login(role);self.token();before=self.storage_state()
            for headers in [{},{'X-CSRF-Token':'incorrecto'},{'X-CSRF-Token':'á'*64}]:
                with self.subTest(route=route,headers=bool(headers)):
                    response=self.client.open(route,method='POST',headers=headers)
                    self.assertEqual(response.status_code,403)
                    self.assertEqual(response.json['code'],'csrf_invalido')
                    self.assertEqual(before,self.storage_state())
                    self.assertEqual(self.events(),[])

    def test_token_is_bound_to_session_and_role_checks_still_apply(self):
        self.login('sistemas');token=self.token();other=self.module.app.test_client()
        username=next(u for u,r in self.module.USER_ROLES.items() if r=='marketing')
        with other.session_transaction() as session:session.update(usuario=username,rol='marketing')
        other_token=other.get('/csrf-token').json['csrf_token']
        self.assertNotEqual(token,other_token)
        self.assertEqual(other.open('/reservar_documento',method='POST',json={'tipo':'compras','nombre':self.names['compras']},headers={'X-CSRF-Token':token}).json['code'],'csrf_invalido')
        response=other.open('/reservar_documento',method='POST',json={'tipo':'compras','nombre':self.names['compras']},headers={'X-CSRF-Token':other_token})
        self.assertEqual(response.status_code,403)
        self.assertNotIn('code',response.json)
        self.assertEqual(self.events(),[])

    def test_login_has_hidden_token_and_rotates_it_after_success(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:token=session['csrf_token']
        username=next(iter(self.module.USER_ROLES))
        with patch.dict(self.module.USER_CREDENTIALS,{username:'credencial-ficticia-de-test'}):
            rejected=self.client.open('/login',method='POST',data={'username':username,'password':'credencial-ficticia-de-test'})
            self.assertEqual(rejected.status_code,403)
            response=self.client.open('/login',method='POST',data={'username':username,'password':'credencial-ficticia-de-test','csrf_token':token})
            self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:
            self.assertEqual(session['usuario'],username)
            self.assertNotEqual(session['csrf_token'],token)
        self.assertEqual(self.client.get('/logout').status_code,405)
        self.assertEqual(self.client.post('/logout').status_code,302)
        with self.client.session_transaction() as session:self.assertNotIn('usuario',session)

    def test_missing_configured_password_never_allows_login_without_password(self):
        username=next(iter(self.module.USER_ROLES))
        with patch.dict(self.module.USER_CREDENTIALS,{username:None}):
            response=self.client.post('/login',data={'username':username})
        self.assertEqual(response.status_code,200)
        with self.client.session_transaction() as session:self.assertNotIn('usuario',session)

    def test_each_document_area_records_create_and_edit_with_current_account(self):
        for kind,role in self.roles.items():
            self.login(role)
            self.assertTrue(self.save(kind).json['success'])
            self.assertTrue(self.save(kind,edit=True).json['success'])
        rows=self.events();self.assertEqual(len(rows),10)
        for i,(kind,role) in enumerate(self.roles.items()):
            pair=rows[i*2:i*2+2]
            self.assertEqual([r['accion'] for r in pair],['crear_documento','editar_documento'])
            for row in pair:
                self.assertEqual(row['tipo'],kind);self.assertEqual(row['nombre'],self.names[kind])
                self.assertEqual(row['rol'],role)
                self.assertEqual(self.module.USER_ROLES[row['usuario']],role)
                self.assertTrue(row['fecha'].endswith('+00:00'))
                self.assertEqual(json.loads(row['detalle']),{})

    def test_reservation_retry_does_not_duplicate_audit_events(self):
        self.login('sistemas')
        reservation=self.client.post('/reservar_documento',json={'tipo':'compras','nombre':self.names['compras']}).json
        self.assertEqual(self.events(),[])
        self.names['compras']=reservation['nombre']
        for _ in range(2):self.assertTrue(self.save(token=reservation['reserva']).json['success'])
        self.assertEqual(len(self.events()),1)

    def test_invoices_links_and_providers_are_audited_without_content_or_accounts(self):
        oc=self.existing('compras');op=self.existing('pagos');self.login('sistemas')
        for _ in range(2):
            response=self.client.post('/subir_factura',data={'nombre_oc':oc,'pdf':(io.BytesIO(b'%PDF-private-invoice-content'),'factura.pdf')})
            self.assertTrue(response.json['success'])
        self.login('contabilidad')
        for reference in [oc,'']:
            self.assertTrue(self.client.post('/vincular_oc',json={'nombre_op':op,'nombre_oc':reference}).json['success'])
        self.login('mantenimiento')
        self.assertTrue(self.client.post('/guardar_proveedor',json={'nombre':'Proveedor de prueba','cuenta_soles':'CUENTA-PRIVADA-TEST'}).json['success'])
        rows=self.events()
        self.assertEqual([r['accion'] for r in rows],['subir_factura','reemplazar_factura','vincular_compra','desvincular_compra','guardar_proveedor'])
        self.assertEqual(json.loads(rows[2]['detalle']),{'orden_compra':oc})
        self.assertEqual(rows[-1]['rol'],'mantenimiento')
        serialized=json.dumps(rows)
        self.assertNotIn('CUENTA-PRIVADA-TEST',serialized);self.assertNotIn('private-invoice-content',serialized)

    def test_failed_audit_rolls_back_document_invoice_link_and_provider(self):
        oc=self.existing('compras');op=self.existing('pagos')
        self.module.sincronizar_contadores_con_disco()
        cases=[('documento','sistemas'),('factura','sistemas'),('vinculo','contabilidad'),('proveedor','mantenimiento')]
        for kind,role in cases:
            self.login(role);before=self.storage_state()
            with patch.object(self.module,'registrar_evento',side_effect=sqlite3.OperationalError('simulated audit failure')):
                if kind=='documento':response=self.save(edit=True)
                elif kind=='factura':response=self.client.post('/subir_factura',data={'nombre_oc':oc,'pdf':(io.BytesIO(b'%PDF-fixture'),'factura.pdf')})
                elif kind=='vinculo':response=self.client.post('/vincular_oc',json={'nombre_op':op,'nombre_oc':oc})
                else:response=self.client.post('/guardar_proveedor',json={'nombre':'Proveedor de prueba'})
            self.assertFalse(response.json['success'],kind)
            self.assertEqual(before,self.storage_state(),kind)
            self.assertEqual(self.events(),[],kind)
        with sqlite3.connect(self.root/'database.db') as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM proveedores_maint').fetchone()[0],0)

    def test_interruption_after_audit_insert_recovers_document_without_false_event(self):
        self.login('sistemas');self.existing('compras');self.module.sincronizar_contadores_con_disco()
        before=self.storage_state();real=self.module.registrar_evento
        def interrupt(*args,**kwargs):
            real(*args,**kwargs);raise KeyboardInterrupt('simulated restart before commit')
        with patch.object(self.module,'registrar_evento',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):self.save(edit=True)
        self.assertEqual(self.events(),[])
        spec=importlib.util.spec_from_file_location('recovered_audit_app',self.root/'app.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(before,self.storage_state());self.assertEqual(self.events(),[])

    def test_all_pages_include_the_same_session_token_and_secure_fetch_script(self):
        response=self.client.get('/login');html=response.get_data(as_text=True)
        token=re.search(r'<meta name="csrf-token" content="([^"]+)"',html).group(1)
        self.assertIn('name="csrf_token" value="'+token+'"',html)
        for kind,role in self.roles.items():
            self.login(role);self.existing(kind)
            for path in ['/', '/historial', '/'+kind, '/'+kind+'?edit='+self.names[kind]]:
                response=self.client.get(path);self.assertEqual(response.status_code,200)
                html=response.get_data(as_text=True)
                self.assertIn('/static/seguridad.js?v=20260930-1',html)
                self.assertRegex(html,r'<meta name="csrf-token" content="[0-9a-f]{64}"')


if __name__=='__main__':unittest.main()
