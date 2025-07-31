import os

from persai.agent.config import load_config_from_template


class TestTemplateLoading:
    def test_load_config_from_template(self, tmp_path):
        """Test loading configuration from Jinja2 template."""
        # Create a simple template
        template_path = tmp_path / "test_template.yaml.j2"
        template_path.write_text(
            """
version: "{{ version }}"
providers:
  inference:
    - provider_id: "{{ provider_id }}"
      config:
        api_key: "{{ env.TEST_API_KEY }}"
"""
        )

        # Set environment variable
        os.environ["TEST_API_KEY"] = "test-key-123"

        try:
            # Load config with context
            config = load_config_from_template(
                template_path, {"version": "2", "provider_id": "test-provider"}
            )

            assert config["version"] == "2"
            assert config["providers"]["inference"][0]["provider_id"] == "test-provider"
            assert (
                config["providers"]["inference"][0]["config"]["api_key"]
                == "test-key-123"
            )
        finally:
            # Clean up
            del os.environ["TEST_API_KEY"]

    def test_load_config_from_template_missing_env(self, tmp_path):
        """Test template loading handles missing environment variables."""
        template_path = tmp_path / "test_template.yaml.j2"
        template_path.write_text(
            """
providers:
{% if env.MISSING_VAR %}
  inference:
    - provider_id: "test"
{% else %}
  inference: []
{% endif %}
"""
        )

        config = load_config_from_template(template_path)
        assert config["providers"]["inference"] == []
