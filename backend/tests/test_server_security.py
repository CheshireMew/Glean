import asyncio
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.core.exceptions import ValidationError
from backend.app.core.http_security import HTTPSecurityMiddleware
from backend.app.infrastructure.database import database
from backend.app.infrastructure.repositories import repositories, transactional_repositories
from backend.app.core.outbound_http import resolve_destination, SafeHTTPTransport
from backend.app.core.outbound_smtp import PinnedSMTPSSL
from backend.app.services.ai_budget import AIBudget
from backend.app.services.ai_runtime import AIEndpoint
from backend.reset_admin import reset_account
from backend.tests import test_intelligence_completion as completion_fixtures


class ServerSecurityTest(unittest.TestCase):
    def setUp(self):
        self.old_path = database.db_path
        database.db_path = str(Path(tempfile.mkdtemp(dir=r'D:\Tools', prefix='glean-security-fix-')) / 'test.db')
        self.config = patch.multiple(settings, ENV='test', JWT_SECRET_KEY='', ADMIN_PASSWORD='', ADMIN_USERNAME='')
        self.config.start()
        reset_account('security-admin', 'Security-check!20261004')
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        database.db_path = self.old_path
        self.config.stop()

    def browser_login(self):
        response = self.client.post('/api/login', headers={'X-Glean-Session': 'browser'},
                                    data={'username': 'security-admin', 'password': 'Security-check!20261004'})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_cookie_is_httponly_and_mutation_requires_csrf_even_with_invalid_auth_header(self):
        response = self.browser_login()
        self.assertNotIn('access_token', response.json()['data'])
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        status = self.client.get('/api/session')
        self.assertEqual(status.status_code, 200)
        csrf = status.json()['data']['csrf_token']
        for headers in ({}, {'Authorization': 'Basic dummy'}, {'X-CSRF-Token': 'wrong'}):
            self.assertEqual(self.client.post('/api/logout', headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/logout', headers={'X-CSRF-Token': csrf}).status_code, 200)
        self.assertEqual(self.client.get('/api/session').status_code, 401)

    def test_cross_origin_login_and_unbounded_forms_are_rejected(self):
        data = {'username': 'security-admin', 'password': 'Security-check!20261004'}
        self.assertEqual(self.client.post('/api/login', data=data, headers={'Origin': 'https://attacker.test'}).status_code, 403)
        extra = {**data, **{f'f{i}': 'x' for i in range(8)}}
        self.assertEqual(self.client.post('/api/login', data=extra).status_code, 400)
        self.assertEqual(self.client.post('/api/login', content=b'x' * 4097).status_code, 413)
        self.assertEqual(self.client.post('/api/login', content=iter([b'x' * 3000, b'x' * 3000]),
                         headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 413)
        self.assertEqual(self.client.post('/api/login', content='username=a&username=b&password=c',
                         headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 400)

    def test_production_cookie_and_health_do_not_expose_runtime_details(self):
        with patch.object(settings, 'ENV', 'production'):
            response = self.browser_login()
            self.assertIn('__Host-glean_session=', response.headers['set-cookie'])
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertEqual(self.client.get('/openapi.json').status_code, 404)
            health = self.client.get('/health/pipeline')
            self.assertNotIn('owner', health.text)
            self.assertNotIn('lease', health.text)
            self.assertIn('strict-transport-security', health.headers)

    def test_public_entities_require_published_events_and_drop_private_metadata(self):
        ids = completion_fixtures.IntelligenceCompletionTest._seed_public_event()
        entity = app_services.intelligence_catalog.save_entity({'entity_type': 'organization', 'slug': 'security-entity',
                 'name': 'Security entity', 'description': '', 'metadata': {'internal_note': 'never public'},
                 'aliases': ['internal-alias']})
        self.assertEqual(self.client.get('/api/public/entities/security-entity').status_code, 404)
        app_services.intelligence_catalog.attach_entity(ids['event'], {'entity_id': entity['id'], 'role': 'subject', 'confidence': 1.0, 'source': 'manual'})
        response = self.client.get('/api/public/entities/security-entity')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('metadata', response.json()['data'])
        self.assertNotIn('internal-alias', response.text)
        repositories().publications.execute('UPDATE profile_publications SET is_public=0')
        self.assertEqual(self.client.get('/api/public/entities/security-entity').status_code, 404)
        self.assertEqual(self.client.get(f"/api/public/events/{ids['event']}").status_code, 404)

    def test_per_client_and_global_request_limits(self):
        security = HTTPSecurityMiddleware(None)
        for _ in range(120):
            self.assertTrue(security.allowed('client', 100))
        self.assertFalse(security.allowed('client', 100))
        self.assertTrue(security.allowed('client', 161))
        global_limit = HTTPSecurityMiddleware(None)
        for index in range(1200):
            self.assertTrue(global_limit.allowed(f'client-{index % 20}', 100))
        self.assertFalse(global_limit.allowed('fresh-client', 100))

    def test_production_egress_rejects_private_dns_and_credentials_in_urls(self):
        for host in ('127.0.0.1', '169.254.169.254', '10.0.0.1', '::1', '::ffff:127.0.0.1'):
            with patch.object(settings, 'ENV', 'production'), patch('socket.getaddrinfo', return_value=[(0, 0, 0, '', (host, 80))]):
                with self.assertRaises(ValidationError):
                    resolve_destination('http://rss.example.test')
        with patch.multiple(settings, ENV='production', PRIVATE_ENDPOINT_HOSTS='model.local'):
            with patch('socket.getaddrinfo', return_value=[(0, 0, 0, '', ('127.0.0.1', 80))]):
                self.assertEqual(resolve_destination('http://model.local/v1', 'integration')[1], '127.0.0.1')
                with self.assertRaises(ValidationError):
                    resolve_destination('http://model.local')

    def test_budget_is_shared_across_calls_and_survives_new_clients(self):
        endpoint = AIEndpoint('test', 'dummy', 'https://model.test', 'dummy', 1, 2)
        with patch.multiple(settings, ENV='production', AI_DAILY_MAX_CALLS=2, AI_DAILY_MAX_COST=1):
            AIBudget(transactional_repositories).reserve(endpoint, 's', 'u', 10)
            AIBudget(transactional_repositories).reserve(endpoint, 's', 'u', 10)
            with self.assertRaises(ValidationError):
                AIBudget(transactional_repositories).reserve(endpoint, 's', 'u', 10)
            saved = repositories().config.get_by_prefix('security.ai-budget.')
            self.assertEqual(json.loads(next(iter(saved.values())))['calls'], 2)

    def test_outbound_transport_pins_ip_and_bounds_responses(self):
        async def run():
            sent = []
            async def handle(request):
                sent.append(request)
                return httpx.Response(200, content=b'OK')
            with patch.object(settings, 'ENV', 'production'), patch('socket.getaddrinfo', return_value=[(0, 0, 0, '', ('93.184.216.34', 443))]), \
                 patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=handle):
                async with httpx.AsyncClient(transport=SafeHTTPTransport(max_bytes=100)) as client:
                    response = await client.get('https://public.example.test/a')
                self.assertEqual(response.text, 'OK')
                self.assertEqual(sent[0].url.host, '93.184.216.34')
                self.assertEqual(sent[0].headers['host'], 'public.example.test')
                self.assertEqual(sent[0].extensions['sni_hostname'], 'public.example.test')
            with patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', new=AsyncMock(return_value=httpx.Response(200, content=b'x' * 101))):
                async with httpx.AsyncClient(transport=SafeHTTPTransport(max_bytes=100)) as client:
                    with self.assertRaises(ValidationError):
                        await client.get('https://public.example.test')
            def resolve(host, port, **kwargs):
                address = '169.254.169.254' if host == 'metadata.test' else '93.184.216.34'
                return [(0, 0, 0, '', (address, port))]
            async def redirect(request):
                return httpx.Response(302, headers={'Location': 'http://metadata.test/latest'})
            with patch.object(settings, 'ENV', 'production'), patch('socket.getaddrinfo', side_effect=resolve), \
                    patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=redirect) as network:
                async with httpx.AsyncClient(transport=SafeHTTPTransport(), follow_redirects=True) as client:
                    with self.assertRaises(ValidationError):
                        await client.get('https://public.example.test')
                self.assertEqual(network.call_count, 1)
        asyncio.run(run())

    def test_compressed_stream_cannot_exceed_decoded_limit(self):
        class CompressedStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield gzip.compress(b'x' * 1_000_000)
        async def run():
            response = httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=CompressedStream())
            with patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', new=AsyncMock(return_value=response)):
                async with httpx.AsyncClient(transport=SafeHTTPTransport(max_bytes=2000)) as client:
                    with self.assertRaises(ValidationError):
                        await client.get('https://public.example.test')
        asyncio.run(run())

    def test_smtp_pins_validated_ip_and_preserves_certificate_hostname(self):
        from unittest.mock import Mock
        smtp = object.__new__(PinnedSMTPSSL)
        smtp.destination = '93.184.216.34'
        smtp.source_address = None
        smtp.context = Mock()
        with patch('socket.create_connection') as connect:
            smtp._get_socket('smtp.example.test', 465, 20)
        connect.assert_called_once_with(('93.184.216.34', 465), 20, None)
        smtp.context.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='smtp.example.test')

    def test_invalid_prices_and_usage_cannot_disable_budget(self):
        with patch.multiple(settings, ENV='production', AI_DAILY_MAX_CALLS=10, AI_DAILY_MAX_COST=1):
            for value in (float('nan'), float('inf'), -1):
                with self.assertRaises(ValidationError):
                    AIBudget(transactional_repositories).reserve(AIEndpoint('test', 'dummy', 'https://model.test', 'dummy', value, 2), 's', 'u', 10)
            budget = AIBudget(transactional_repositories)
            reservation = budget.reserve(AIEndpoint('test', 'dummy', 'https://model.test', 'dummy', 1, 2), 's', 'u', 10)
            saved = repositories().config.get_config(reservation[0])
            budget.settle(reservation, -1)
            self.assertEqual(repositories().config.get_config(reservation[0]), saved)
