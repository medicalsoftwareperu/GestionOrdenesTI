"""Pruebas de guardado, fallos y concurrencia con documentos temporales."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_document_access as access


class DocumentSaveTests(unittest.TestCase):
    setUp = access.DocumentAccessTests.setUp
    login = access.DocumentAccessTests.login
    storage_state = access.DocumentAccessTests.storage_state
    existing = access.DocumentAccessTests.existing

    def reserve(self, client=None, kind='compras', company=''):
        client = client or self.client
        response = client.post('/reservar_documento', json={
            'tipo': kind, 'nombre': self.names[kind], 'empresa': company})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def save(self, name=None, token='', edit=False, pdf=b'%PDF-1.4\ntest', metadata=None, items=None, client=None):
        name = name or self.names['compras']
        metadata = {'razon_social': 'Empresa de prueba', 'ruc': '', 'direccion': '',
                    'items': [{'desc': 'Equipo de prueba'}]} if metadata is None else metadata
        items = [{'desc': 'Equipo de prueba', 'marca': '', 'modelo': ''}] if items is None else items
        return (client or self.client).post('/guardar_pdf', data={
            'pdf': (io.BytesIO(pdf), name), 'edit_mode': str(edit).lower(), 'reserva': token,
            'metadata': metadata if isinstance(metadata, str) else json.dumps(metadata),
            'items': items if isinstance(items, str) else json.dumps(items)})

    def db(self, query, args=()):
        with sqlite3.connect(self.root / 'database.db') as conn:
            return conn.execute(query, args).fetchall()

    def test_pdf_metadata_search_and_counter_are_saved_together(self):
        self.login('sistemas'); reservation = self.reserve()
        response = self.save(reservation['nombre'], reservation['reserva'])
        self.assertTrue(response.json['success'])
        name = reservation['nombre']
        self.assertTrue((self.root / 'historial/compras' / name).is_file())
        self.assertEqual(json.loads((self.root / 'historial/compras' / (name[:-4]+'.json')).read_text())['items'][0]['desc'], 'Equipo de prueba')
        self.assertEqual(self.db('SELECT COUNT(*) FROM items_pdf WHERE nombre_archivo=?', (name,)), [(1,)])
        self.assertEqual(self.db("SELECT valor FROM contadores WHERE tipo='compras'"), [(2,)])
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'), [(0,)])

    def test_invalid_payload_or_pdf_does_not_change_files_or_counters(self):
        self.login('sistemas')
        for kwargs in [{'metadata': '{'}, {'metadata': []}, {'items': '{}'}, {'items': [7]},
                       {'pdf': b'not a PDF'}, {'metadata': {'razon_social': 7}}]:
            with self.subTest(kwargs=kwargs):
                before = self.storage_state()
                self.assertEqual(self.save(**kwargs).status_code, 400)
                self.assertEqual(before, self.storage_state())

    def test_failed_sql_rolls_back_new_document_and_company(self):
        self.login('sistemas'); reservation=self.reserve();before=self.storage_state()
        with patch.object(self.module, 'persistir_datos_documento', side_effect=sqlite3.OperationalError('injected SQL failure')):
            self.assertEqual(self.save(reservation['nombre'], reservation['reserva']).status_code, 500)
        self.assertEqual(before, self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'), [(0,)])
        self.assertTrue(self.save(reservation['nombre'], reservation['reserva']).json['success'])

    def test_failed_json_publication_restores_previous_edit(self):
        self.login('sistemas');name=self.existing('compras')
        self.assertTrue(self.save(name, edit=True).json['success']);before=self.storage_state()
        real_replace=self.module.os.replace; failed=False
        def replace(source, destination):
            nonlocal failed
            if not failed and str(destination).endswith('.json'):
                failed=True
                raise OSError('injected disk failure')
            return real_replace(source, destination)
        with patch.object(self.module.os,'replace',side_effect=replace):
            self.assertEqual(self.save(name,edit=True,pdf=b'%PDF-1.4\nchanged').status_code,500)
        self.assertEqual(before,self.storage_state())

    def test_failed_final_commit_restores_files_and_database(self):
        self.login('sistemas');before=self.storage_state();real_get=self.module.get_db_connection;failed=False
        class Connection:
            def __init__(self):self.conn=real_get();self.final=False
            def execute(self,sql,args=()):
                if sql.startswith('DELETE FROM guardados_pendientes'):self.final=True
                return self.conn.execute(sql,args)
            def commit(self):
                nonlocal failed
                if self.final and not failed:
                    failed=True
                    raise sqlite3.OperationalError('injected commit failure')
                return self.conn.commit()
            def rollback(self):self.final=False;return self.conn.rollback()
            def close(self):return self.conn.close()
        with patch.object(self.module,'get_db_connection',side_effect=Connection):
            self.assertEqual(self.save().status_code,500)
        self.assertEqual(before,self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM items_pdf'),[(0,)])

    def test_restart_recovers_an_interrupted_edit(self):
        self.login('sistemas');name=self.names['compras'];self.save(name);self.save(name,edit=True)
        before=self.storage_state()
        with patch.object(self.module,'persistir_datos_documento',side_effect=KeyboardInterrupt('simulated interruption')):
            with self.assertRaises(KeyboardInterrupt):self.save(name,edit=True,pdf=b'%PDF-1.4\ninterrupted')
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(1,)])
        spec=importlib.util.spec_from_file_location('restarted_app',self.root/'app.py')
        restarted=importlib.util.module_from_spec(spec);spec.loader.exec_module(restarted)
        self.assertEqual(before,self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_restart_removes_an_interrupted_creation_before_sync(self):
        self.login('sistemas');before=self.storage_state()
        with patch.object(self.module,'persistir_datos_documento',side_effect=KeyboardInterrupt('simulated interruption')):
            with self.assertRaises(KeyboardInterrupt):self.save()
        spec=importlib.util.spec_from_file_location('restarted_new_app',self.root/'app.py')
        restarted=importlib.util.module_from_spec(spec);spec.loader.exec_module(restarted)
        self.assertEqual(before,self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_same_reservation_retry_is_idempotent(self):
        self.login('sistemas');r=self.reserve()
        self.assertTrue(self.save(r['nombre'],r['reserva']).json['success']);before=self.storage_state()
        self.assertTrue(self.save(r['nombre'],r['reserva']).json['success'])
        self.assertEqual(before,self.storage_state())
        self.assertEqual(self.save(r['nombre'],r['reserva'],pdf=b'%PDF-1.4\nother').status_code,409)

    def test_reservation_is_bound_to_user_filename_and_company(self):
        self.login('sistemas');r=self.reserve();before=self.storage_state()
        self.assertEqual(self.save(r['nombre'], 'not-a-token').status_code,400)
        self.assertEqual(self.save('OC_20260930-0002.pdf', r['reserva']).status_code,400)
        self.assertEqual(self.save(r['nombre']).status_code,409)
        self.assertEqual(before,self.storage_state())
        self.login('contabilidad');r=self.reserve(kind='pagos',company='Empresa A')
        self.assertEqual(self.save(r['nombre'],r['reserva'],metadata={'razon_social':'Empresa B','items':[]},items=[]).status_code,400)

    def test_concurrent_reservations_and_saves_are_unique(self):
        username=next(user for user,role in self.module.USER_ROLES.items() if role=='sistemas')
        def worker(_):
            client=self.module.app.test_client()
            with client.session_transaction() as session:session.update(usuario=username,rol='sistemas')
            r=self.reserve(client)
            response=self.save(r['nombre'],r['reserva'],client=client)
            self.assertEqual(response.status_code,200,response.json)
            return r['nombre']
        with ThreadPoolExecutor(max_workers=6) as executor:names=list(executor.map(worker,range(6)))
        self.assertEqual(len(set(names)),6)
        self.assertEqual(self.db("SELECT valor FROM contadores WHERE tipo='compras'"),[(7,)])
        self.assertEqual(self.db('SELECT COUNT(*) FROM items_pdf'),[(6,)])
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_old_open_forms_cannot_overwrite_a_concurrent_creation(self):
        username=next(user for user,role in self.module.USER_ROLES.items() if role=='sistemas')
        def worker(_):
            client=self.module.app.test_client()
            with client.session_transaction() as session:session.update(usuario=username,rol='sistemas')
            return self.save(client=client).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:codes=list(executor.map(worker,range(2)))
        self.assertEqual(sorted(codes),[200,409])
        self.assertEqual(self.db('SELECT COUNT(*) FROM items_pdf'),[(1,)])

    def test_payment_sequences_remain_independent_by_company(self):
        self.login('contabilidad')
        a=self.reserve(kind='pagos',company='Empresa A'); b=self.reserve(kind='pagos',company='Empresa A')
        self.assertEqual(a['numero'],'2026-0001');self.assertEqual(b['numero'],'2026-0002')
        # Dos empresas con el mismo prefijo tampoco pueden generar el mismo archivo.
        c=self.reserve(kind='pagos',company='Empresa B');self.assertEqual(c['numero'],'2026-0003')
        response=self.client.post('/reservar_documento',json={'tipo':'pagos','nombre':'OP_OT_2026-0001.pdf','empresa':'ONCO TEST S.A.C.'})
        self.assertEqual(response.json['numero'],'2026-0012')

    def test_sync_does_not_lower_existing_counters(self):
        with sqlite3.connect(self.root/'database.db') as conn:conn.execute("UPDATE contadores SET valor=99 WHERE tipo='compras'")
        self.module.sincronizar_contadores_con_disco()
        self.assertEqual(self.db("SELECT valor FROM contadores WHERE tipo='compras'"),[(99,)])

    def test_payment_edit_preserves_existing_purchase_link(self):
        self.login('contabilidad');name=self.existing('pagos')
        p=self.root/'historial/pagos'/(name[:-4]+'.json');p.write_text(json.dumps({'items':[],'orden_compra_referencia':'OC_20260930-0001.pdf'}))
        response=self.save(name,edit=True,items=[],metadata={'items':[]})
        self.assertTrue(response.json['success'])
        updated=json.loads((self.root/'historial/pagos_editadas'/(name[:-4]+'.json')).read_text())
        self.assertEqual(updated['orden_compra_referencia'],'OC_20260930-0001.pdf')


if __name__=='__main__':unittest.main()
