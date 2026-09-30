"""Pruebas HTTP en una copia temporal, sin tocar documentos o datos reales.

Ejecutar: python -m unittest discover -s tests -v
Requiere Flask, igual que la aplicación.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest


class DocumentAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gestionguias_access_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Path(os.environ.get('GESTIONGUIAS_APP_SOURCE', Path(__file__).resolve().parents[1] / 'app.py'))
        shutil.copy2(source, self.root / 'app.py')
        shutil.copytree(source.parent / 'templates', self.root / 'templates')
        spec = importlib.util.spec_from_file_location('gestionguias_test_app', self.root / 'app.py')
        self.module = importlib.util.module_from_spec(spec)
        # La copia no incluye .env, database.db ni historial de producción.
        spec.loader.exec_module(self.module)
        self.module.app.config.update(TESTING=True, SECRET_KEY='isolated-test-key')
        self.client = self.module.app.test_client()
        self.names = {
            'compras': 'OC_20260930-0001.pdf', 'bajas': 'BAJA_20260930-0001.pdf',
            'pagos': 'OP_JyR_2026-0001.pdf', 'servicios': 'OS_20260930-0001.pdf',
            'mantenimiento': 'OCM_20260930-0001.pdf'
        }
        self.roles = {'compras': 'sistemas', 'bajas': 'sistemas', 'pagos': 'contabilidad',
                      'servicios': 'marketing', 'mantenimiento': 'mantenimiento'}

    def login(self, role):
        username = next(user for user, assigned in self.module.USER_ROLES.items() if assigned == role)
        with self.client.session_transaction() as session:
            session.clear()
            session.update(usuario=username, rol=role)

    def save(self, name, edit=False):
        return self.client.post('/guardar_pdf', data={
            'pdf': (io.BytesIO(b'%PDF-1.4\nfixture'), name),
            'edit_mode': 'true' if edit else 'false',
            'metadata': json.dumps({'items': []}), 'items': '[]'
        })

    def existing(self, kind, name=None):
        name = name or self.names[kind]
        folder = self.root / 'historial' / kind
        (folder / name).write_bytes(b'%PDF-1.4\noriginal')
        (folder / (name[:-4] + '.json')).write_text(json.dumps({'items': []}))
        return name

    def storage_state(self):
        with sqlite3.connect(self.root / 'database.db') as conn:
            counters = conn.execute('SELECT tipo, valor FROM contadores ORDER BY tipo').fetchall()
        files = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in (self.root / 'historial').rglob('*') if p.is_file()}
        return counters, files

    def test_normal_create_edit_view_and_metadata_for_every_area(self):
        for kind, name in self.names.items():
            with self.subTest(kind=kind):
                self.login(self.roles[kind])
                self.assertEqual(self.client.get('/' + kind).status_code, 200)
                response = self.save(name)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json['success'])
                self.assertTrue((self.root / 'historial' / kind / name).is_file())
                self.assertEqual(self.save(name, edit=True).status_code, 200)
                self.assertTrue((self.root / 'historial' / (kind + '_editadas') / name).is_file())
                self.assertEqual(self.client.get('/' + kind, query_string={'edit': name}).status_code, 200)
                with self.client.get('/ver_pdf/' + kind + '/' + name) as pdf:
                    self.assertEqual(pdf.status_code, 200)
                self.assertEqual(self.client.get('/get_metadata/' + kind + '/' + name).status_code, 200)

    def test_other_areas_cannot_create_or_edit_documents(self):
        for kind, name in self.names.items():
            self.existing(kind)
            for role in set(self.roles.values()) - {self.roles[kind]}:
                for edit in [False, True]:
                    with self.subTest(kind=kind, role=role, edit=edit):
                        self.login(role)
                        before = self.storage_state()
                        self.assertEqual(self.save(name, edit).status_code, 403)
                        self.assertEqual(before, self.storage_state())
                        self.assertEqual(self.client.get('/get_metadata/' + kind + '/' + name).status_code, 403)
                        self.assertEqual(self.client.get('/ver_pdf/' + kind + '/' + name).status_code, 404)

    def test_unauthenticated_write_redirects_without_changing_storage(self):
        before = self.storage_state()
        self.assertEqual(self.save(self.names['compras']).status_code, 302)
        self.assertEqual(before, self.storage_state())

    def test_invalid_names_do_not_write_or_increment_counters(self):
        self.login('sistemas')
        for name in ['', '../../outside.pdf', '/tmp/outside.pdf', 'OC_../../outside.pdf',
                     'OC_20260930-0001.pdf/../../outside', 'OC_20260930-0001.pdf\\..\\outside',
                     'OC_20260930-0001.pdf.exe', 'OC_20260930-0001.json', 'OC_20260930-0001.PDF',
                     'OC_２０２６０９３０-0001.pdf', 'OC_20260930-0001:stream.pdf',
                     'OC_' + '1' * 200 + '.pdf', 'OC_000-0118.pdf']:
            with self.subTest(name=name):
                before = self.storage_state()
                self.assertEqual(self.save(name).status_code, 400)
                self.assertEqual(before, self.storage_state())

    def test_edit_requires_existing_document(self):
        self.login('sistemas')
        before = self.storage_state()
        self.assertEqual(self.save(self.names['compras'], edit=True).status_code, 404)
        self.assertEqual(before, self.storage_state())

    def test_legacy_files_remain_readable_and_editable(self):
        for kind, name in [('compras', 'OC_000-0118.pdf'), ('pagos', 'OP_002026-000004.pdf')]:
            with self.subTest(kind=kind):
                self.existing(kind, name)
                self.login(self.roles[kind])
                self.assertEqual(self.client.get('/' + kind, query_string={'edit': name}).status_code, 200)
                self.assertEqual(self.client.get('/get_metadata/' + kind + '/' + name).status_code, 200)
                with self.client.get('/ver_pdf/' + kind + '/' + name) as pdf:
                    self.assertEqual(pdf.status_code, 200)
                self.assertTrue(self.save(name, edit=True).json['success'])

    def test_all_current_and_payment_prefixes_remain_valid(self):
        for prefix in ['OP', 'OP_DP', 'OP_DD', 'OP_DX', 'OP_OT', 'OP_OX', 'OP_MED', 'OP_JyR', 'OP_JyL']:
            self.module.validar_nombre_documento('pagos', prefix + '_2026-0001.pdf')
        self.module.validar_nombre_documento('compras', 'OC_20260930-10000.pdf')

    def test_invoice_upload_replace_and_accounting_read_still_work(self):
        name = self.existing('compras')
        self.login('sistemas')
        for content in [b'%PDF-original', b'%PDF-replacement']:
            response = self.client.post('/subir_factura', data={'nombre_oc': name,
                'pdf': (io.BytesIO(content), 'factura proveedor.pdf')})
            self.assertTrue(response.json['success'])
        self.login('contabilidad')
        with self.client.get('/ver_factura/Factura_' + name) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'%PDF-replacement')
        self.login('marketing')
        self.assertEqual(self.client.get('/ver_factura/Factura_' + name).status_code, 403)
        self.assertEqual(self.client.post('/subir_factura', data={'nombre_oc': name,
            'pdf': (io.BytesIO(b'%PDF'), 'factura.pdf')}).status_code, 403)

    def test_invalid_invoice_reference_is_rejected(self):
        self.login('sistemas')
        for name, status in [('OC_../outside.pdf', 400), ('OC_20260930-0001.pdf', 404)]:
            before = self.storage_state()
            response = self.client.post('/subir_factura', data={'nombre_oc': name,
                'pdf': (io.BytesIO(b'%PDF'), 'factura.pdf')})
            self.assertEqual(response.status_code, status)
            self.assertEqual(before, self.storage_state())

    def test_accounting_can_link_and_unlink_existing_documents(self):
        oc = self.existing('compras'); op = self.existing('pagos')
        self.login('contabilidad')
        for link in [oc, '']:
            response = self.client.post('/vincular_oc', json={'nombre_op': op, 'nombre_oc': link})
            self.assertTrue(response.json['success'])
            metadata = json.loads((self.root / 'historial/pagos' / (op[:-4] + '.json')).read_text())
            self.assertEqual(metadata.get('orden_compra_referencia', ''), link)

    def test_invalid_link_references_do_not_modify_metadata(self):
        op = self.existing('pagos'); self.login('contabilidad')
        for payment, purchase, status in [(op, 'OC_../outside.pdf', 400),
                ('OP_../../outside.pdf', '', 400), (op, self.names['compras'], 404), (op, 42, 400)]:
            before = self.storage_state()
            self.assertEqual(self.client.post('/vincular_oc', json={
                'nombre_op': payment, 'nombre_oc': purchase}).status_code, status)
            self.assertEqual(before, self.storage_state())
        self.login('marketing')
        self.assertEqual(self.client.post('/vincular_oc', json={'nombre_op': op}).status_code, 403)

    def test_path_escape_through_pdf_or_json_symlinks_is_rejected(self):
        self.login('sistemas'); name = self.names['compras']
        outside = self.root / 'outside'; outside.mkdir()
        for extension in ['.pdf', '.json']:
            target = outside / ('private' + extension); target.write_bytes(b'private')
            link = self.root / 'historial/compras' / (name[:-4] + extension)
            link.symlink_to(target)
            before = self.storage_state()
            self.assertEqual(self.save(name).status_code, 400)
            self.assertEqual(before, self.storage_state())
            self.assertEqual(target.read_bytes(), b'private')
            if extension == '.pdf':
                self.assertEqual(self.client.get('/ver_pdf/compras/' + name).status_code, 400)
            else:
                self.assertEqual(self.client.get('/get_metadata/compras/' + name).status_code, 400)
            link.unlink()

    def test_control_characters_and_path_separators_are_rejected(self):
        for name in ['OC_20260930-0001.pdf\n', 'OC_20260930-0001.pdf\0',
                     'OC_../outside.pdf', 'OC_..\\outside.pdf']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.module.validar_nombre_documento('compras', name)

    def test_role_is_recovered_from_the_account(self):
        self.login('marketing')
        with self.client.session_transaction() as session:
            session['rol'] = 'sistemas'
        self.assertEqual(self.save(self.names['compras']).status_code, 403)
        with self.client.session_transaction() as session:
            session.clear()
            session.update(usuario='unknown-account', rol='sistemas')
        self.assertEqual(self.save(self.names['compras']).status_code, 302)

    def test_login_credentials_and_form_submission_are_unchanged(self):
        for username, role in self.module.USER_ROLES.items():
            with self.client.session_transaction() as session:
                session.clear()
            response = self.client.post('/login', data={
                'username': username, 'password': self.module.USER_CREDENTIALS[username]})
            self.assertEqual(response.status_code, 302)
            with self.client.session_transaction() as session:
                self.assertEqual(session['rol'], role)

    def test_unsafe_edit_query_is_rejected_before_rendering(self):
        self.login('sistemas')
        self.assertEqual(self.client.get('/compras', query_string={'edit': 'OC_../outside.pdf'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
