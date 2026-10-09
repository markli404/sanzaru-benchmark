"""Public releases must not depend on a private provider deployment."""
import os
import unittest
from unittest.mock import patch

from sanzaru.cli.api import _endpoint


class PublicConfigTests(unittest.TestCase):
    def test_qwen_requires_explicit_endpoint(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'QWEN_BASE_URL'):
                _endpoint('qwen-example')

    def test_qwen_endpoint_and_key_from_environment(self):
        with patch.dict(os.environ, {
            'QWEN_BASE_URL': 'http://localhost:8000/v1', 'QWEN_API_KEY': 'test-key',
        }, clear=True):
            self.assertEqual(_endpoint('qwen-example'), (
                'http://localhost:8000/v1', 'test-key', {'enable_thinking': False}))

    def test_provider_default_and_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_endpoint('deepseek-example')[0], 'https://api.deepseek.com/v1')
        with patch.dict(os.environ, {'DEEPSEEK_BASE_URL': 'http://localhost:8000/v1'}, clear=True):
            self.assertEqual(_endpoint('deepseek-example')[0], 'http://localhost:8000/v1')
