"""
Jinja2 template renderer for network configurations.

This module provides template rendering capabilities for generating
device-specific configurations from reusable templates.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from loguru import logger


class TemplateRenderer:
    """Jinja2 template renderer for network configurations."""

    def __init__(self, template_dir: str | Path | None = None):
        """
        Initialize template renderer.

        Args:
            template_dir: Root directory for templates. If None, uses
                         nso_orchestration/templates/
        """
        if template_dir is None:
            # Default: templates/ directory relative to this file
            template_dir = Path(__file__).parent.parent / "templates"

        self.template_dir = Path(template_dir)

        if not self.template_dir.exists():
            logger.warning(f"Template directory does not exist: {self.template_dir}")
            self.template_dir.mkdir(parents=True, exist_ok=True)

        # Create Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            undefined=StrictUndefined,  # Fail fast if variable is missing
            trim_blocks=True,           # Remove first newline after block
            lstrip_blocks=True,         # Remove leading spaces/tabs before block
            autoescape=False,           # Don't escape XML (we want raw XML)
        )

        logger.debug(f"Template renderer initialized with directory: {self.template_dir}")

    def render(self, template_name: str, **context) -> str:
        """
        Render a template with the given context variables.

        Args:
            template_name: Name of template file (e.g., 'ios-xe/bgp.xml.j2')
            **context: Variables to pass to template

        Returns:
            Rendered template as string

        Raises:
            TemplateNotFound: If template doesn't exist
            UndefinedError: If template uses undefined variable

        Example:
            renderer = TemplateRenderer()
            xml = renderer.render(
                'ios-xe/bgp.xml.j2',
                local_as=65001,
                neighbor_ip='10.0.0.2'
            )
        """
        logger.debug(f"Rendering template: {template_name}")
        logger.debug(f"Context variables: {list(context.keys())}")

        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**context)

            logger.info(f"✓ Template rendered: {template_name} ({len(rendered)} chars)")
            return rendered

        except TemplateNotFound as e:
            logger.error(f"Template not found: {template_name}")
            logger.error(f"Searched in: {self.template_dir}")
            raise
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            raise

    def list_templates(self, pattern: str = "**/*.j2") -> list[Path]:
        """
        List all available templates.

        Args:
            pattern: Glob pattern for matching templates (default: all .j2 files)

        Returns:
            List of template paths relative to template_dir
        """
        templates = list(self.template_dir.glob(pattern))

        # Make paths relative to template_dir
        relative_templates = [
            t.relative_to(self.template_dir) for t in templates
        ]

        logger.debug(f"Found {len(relative_templates)} templates matching '{pattern}'")
        return relative_templates

    def validate_template(self, template_name: str, **sample_context) -> bool:
        """
        Validate a template with sample context.

        Args:
            template_name: Name of template to validate
            **sample_context: Sample variables to test template

        Returns:
            True if template renders without errors
        """
        try:
            self.render(template_name, **sample_context)
            logger.info(f"✓ Template validation passed: {template_name}")
            return True
        except Exception as e:
            logger.error(f"✗ Template validation failed: {template_name} - {e}")
            return False


# Convenience function for simple rendering
def render_template(template_name: str, template_dir: str | Path | None = None, **context) -> str:
    """
    Convenience function to render a template.

    Args:
        template_name: Name of template file
        template_dir: Optional template directory override
        **context: Variables to pass to template

    Returns:
        Rendered template string
    """
    renderer = TemplateRenderer(template_dir=template_dir)
    return renderer.render(template_name, **context)