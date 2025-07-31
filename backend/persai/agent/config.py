import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger


def load_config_from_template(
    template_path: Path, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Load configuration from a Jinja2 template file."""
    if context is None:
        context = {}

    logger.info("Loading configuration from template", template_path=str(template_path))

    # Add environment variables to context
    context["env"] = os.environ

    # Load and render template
    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)
    rendered = template.render(context)

    # Parse YAML
    config = yaml.safe_load(rendered)
    
    logger.info("Configuration loaded successfully", 
        template_path=str(template_path),
        config_size=len(rendered),
        has_providers=bool(config.get("providers"))
    )
    
    return config
