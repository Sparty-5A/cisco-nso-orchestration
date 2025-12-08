"""Tests for template renderer."""

import pytest
from jinja2 import TemplateNotFound, UndefinedError

from automation.template_renderer import (
    TemplateRenderer,
    render_template,
)


class TestTemplateRenderer:
    """Test template rendering functionality."""

    def test_renderer_initialization(self):
        """Test renderer initializes with default template directory."""
        renderer = TemplateRenderer()
        assert renderer.template_dir.exists()
        assert renderer.template_dir.name == "templates"

    def test_render_bgp_template(self):
        """Test rendering BGP service template."""
        renderer = TemplateRenderer()

        # Test data
        context = {
            "local_as": 65001,
            "router_id": "10.100.100.1",
            "neighbors": [
                {
                    "neighbor_ip": "10.0.0.2",
                    "remote_as": 65002,
                    "description": "Core router",
                    "password": None,
                    "update_source": "Loopback0",
                }
            ],
            "import_policy": "BGP-IMPORT",
            "export_policy": "BGP-EXPORT",
        }

        xml = renderer.render("ios-xe/bgp_service.xml.j2", **context)

        # Verify template was rendered
        assert xml is not None
        assert len(xml) > 0

        # Verify key elements are present
        assert "<router" in xml
        assert "<bgp>" in xml
        assert "65001" in xml  # Local AS
        assert "10.100.100.1" in xml  # Router ID
        assert "10.0.0.2" in xml  # Neighbor IP
        assert "65002" in xml  # Remote AS
        assert "Core router" in xml  # Description
        assert "Loopback0" in xml  # Update source

        # Verify no Jinja2 placeholders remain
        assert "{{" not in xml
        assert "}}" not in xml

    def test_render_with_optional_fields(self):
        """Test rendering with optional neighbor fields."""
        renderer = TemplateRenderer()

        context = {
            "local_as": 65001,
            "router_id": "10.100.100.1",
            "neighbors": [
                {
                    "neighbor_ip": "10.0.0.2",
                    "remote_as": 65002,
                    "description": "Test neighbor",
                    "password": "SecurePass123",  # Optional field
                    "update_source": "Loopback100",  # Optional field
                }
            ],
            "import_policy": None,  # Optional
            "export_policy": None,  # Optional
        }

        xml = renderer.render("ios-xe/bgp_service.xml.j2", **context)

        # Verify optional fields are present when provided
        assert "SecurePass123" in xml
        assert "Loopback100" in xml

    def test_render_template_not_found(self):
        """Test error when template doesn't exist."""
        renderer = TemplateRenderer()

        with pytest.raises(TemplateNotFound):
            renderer.render("nonexistent/template.j2")

    def test_render_missing_variable(self):
        """Test error when required variable is missing."""
        renderer = TemplateRenderer()

        # Missing 'router_id' variable
        context = {
            "local_as": 65001,
            # router_id missing!
            "neighbors": [],
        }

        with pytest.raises(UndefinedError):
            renderer.render("ios-xe/bgp_service.xml.j2", **context)

    def test_list_templates(self):
        """Test listing available templates."""
        renderer = TemplateRenderer()

        templates = renderer.list_templates()

        # Should find at least the BGP template
        template_names = [str(t) for t in templates]
        assert any("bgp_service.xml.j2" in name for name in template_names)

    def test_validate_template(self):
        """Test template validation with sample context."""
        renderer = TemplateRenderer()

        sample_context = {
            "local_as": 65001,
            "router_id": "10.100.100.1",
            "neighbors": [
                {
                    "neighbor_ip": "10.0.0.2",
                    "remote_as": 65002,
                    "description": "Test",
                    "password": None,
                    "update_source": None,
                }
            ],
            "import_policy": None,
            "export_policy": None,
        }

        # Should return True for valid template
        is_valid = renderer.validate_template("ios-xe/bgp_service.xml.j2", **sample_context)
        assert is_valid is True

    def test_validate_template_invalid(self):
        """Test template validation fails with invalid context."""
        renderer = TemplateRenderer()

        # Invalid context (missing required fields)
        invalid_context = {
            "local_as": 65001,
            # Missing router_id, neighbors
        }

        is_valid = renderer.validate_template("ios-xe/bgp_service.xml.j2", **invalid_context)
        assert is_valid is False

    def test_convenience_function(self):
        """Test convenience render_template function."""
        xml = render_template(
            "ios-xe/bgp_service.xml.j2",
            local_as=65001,
            router_id="10.1.1.1",
            neighbors=[],
            import_policy=None,
            export_policy=None,
        )

        assert xml is not None
        assert "65001" in xml
        assert "10.1.1.1" in xml

    def test_multiple_neighbors(self):
        """Test rendering with multiple BGP neighbors."""
        renderer = TemplateRenderer()

        context = {
            "local_as": 65001,
            "router_id": "10.100.100.1",
            "neighbors": [
                {
                    "neighbor_ip": "10.0.0.2",
                    "remote_as": 65002,
                    "description": "Neighbor 1",
                    "password": None,
                    "update_source": None,
                },
                {
                    "neighbor_ip": "10.0.0.3",
                    "remote_as": 65003,
                    "description": "Neighbor 2",
                    "password": "SecurePass",
                    "update_source": "Loopback0",
                },
                {
                    "neighbor_ip": "10.0.0.4",
                    "remote_as": 65004,
                    "description": "Neighbor 3",
                    "password": None,
                    "update_source": None,
                },
            ],
            "import_policy": None,
            "export_policy": None,
        }

        xml = renderer.render("ios-xe/bgp_service.xml.j2", **context)

        # Verify all neighbors are present
        assert "10.0.0.2" in xml
        assert "10.0.0.3" in xml
        assert "10.0.0.4" in xml
        assert "65002" in xml
        assert "65003" in xml
        assert "65004" in xml
        assert "Neighbor 1" in xml
        assert "Neighbor 2" in xml
        assert "Neighbor 3" in xml


def test_render_preserves_xml_structure():
    """Test that rendered XML is well-formed."""
    xml = render_template(
        "ios-xe/bgp_service.xml.j2",
        local_as=65001,
        router_id="10.1.1.1",
        neighbors=[
            {
                "neighbor_ip": "10.0.0.2",
                "remote_as": 65002,
                "description": "Test",
                "password": None,
                "update_source": None,
            }
        ],
        import_policy=None,
        export_policy=None,
    )

    # Basic XML structure checks
    assert xml.startswith("<config")  # ✅ CORRECT - NETCONF wrapper
    assert "<router" in xml
    assert "<bgp>" in xml
    assert "</bgp>" in xml
    assert "</router>" in xml
    assert "</config>" in xml

    # Check proper nesting
    bgp_start = xml.find("<bgp>")
    bgp_end = xml.find("</bgp>")
    assert bgp_start < bgp_end