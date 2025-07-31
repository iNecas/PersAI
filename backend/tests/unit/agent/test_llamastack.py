import os
from unittest.mock import patch

from persai.agent.agent import config_file, get_default_model


class TestConfigFile:
    def test_config_file_uses_template_when_available(self, tmp_path):
        """Test that config_file prefers template over static config."""
        # Create a mock template file
        template_path = tmp_path / "llamastack.yaml.j2"
        template_path.write_text(
            """
version: "2"
models:
  - model_id: "test-model"
    provider_id: "test-provider"
"""
        )

        # Mock the base_dir to point to our tmp_path
        with patch("persai.agent.agent.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            mock_path.return_value.__truediv__.return_value.exists.return_value = True

            # Mock load_config_from_template to return test data
            with patch("persai.agent.agent.load_config_from_template") as mock_load:
                mock_load.return_value = {
                    "version": "2",
                    "models": [
                        {"model_id": "test-model", "provider_id": "test-provider"}
                    ],
                }

                # Mock tempfile.NamedTemporaryFile
                with patch(
                    "persai.agent.agent.tempfile.NamedTemporaryFile"
                ) as mock_temp:
                    mock_temp.return_value.__enter__.return_value.name = str(
                        tmp_path / "test.yaml"
                    )

                    with config_file() as config_path:
                        # Should use template, not static config
                        assert "test.yaml" in config_path
                        mock_load.assert_called_once()

    def test_config_file_falls_back_to_static_config(self, tmp_path):
        """Test that config_file falls back to static config when template fails."""
        # Create a static config file
        static_path = tmp_path / "llamastack.yaml"
        static_path.write_text("version: '2'\nmodels: []")

        # Mock the base_dir to point to our tmp_path
        with patch("persai.agent.agent.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            # Template doesn't exist
            mock_path.return_value.__truediv__.return_value.exists.return_value = False
            mock_path.return_value.__truediv__.return_value.absolute.return_value = (
                static_path
            )

            with config_file() as config_path:
                # Should use static config
                assert config_path == str(static_path)

    def test_config_file_handles_template_rendering_error(self, tmp_path):
        """Test that config_file raises template rendering errors immediately."""
        # Create files
        template_path = tmp_path / "llamastack.yaml.j2"
        template_path.write_text("invalid {{ jinja")
        static_path = tmp_path / "llamastack.yaml"
        static_path.write_text("version: '2'\nmodels: []")

        with patch("persai.agent.agent.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            mock_path.return_value.__truediv__.return_value.exists.return_value = True
            mock_path.return_value.__truediv__.return_value.absolute.return_value = (
                static_path
            )

            # Mock load_config_from_template to raise an error
            with patch(
                "persai.agent.agent.load_config_from_template",
                side_effect=Exception("Template error"),
            ):
                # Should raise the template error immediately instead of falling back
                try:
                    with config_file() as config_path:
                        pass
                    assert False, "Expected exception to be raised"
                except Exception as e:
                    assert str(e) == "Template error"

    def test_config_file_handles_no_models_in_template(self):
        """Test that config_file handles template with no models configured."""
        # This is more of an integration test - test the actual behavior
        with patch.dict(os.environ, {}, clear=True):  # Clear all API keys
            # This should use the template but find no models, then fall back
            with patch("builtins.print") as mock_print:
                with config_file() as config_path:
                    # Should either use static config or show warning
                    # The exact behavior depends on whether static config exists
                    # This test mainly ensures no exceptions are raised
                    assert config_path is not None
                    assert isinstance(config_path, str)


class TestGetDefaultModel:
    def test_get_default_model_from_env(self):
        """Test that get_default_model respects PERSAI_DEFAULT_MODEL environment variable."""
        config_data = {
            "models": [{"model_id": "gpt-4o-mini"}, {"model_id": "claude-3-5-haiku"}]
        }

        with patch.dict(os.environ, {"PERSAI_DEFAULT_MODEL": "claude-3-5-haiku"}):
            model = get_default_model(config_data)
            assert model == "claude-3-5-haiku"

    def test_get_default_model_first_available(self):
        """Test that get_default_model returns first available model when no env var is set."""
        config_data = {
            "models": [{"model_id": "gpt-4o-mini"}, {"model_id": "claude-3-5-haiku"}]
        }

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            model = get_default_model(config_data)
            assert model == "gpt-4o-mini"

    def test_get_default_model_fallback(self):
        """Test that get_default_model returns fallback when no models in config."""
        config_data = {"models": []}

        with patch.dict(os.environ, {}, clear=True):
            model = get_default_model(config_data)
            assert model == "gpt-4o-mini"

    def test_get_default_model_no_models_key(self):
        """Test that get_default_model handles missing models key."""
        config_data = {}

        with patch.dict(os.environ, {}, clear=True):
            model = get_default_model(config_data)
            assert model == "gpt-4o-mini"


class TestSystemPrompt:
    def test_system_prompt_from_env(self):
        """Test that SYSTEM_PROMPT can be overridden by environment variable."""
        custom_prompt = "Custom system prompt for testing"

        with patch.dict(os.environ, {"PERSAI_SYSTEM_PROMPT": custom_prompt}):
            # Need to re-import to get the updated value
            from importlib import reload
            import persai.agent.agent

            reload(persai.agent.agent)

            assert persai.agent.agent.SYSTEM_PROMPT == custom_prompt

    def test_system_prompt_default(self):
        """Test that SYSTEM_PROMPT has default value when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to re-import to get the updated value
            from importlib import reload
            import persai.agent.agent

            reload(persai.agent.agent)

            assert "Prometheus expert" in persai.agent.agent.SYSTEM_PROMPT
