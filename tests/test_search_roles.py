"""Búsqueda y mapas del historial: visibilidad HTTP por rol sin datos reales."""
import json
import sqlite3
import unittest
from unittest.mock import patch
import test_document_access as access


class SearchRoleTests(unittest.TestCase):
    setUp = access.DocumentAccessTests.setUp
    login = access.DocumentAccessTests.login
    existing = access.DocumentAccessTests.existing
    storage_state = access.DocumentAccessTests.storage_state
    endpoints = ['/buscar_archivos?q=equipo', '/get_mapeo_proveedores', '/get_mapeo_emisores']

    def seed(self):
        for kind, name in self.names.items():
            self.existing(kind)
            (self.root / 'historial' / kind / (name[:-4]+'.json')).write_text(json.dumps({
                'items':[], 'prov_nombre':'Proveedor privado '+kind,
                'razon_social':'Emisor privado '+kind}))
            self.index(name)

    def index(self, name, text='equipo común'):
        with sqlite3.connect(self.root/'database.db') as conn:
            conn.execute('INSERT INTO items_pdf(nombre_archivo,contenido) VALUES (?,?)',(name,text))

    def expected(self, role):
        return {name for kind,name in self.names.items() if self.roles[kind]==role}

    def test_search_matches_only_documents_of_each_authenticated_role(self):
        self.seed()
        for role in set(self.roles.values()):
            self.login(role)
            for query in ['equipo','EQUIPO','', '%', '_']:
                with self.subTest(role=role,query=query):
                    response=self.client.get('/buscar_archivos',query_string={'q':query})
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(set(response.json),self.expected(role))
            self.assertEqual(self.client.get('/buscar_archivos?q=inexistente').json,[])

    def test_both_maps_include_only_authorized_names_and_values(self):
        self.seed()
        for role in set(self.roles.values()):
            self.login(role)
            for endpoint,label in [('/get_mapeo_proveedores','Proveedor privado '),('/get_mapeo_emisores','Emisor privado ')]:
                with self.subTest(role=role,endpoint=endpoint):
                    response=self.client.get(endpoint)
                    expected={name:label+kind for kind,name in self.names.items() if self.roles[kind]==role}
                    self.assertEqual(response.json,expected)

    def test_edit_overrides_map_values_and_index_results_stay_unique(self):
        self.seed();name=self.names['compras'];self.index(name)
        p=self.root/'historial/compras_editadas'/(name[:-4]+'.json')
        p.write_text(json.dumps({'prov_nombre':'Proveedor editado','razon_social':'Emisor editado'}))
        self.login('sistemas')
        self.assertEqual(self.client.get('/get_mapeo_proveedores').json[name],'Proveedor editado')
        self.assertEqual(self.client.get('/get_mapeo_emisores').json[name],'Emisor editado')
        self.assertEqual(self.client.get('/buscar_archivos?q=equipo').json.count(name),1)

    def test_legacy_and_edit_only_documents_keep_their_visibility(self):
        for kind,name in [('compras','OC_000-0118.pdf'),('pagos','OP_002026-000004.pdf')]:
            self.existing(kind,name);self.index(name)
            self.login(self.roles[kind])
            self.assertIn(name,self.client.get('/buscar_archivos?q=equipo').json)
            self.assertEqual(self.client.get('/get_metadata/'+kind+'/'+name).status_code,200)
        name='OCM_20260930-0009.pdf';folder=self.root/'historial/mantenimiento_editadas'
        (folder/name).write_bytes(b'%PDF-edit-only')
        (folder/(name[:-4]+'.json')).write_text(json.dumps({'prov_nombre':'Proveedor editado'}))
        self.index(name);self.login('mantenimiento')
        self.assertEqual(self.client.get('/buscar_archivos?q=equipo').json,[name])
        self.assertEqual(self.client.get('/get_mapeo_proveedores').json,{name:'Proveedor editado'})

    def test_stale_or_invalid_index_and_metadata_do_not_leak_names(self):
        self.seed();self.login('sistemas')
        for name in ['OC_20260930-0999.pdf','OC_../outside.pdf','OC_20260930-0001.pdf/../OP_2026-0001.pdf']:
            self.index(name)
        # Un JSON sin PDF o de otro tipo dentro de Compras tampoco corresponde al historial visible.
        folder=self.root/'historial/compras'
        for name in ['OC_20260930-0999.json','OP_JyR_2026-0999.json']:
            (folder/name).write_text(json.dumps({'prov_nombre':'No exponer','razon_social':'No exponer'}))
        (folder/'OP_JyR_2026-0999.pdf').write_bytes(b'%PDF-wrong-area');self.index('OP_JyR_2026-0999.pdf')
        self.assertEqual(set(self.client.get('/buscar_archivos?q=equipo').json),self.expected('sistemas'))
        for endpoint in self.endpoints[1:]:self.assertEqual(set(self.client.get(endpoint).json),self.expected('sistemas'))

    def test_query_parameters_and_stale_session_role_cannot_expand_access(self):
        self.seed();self.login('mantenimiento')
        with self.client.session_transaction() as session:session['rol']='sistemas'
        for endpoint in self.endpoints:
            response=self.client.get(endpoint.split('?')[0],query_string={'rol':'sistemas','tipo':'compras','q':'equipo'})
            self.assertEqual(set(response.json),self.expected('mantenimiento'))

    def test_unknown_role_fails_closed_without_exposing_any_records(self):
        self.seed();self.login('sistemas')
        with self.client.session_transaction() as session:username=session['usuario']
        with patch.dict(self.module.USER_ROLES,{username:'desconocido'}):
            self.assertEqual(self.client.get(self.endpoints[0]).json,[])
            for endpoint in self.endpoints[1:]:self.assertEqual(self.client.get(endpoint).json,{})

    def test_unauthenticated_requests_redirect_without_data(self):
        self.seed()
        for endpoint in self.endpoints:
            response=self.client.get(endpoint)
            self.assertEqual(response.status_code,302)
            self.assertTrue(response.headers['Location'].endswith('/login'))

    def test_corrupt_metadata_does_not_break_other_visible_records(self):
        self.seed();self.login('sistemas')
        name=self.names['compras']
        (self.root/'historial/compras'/(name[:-4]+'.json')).write_text('{invalid')
        expected={self.names['bajas']}
        for endpoint in self.endpoints[1:]:self.assertEqual(set(self.client.get(endpoint).json),expected)
        self.assertEqual(set(self.client.get('/buscar_archivos?q=equipo').json),self.expected('sistemas'))

    def test_read_requests_preserve_files_counters_and_purchase_link_workflow(self):
        self.seed();before=self.storage_state()
        for role in set(self.roles.values()):
            self.login(role)
            for endpoint in self.endpoints:self.assertEqual(self.client.get(endpoint).status_code,200)
        self.assertEqual(before,self.storage_state())
        self.login('contabilidad')
        self.assertIn(self.names['compras'],self.client.get('/get_lista_compras').json)
        self.assertTrue(self.client.post('/vincular_oc',json={'nombre_op':self.names['pagos'],'nombre_oc':self.names['compras']}).json['success'])


if __name__=='__main__':unittest.main()
