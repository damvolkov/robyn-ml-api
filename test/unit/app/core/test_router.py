"""Tests for custom router with body parsing and response handling."""

import pytest
from pydantic import BaseModel
from robyn import Response

from app.core.router import BodyType, parse_response, post_parse_body, pre_parse_body


# -----------------------------------------------------------------------------
# Test Models
# -----------------------------------------------------------------------------


class SampleModel(BaseModel):
    """Sample Pydantic model for testing."""

    name: str
    value: int


# -----------------------------------------------------------------------------
# pre_parse_body Tests
# -----------------------------------------------------------------------------


class TestPreParseBody:
    """Tests for pre_parse_body function."""

    def test_pydantic_model_annotation(self) -> None:
        """Verify Pydantic model annotations are detected."""

        async def handler(body: SampleModel) -> None:
            pass

        import inspect

        sig = inspect.signature(handler)
        result = pre_parse_body(sig)

        assert "body" in result
        assert result["body"][0] == BodyType.PYDANTIC

    def test_dict_annotation(self) -> None:
        """Verify dict annotations are detected as JSONABLE."""

        async def handler(data: dict) -> None:
            pass

        import inspect

        sig = inspect.signature(handler)
        result = pre_parse_body(sig)

        assert "data" in result
        assert result["data"][0] == BodyType.JSONABLE

    def test_body_named_parameter(self) -> None:
        """Verify parameter named 'body' is detected as JSONABLE."""

        async def handler(body) -> None:
            pass

        import inspect

        sig = inspect.signature(handler)
        result = pre_parse_body(sig)

        assert "body" in result
        assert result["body"][0] == BodyType.JSONABLE

    def test_no_body_parameters(self) -> None:
        """Verify handlers without body params return empty dict."""

        async def handler(request, global_dependencies) -> None:
            pass

        import inspect

        sig = inspect.signature(handler)
        result = pre_parse_body(sig)

        assert result == {}


# -----------------------------------------------------------------------------
# post_parse_body Tests
# -----------------------------------------------------------------------------


class TestPostParseBody:
    """Tests for post_parse_body function."""

    def test_pydantic_valid_json(self) -> None:
        """Verify valid JSON is parsed into Pydantic model."""
        body_config = {"body": (BodyType.PYDANTIC, SampleModel)}
        kwargs = {"body": '{"name": "test", "value": 42}'}

        error = post_parse_body(body_config, kwargs)

        assert error is None
        assert isinstance(kwargs["body"], SampleModel)
        assert kwargs["body"].name == "test"
        assert kwargs["body"].value == 42

    def test_pydantic_invalid_json(self) -> None:
        """Verify invalid JSON returns 422 Response."""
        body_config = {"body": (BodyType.PYDANTIC, SampleModel)}
        kwargs = {"body": '{"name": "test"}'}  # missing 'value'

        error = post_parse_body(body_config, kwargs)

        assert isinstance(error, Response)
        assert error.status_code == 422

    def test_jsonable_valid_json(self) -> None:
        """Verify valid JSON is parsed to dict."""
        body_config = {"data": (BodyType.JSONABLE, None)}
        kwargs = {"data": '{"key": "value"}'}

        error = post_parse_body(body_config, kwargs)

        assert error is None
        assert kwargs["data"] == {"key": "value"}

    def test_jsonable_invalid_json(self) -> None:
        """Verify invalid JSON returns 422 Response."""
        body_config = {"data": (BodyType.JSONABLE, None)}
        kwargs = {"data": "not valid json"}

        error = post_parse_body(body_config, kwargs)

        assert isinstance(error, Response)
        assert error.status_code == 422

    def test_raw_body_unchanged(self) -> None:
        """Verify RAW body type leaves data unchanged."""
        body_config = {"data": (BodyType.RAW, None)}
        original = b"raw bytes"
        kwargs = {"data": original}

        error = post_parse_body(body_config, kwargs)

        assert error is None
        assert kwargs["data"] == original

    def test_missing_param_ignored(self) -> None:
        """Verify missing parameters don't cause errors."""
        body_config = {"body": (BodyType.PYDANTIC, SampleModel)}
        kwargs = {}  # body not in kwargs

        error = post_parse_body(body_config, kwargs)

        assert error is None


# -----------------------------------------------------------------------------
# parse_response Tests
# -----------------------------------------------------------------------------


class TestParseResponse:
    """Tests for parse_response function."""

    def test_response_passthrough(self) -> None:
        """Verify Response objects pass through unchanged."""
        original = Response(status_code=201, headers={}, description="created")
        result = parse_response(original)
        assert result is original

    def test_pydantic_model_to_json(self) -> None:
        """Verify Pydantic models are serialized to JSON."""
        model = SampleModel(name="test", value=123)
        result = parse_response(model)

        assert result.status_code == 200
        assert result.headers["content-type"] == "application/json"
        assert "test" in result.description
        assert "123" in result.description

    def test_dict_to_json(self) -> None:
        """Verify dicts are serialized to JSON."""
        data = {"key": "value", "num": 42}
        result = parse_response(data)

        assert result.status_code == 200
        assert result.headers["content-type"] == "application/json"
        assert "key" in result.description
        assert "value" in result.description

    def test_other_to_string(self) -> None:
        """Verify other types are converted to string."""
        result = parse_response("plain text")
        assert result.status_code == 200
        assert result.description == "plain text"

    @pytest.mark.parametrize(
        ("input_val", "expected_type"),
        [
            (Response(status_code=200, headers={}, description=""), Response),
            (SampleModel(name="x", value=1), Response),
            ({"a": 1}, Response),
            ("text", Response),
            (123, Response),
        ],
    )
    def test_always_returns_response(self, input_val, expected_type) -> None:
        """Verify parse_response always returns a Response."""
        result = parse_response(input_val)
        assert isinstance(result, expected_type)
