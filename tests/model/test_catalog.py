"""Offline CLI checks: advertised setup choices must fit the key-only flow."""
import json
from pathlib import Path
import subprocess
import unittest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "services/model"
NETWORK_GUARD = "data:text/javascript," + quote("""
import net from 'node:net';
import http from 'node:http';
import https from 'node:https';
import dns from 'node:dns';
const deny = () => { throw new Error('Catalog attempted network access'); };
net.Socket.prototype.connect = deny;
http.request = http.get = https.request = https.get = deny;
dns.lookup = dns.resolve = deny;
globalThis.fetch = deny;
""")
ERROR = "Model is not available for API-key setup in the installed Pi catalog; use an explicit custom model and host configuration.\n"


class CatalogContract(unittest.TestCase):
    def catalog(self, *args, success=True):
        result = subprocess.run(["node", "--import", NETWORK_GUARD, MODEL / "catalog.mjs", *args], cwd=MODEL,
                                capture_output=True, text=True, timeout=15)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, ERROR)
        return None

    def builtin(self, provider):
        script = "import {getBuiltinModels} from '@earendil-works/pi-ai/providers/all'; console.log(JSON.stringify(getBuiltinModels(process.argv[1])));"
        return json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script, provider], cwd=MODEL, text=True))

    def test_groq_and_openai_roundtrip_preserves_native_semantics_and_endpoint(self):
        providers = self.catalog()
        for provider in ("groq", "openai"):
            with self.subTest(provider=provider):
                self.assertIn(provider, providers)
                models = self.catalog(provider)
                self.assertGreater(len(models), 0)
                selected = models[0]["id"]
                native = next(model for model in self.builtin(provider) if model["id"] == selected)
                resolved = self.catalog(provider, selected)
                self.assertEqual(resolved["endpoint"], native["baseUrl"])
                self.assertEqual(resolved["definition"], {key: value for key, value in native.items() if key not in ("baseUrl", "headers")})

    def test_oauth_only_provider_is_not_advertised_as_api_key_setup(self):
        self.assertNotIn("openai-codex", self.catalog())
        native = self.builtin("openai-codex")
        self.assertGreater(len(native), 0)
        self.catalog("openai-codex", native[0]["id"], success=False)

    def test_endpoint_placeholders_and_empty_routes_are_not_silently_usable(self):
        providers = self.catalog()
        for provider in ("cloudflare-ai-gateway", "cloudflare-workers-ai", "google-vertex", "azure-openai-responses"):
            with self.subTest(provider=provider):
                native = self.builtin(provider)
                self.assertGreater(len(native), 0)
                self.assertTrue(not native[0]["baseUrl"] or "{" in native[0]["baseUrl"])
                self.assertNotIn(provider, providers)
                self.catalog(provider, native[0]["id"], success=False)

    def test_required_static_headers_are_not_discarded_to_make_a_model_appear_usable(self):
        providers = self.catalog()
        for provider in ("github-copilot", "nvidia"):
            with self.subTest(provider=provider):
                native = self.builtin(provider)
                model = next(model for model in native if model.get("headers"))
                self.assertNotIn(provider, providers)
                self.catalog(provider, model["id"], success=False)

    def test_unknown_selection_returns_fixed_generic_error(self):
        self.catalog("missing-provider", success=False)
        self.catalog("groq", "missing-model", success=False)

    def test_catalog_and_dispatch_use_one_api_capability_declaration(self):
        script = "import {supportsAPI} from './pi.mjs'; console.log(JSON.stringify([supportsAPI('openai-completions'),supportsAPI('openai-responses'),supportsAPI('unsupported-test-api')]));"
        self.assertEqual(json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script], cwd=MODEL, text=True)), [True, True, False])


if __name__ == "__main__":
    unittest.main()
