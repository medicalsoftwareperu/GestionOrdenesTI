"""Facturas, vínculos y proveedores: pruebas aisladas de fallos y migración."""
import importlib.util
import io
import json
import sqlite3
import sys
import unittest
from unittest.mock import patch
import test_document_access as access


class AttachmentsAndProvidersTests(unittest.TestCase):
    setUp = access.DocumentAccessTests.setUp
    login = access.DocumentAccessTests.login
    existing = access.DocumentAccessTests.existing
    storage_state = access.DocumentAccessTests.storage_state

    def upload(self, name, content=b'%PDF-1.4\nfactura'):
        return self.client.post('/subir_factura', data={'nombre_oc': name,
            'pdf': (io.BytesIO(content), 'factura proveedor.pdf')})

    def link(self, op, oc):
        return self.client.post('/vincular_oc', json={'nombre_op': op, 'nombre_oc': oc})

    def reload(self):
        spec = importlib.util.spec_from_file_location('gestionguias_restarted_attachments', self.root / 'app.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: module}):
            spec.loader.exec_module(module)
        return module

    def db(self, sql, args=()):
        with sqlite3.connect(self.root / 'database.db') as conn:
            return conn.execute(sql, args).fetchall()

    def test_invoice_invalid_content_preserves_previous_file(self):
        name=self.existing('compras');self.login('sistemas');self.upload(name)
        before=self.storage_state()
        self.assertEqual(self.upload(name,b'<html>not pdf</html>').status_code,400)
        self.assertEqual(before,self.storage_state())

    def test_failed_invoice_replacement_preserves_previous_file_and_allows_retry(self):
        name=self.existing('compras');self.login('sistemas');self.upload(name);before=self.storage_state()
        real=self.module.os.replace;failed=False
        def replace(source,destination):
            nonlocal failed
            if not failed and not str(source).endswith('.anterior'):
                failed=True;raise OSError('simulated write failure')
            return real(source,destination)
        with patch.object(self.module.os,'replace',side_effect=replace):
            self.assertEqual(self.upload(name,b'%PDF-changed').status_code,500)
        self.assertEqual(before,self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])
        self.assertTrue(self.upload(name,b'%PDF-changed').json['success'])

    def test_failed_commit_restores_invoice_and_link(self):
        oc=self.existing('compras');op=self.existing('pagos')
        self.login('sistemas');self.upload(oc)
        for kind in ['invoice','link']:
            self.login('sistemas' if kind=='invoice' else 'contabilidad')
            before=self.storage_state();real=self.module.get_db_connection;failed=False
            class Connection:
                def __init__(self):self.conn=real();self.final=False
                def execute(self,sql,args=()):
                    if sql.startswith('DELETE FROM guardados_pendientes'):self.final=True
                    return self.conn.execute(sql,args)
                def commit(self):
                    nonlocal failed
                    if self.final and not failed:
                        failed=True;raise sqlite3.OperationalError('simulated final commit failure')
                    return self.conn.commit()
                def rollback(self):self.final=False;return self.conn.rollback()
                def close(self):self.conn.close()
            with self.subTest(kind=kind),patch.object(self.module,'get_db_connection',side_effect=Connection):
                response=self.upload(oc,b'%PDF-replacement') if kind=='invoice' else self.link(op,oc)
                self.assertEqual(response.status_code,500)
            self.assertEqual(before,self.storage_state())
            self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_restart_recovers_replaced_invoice_and_link(self):
        oc=self.existing('compras');op=self.existing('pagos')
        self.module.sincronizar_contadores_con_disco()
        for kind in ['invoice','link']:
            self.login('sistemas' if kind=='invoice' else 'contabilidad')
            if kind=='invoice':self.upload(oc)
            before=self.storage_state();real=self.module.os.replace
            def replace(source,destination):
                result=real(source,destination)
                if not str(source).endswith('.anterior'):raise KeyboardInterrupt('simulated restart after publication')
                return result
            with self.subTest(kind=kind),patch.object(self.module.os,'replace',side_effect=replace):
                with self.assertRaises(KeyboardInterrupt):
                    self.upload(oc,b'%PDF-replacement') if kind=='invoice' else self.link(op,oc)
            self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(1,)])
            self.reload()
            self.assertEqual(before,self.storage_state())
            self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_restart_between_journal_commit_and_publication_keeps_recovery_files(self):
        oc=self.existing('compras');self.login('sistemas');self.upload(oc)
        self.module.sincronizar_contadores_con_disco();before=self.storage_state()
        real=self.module.get_db_connection;interrupted=False
        class Connection:
            def __init__(self):self.conn=real();self.journal=False
            def execute(self,sql,args=()):
                if sql.startswith('INSERT INTO guardados_pendientes'):self.journal=True
                return self.conn.execute(sql,args)
            def commit(self):
                nonlocal interrupted
                self.conn.commit()
                if self.journal and not interrupted:
                    interrupted=True;raise KeyboardInterrupt('interruption during journal commit')
            def rollback(self):self.conn.rollback()
            def close(self):self.conn.close()
        with patch.object(self.module,'get_db_connection',side_effect=Connection):
            with self.assertRaises(KeyboardInterrupt):self.upload(oc,b'%PDF-replacement')
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(1,)])
        self.reload();self.assertEqual(before,self.storage_state())
        self.assertEqual(self.db('SELECT COUNT(*) FROM guardados_pendientes'),[(0,)])

    def test_restart_removes_incomplete_first_invoice(self):
        oc=self.existing('compras');self.login('sistemas');self.module.sincronizar_contadores_con_disco()
        before=self.storage_state();real=self.module.os.replace
        def replace(source,destination):
            result=real(source,destination);raise KeyboardInterrupt('simulated restart')
        with patch.object(self.module.os,'replace',side_effect=replace):
            with self.assertRaises(KeyboardInterrupt):self.upload(oc)
        self.reload();self.assertEqual(before,self.storage_state())

    def test_link_updates_latest_metadata_and_keeps_other_fields(self):
        oc=self.existing('compras');op=self.existing('pagos');self.login('contabilidad')
        original=self.root/'historial/pagos'/(op[:-4]+'.json')
        edited=self.root/'historial/pagos_editadas'/(op[:-4]+'.json')
        edited.write_text(json.dumps({'items':[{'detalle':'Pago'}],'obs':'Conservar'}))
        original_bytes=original.read_bytes()
        for reference in [oc,'']:
            self.assertTrue(self.link(op,reference).json['success'])
            metadata=json.loads(edited.read_text())
            self.assertEqual(metadata['obs'],'Conservar');self.assertEqual(metadata['items'],[{'detalle':'Pago'}])
            self.assertEqual(metadata.get('orden_compra_referencia',''),reference)
            self.assertEqual(original.read_bytes(),original_bytes)

    def test_invalid_link_payload_does_not_change_metadata(self):
        op=self.existing('pagos');self.login('contabilidad');before=self.storage_state()
        for data in [None,[],{'nombre_op':op,'nombre_oc':2}]:
            self.assertEqual(self.client.post('/vincular_oc',json=data).status_code,400)
        self.assertEqual(before,self.storage_state())

    def provider(self, account):
        return {'nombre':'Proveedor compartido de prueba','ruc':'12345678901','direccion':'Dirección',
                'contacto':'Contacto','cuenta_soles':account,'cci':'CCI-'+account,'cuenta_dolares':'USD-'+account,
                'banco':'Banco de prueba','contacto_nombre':'Ana','contacto_telefono':'555'}

    def test_provider_read_and_write_are_separate_for_all_four_areas(self):
        for role in ['sistemas','mantenimiento','contabilidad','marketing']:
            self.login(role)
            self.assertTrue(self.client.post('/guardar_proveedor',json=self.provider(role)).json['success'])
        for role in ['sistemas','mantenimiento','contabilidad','marketing']:
            self.login(role);rows=self.client.get('/get_proveedores').json
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['cuenta_soles'],role)
            self.assertEqual(rows[0]['cci'],'CCI-'+role)
            self.assertEqual(rows[0]['contacto_nombre'],'Ana')

    def prepare_legacy_providers(self):
        with sqlite3.connect(self.root/'database.db') as conn:
            conn.execute('DELETE FROM migraciones_sistema WHERE id=?',('separar_proveedores_mantenimiento_v1',))
            conn.execute('INSERT INTO proveedores (nombre, ruc, cuenta_soles, banco, contacto_nombre) VALUES (?,?,?,?,?)',
                         ('Proveedor anterior','123','Cuenta anterior','Banco anterior','Ana'))

    def test_migration_preserves_previous_list_and_copies_only_once(self):
        self.prepare_legacy_providers();self.reload()
        columns='nombre,ruc,cuenta_soles,banco,contacto_nombre'
        self.assertEqual(self.db('SELECT '+columns+' FROM proveedores_maint'),self.db('SELECT '+columns+' FROM proveedores'))
        self.login('mantenimiento');data=self.provider('Cuenta mantenimiento');data['nombre']='Proveedor anterior'
        self.assertTrue(self.client.post('/guardar_proveedor',json=data).json['success'])
        self.reload()
        self.assertEqual(self.db('SELECT cuenta_soles FROM proveedores_maint'),[('Cuenta mantenimiento',)])
        self.assertEqual(self.db('SELECT cuenta_soles FROM proveedores'),[('Cuenta anterior',)])
        self.login('sistemas');data['nombre']='Nuevo de Sistemas';self.client.post('/guardar_proveedor',json=data)
        self.reload();self.assertEqual(self.db('SELECT COUNT(*) FROM proveedores_maint'),[(1,)])

    def test_migration_keeps_existing_maintenance_provider_on_name_collision(self):
        self.prepare_legacy_providers()
        self.db('INSERT INTO proveedores_maint(nombre,cuenta_soles) VALUES (?,?)',('Proveedor anterior','Cuenta propia'))
        self.reload()
        self.assertEqual(self.db('SELECT cuenta_soles FROM proveedores_maint'),[('Cuenta propia',)])
        self.assertEqual(self.db('SELECT cuenta_soles FROM proveedores'),[('Cuenta anterior',)])


if __name__=='__main__':unittest.main()
