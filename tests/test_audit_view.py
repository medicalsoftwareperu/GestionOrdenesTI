"""La vista no modifica datos y está reservada a la cuenta de TI."""
import sqlite3
import unittest
import test_document_access as access


class AuditViewTests(unittest.TestCase):
    setUp = access.DocumentAccessTests.setUp
    login = access.DocumentAccessTests.login

    def insert(self, name='OC_20260930-0001.pdf', role='sistemas', action='crear_documento', detail='{}'):
        conn = sqlite3.connect(self.root / 'database.db')
        try:
            conn.execute('INSERT INTO auditoria(fecha,usuario,rol,accion,tipo,nombre,detalle) VALUES(?,?,?,?,?,?,?)',
                         ('2026-09-30T20:00:00+00:00', 'cuenta-prueba', role, action, 'compras', name, detail))
            conn.commit()
        finally:
            conn.close()

    def test_only_ti_account_can_open_view_and_see_card(self):
        self.assertEqual(self.client.get('/auditoria').status_code, 302)
        for role in ('contabilidad', 'marketing', 'mantenimiento'):
            self.login(role)
            with self.client.session_transaction() as current:
                current['rol'] = 'sistemas'  # El servidor recupera el rol real.
            self.assertEqual(self.client.get('/auditoria').status_code, 403)
            self.assertNotIn(b'Ver Auditor', self.client.get('/').data)
        self.login('sistemas')
        self.assertEqual(self.client.get('/auditoria').status_code, 200)
        self.assertIn(b'Ver Auditor', self.client.get('/').data)
        # Incluso otra cuenta con rol sistemas no es la cuenta TI autorizada.
        self.module.USER_ROLES['otra-cuenta-prueba'] = 'sistemas'
        with self.client.session_transaction() as current:
            current['usuario'] = 'otra-cuenta-prueba'
        self.assertEqual(self.client.get('/auditoria').status_code, 403)
        self.assertNotIn(b'Ver Auditor', self.client.get('/').data)

    def test_empty_read_only_page_and_peru_time(self):
        self.login('sistemas')
        self.assertIn('Aún no hay acciones', self.client.get('/auditoria').text)
        self.insert(detail='{"orden_compra":"OC-vinculada.pdf"}')
        response = self.client.get('/auditoria')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('30/09/2026 15:00:00', response.text)
        self.assertIn('OC-vinculada.pdf', response.text)
        self.assertIn('Crear documento', response.text)
        self.assertEqual(self.client.post('/auditoria').status_code, 405)
        conn = sqlite3.connect(self.root / 'database.db')
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0], 1)
        finally:
            conn.close()

    def test_filters_are_combined_and_search_wildcards_are_literal(self):
        self.login('sistemas')
        self.insert('uno_100%.pdf', 'contabilidad', 'editar_documento')
        self.insert('unoX100AAA.pdf', 'sistemas')
        response = self.client.get('/auditoria', query_string={'buscar': 'uno_100%', 'rol': 'contabilidad', 'accion': 'editar_documento'})
        self.assertIn('uno_100%.pdf', response.text)
        self.assertNotIn('unoX100AAA.pdf', response.text)
        self.assertIn('No hay registros', self.client.get('/auditoria', query_string={'buscar': "' OR 1=1 --"}).text)
        self.assertIn('No hay registros', self.client.get('/auditoria', query_string={'rol': "' OR 1=1 --"}).text)

    def test_pagination_latest_first_and_invalid_pages(self):
        self.login('sistemas')
        for n in range(55):
            self.insert('registro-%03d.pdf' % n)
        first = self.client.get('/auditoria', query_string={'rol': 'sistemas'}).text
        self.assertIn('registro-054.pdf', first)
        self.assertNotIn('registro-004.pdf', first)
        self.assertIn('pagina=2', first)
        self.assertIn('rol=sistemas', first)
        last = self.client.get('/auditoria?pagina=999999999999999999999').text
        self.assertIn('Página 2 de 2', last)
        self.assertIn('registro-004.pdf', last)
        self.assertNotIn('registro-054.pdf', last)
        for page in ('abc', '-3', '0'):
            self.assertIn('Página 1 de 2', self.client.get('/auditoria', query_string={'pagina': page}).text)

    def test_stored_text_and_filters_are_escaped(self):
        self.login('sistemas')
        self.insert('<script>alert(1)</script>', detail='{"orden_compra":"<img src=x onerror=alert(1)>"}')
        response = self.client.get('/auditoria').text
        self.assertNotIn('<script>alert(1)</script>', response)
        self.assertNotIn('<img src=x', response)
        self.assertIn('&lt;script&gt;', response)
        self.assertNotIn('value="<script>', self.client.get('/auditoria', query_string={'buscar':'<script>'}).text)


if __name__ == '__main__':
    unittest.main()
