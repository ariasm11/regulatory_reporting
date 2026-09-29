import tempfile
import unittest
from pathlib import Path
from siter.hosted import public_origin,bootstrap
from siter.service import Service,Problem


class HostedTests(unittest.TestCase):
    def test_https_origin_is_fixed_not_request_derived(self):
        self.assertEqual(public_origin('https://demo.example/'),'https://demo.example')
        for value in ('http://demo.example','https://','https://user:pass@demo.example','https://demo.example/path','https://demo.example?x=1'):
            with self.assertRaises(ValueError): public_origin(value)

    def test_bootstrap_requires_secret_and_never_resets_existing_users(self):
        with tempfile.TemporaryDirectory() as d:
            s=Service(Path(d))
            try:
                with self.assertRaises(ValueError):bootstrap(s,'','')
                self.assertTrue(bootstrap(s,'analyst','test-only-password'))
                token,_=s.login('analyst','test-only-password')
                self.assertFalse(bootstrap(s,'analyst','different-password'))
                self.assertEqual(s.session(token)['username'],'analyst')
                with self.assertRaises(Problem):s.login('analyst','different-password')
            finally:s.close()

    def test_fresh_ephemeral_instance_recreates_login(self):
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                s=Service(Path(d),ephemeral=True)
                try:
                    self.assertTrue(bootstrap(s,'analyst','test-only-password'))
                    token,_=s.login('analyst','test-only-password')
                    self.assertTrue(s.config(s.session(token)['username'])['ephemeral'])
                finally:s.close()
