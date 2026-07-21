import unittest

from backend.config import Settings
from backend.gateways.bizrouter_gateway import BizRouterConfigurationError, BizRouterGateway
from backend.gateways.model_gateway import create_model_gateway


class ModelProviderConfigTests(unittest.TestCase):
    def test_openai_provider_uses_openai_credentials(self) -> None:
        settings = Settings(
            model_provider="openai",
            openai_api_key="openai-key",
            bizrouter_api_key="bizrouter-key",
        )

        self.assertTrue(settings.model_configured)

    def test_bizrouter_provider_uses_compatible_endpoint(self) -> None:
        settings = Settings(
            model_provider="bizrouter",
            chat_model="openai/gpt-5-nano",
            openai_api_key="openai-key",
            bizrouter_api_key="bizrouter-key",
            bizrouter_base_url="https://api.bizrouter.ai/v1/",
        )

        self.assertTrue(settings.model_configured)
        gateway = create_model_gateway(settings)
        self.assertIsInstance(gateway, BizRouterGateway)
        self.assertEqual(str(gateway._client.base_url), "https://api.bizrouter.ai/v1/")

    def test_bizrouter_provider_requires_its_own_key(self) -> None:
        settings = Settings(
            model_provider="bizrouter",
            openai_api_key="openai-key",
            bizrouter_api_key=None,
        )

        self.assertFalse(settings.model_configured)
        with self.assertRaisesRegex(
            BizRouterConfigurationError,
            "STATYEARBOOK_BACKEND_BIZROUTER_API_KEY is not configured",
        ):
            create_model_gateway(settings)


if __name__ == "__main__":
    unittest.main()
