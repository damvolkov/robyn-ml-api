"""Router with automatic body parsing, validation and response handling."""

import inspect
from collections.abc import Callable
from enum import StrEnum
from functools import wraps
from typing import Any

import orjson
from pydantic import BaseModel, ValidationError
from robyn import Response, SubRouter, status_codes
from robyn.robyn import HttpMethod
from robyn.types import Body


class BodyType(StrEnum):
    PYDANTIC = "pydantic"
    JSONABLE = "jsonable"
    RAW = "raw"


def _ensure_body(model_cls: type[BaseModel]) -> type[BaseModel]:
    if issubclass(model_cls, Body):
        return model_cls
    return type(model_cls.__name__, (model_cls, Body), {})


def pre_parse_body(sig: inspect.Signature) -> dict[str, tuple[BodyType, type | None]]:
    parsed: dict[str, tuple[BodyType, type | None]] = {}
    for name, param in sig.parameters.items():
        annotation = param.annotation
        match annotation:
            case type() if issubclass(annotation, BaseModel):
                parsed[name] = (BodyType.PYDANTIC, _ensure_body(annotation))
            case type() if issubclass(annotation, Body):
                parsed[name] = (BodyType.JSONABLE, annotation)
            case type() if annotation is dict:
                parsed[name] = (BodyType.JSONABLE, None)
            case _ if name == "body":
                parsed[name] = (BodyType.JSONABLE, None)
    return parsed


def post_parse_body(
    body_config: dict[str, tuple[BodyType, type | None]],
    kwargs: dict[str, Any],
) -> Response | None:
    for param_name, (body_type, model_cls) in body_config.items():
        if param_name not in kwargs:
            continue
        raw = kwargs[param_name]
        if not isinstance(raw, (str, bytes)):
            continue

        match body_type:
            case BodyType.PYDANTIC:
                try:
                    kwargs[param_name] = model_cls.model_validate_json(raw)
                except ValidationError as ex:
                    return Response(status_code=422, headers={}, description=ex.json())
            case BodyType.JSONABLE:
                try:
                    kwargs[param_name] = orjson.loads(raw)
                except orjson.JSONDecodeError as ex:
                    return Response(status_code=422, headers={}, description=str(ex))
            case BodyType.RAW:
                pass
    return None


def parse_response(result: Any) -> Response:
    match result:
        case Response():
            return result
        case BaseModel():
            return Response(
                status_code=status_codes.HTTP_200_OK,
                headers={"content-type": "application/json"},
                description=result.model_dump_json(indent=4),
            )
        case dict():
            return Response(
                status_code=status_codes.HTTP_200_OK,
                headers={"content-type": "application/json"},
                description=orjson.dumps(result).decode(),
            )
        case _:
            return Response(
                status_code=status_codes.HTTP_200_OK,
                headers={},
                description=str(result),
            )


HTTP_METHODS: tuple[HttpMethod, ...] = (
    HttpMethod.GET,
    HttpMethod.POST,
    HttpMethod.PUT,
    HttpMethod.DELETE,
    HttpMethod.PATCH,
    HttpMethod.HEAD,
    HttpMethod.OPTIONS,
    HttpMethod.TRACE,
    HttpMethod.CONNECT,
)


def _create_method_wrapper(original_method: Callable) -> Callable:
    @wraps(original_method)
    def method_wrapper(*args, **kwargs) -> Callable:
        decorator = original_method(*args, **kwargs)

        def handler_decorator(handler: Callable) -> Callable:
            sig = inspect.signature(handler)
            body_config = pre_parse_body(sig)

            @wraps(handler)
            async def wrapped_handler(*h_args, **h_kwargs):
                if error := post_parse_body(body_config, h_kwargs):
                    return error
                result = await handler(*h_args, **h_kwargs)
                return parse_response(result)

            new_params = [
                param.replace(annotation=body_config[name][1]) if name in body_config else param
                for name, param in sig.parameters.items()
            ]
            wrapped_handler.__signature__ = sig.replace(parameters=new_params)
            return decorator(wrapped_handler)

        return handler_decorator

    return method_wrapper


def _type_wrapper[T](cls: T) -> T:
    for method in HTTP_METHODS:
        method_name = str(method).split(".")[-1].lower()
        if hasattr(cls, method_name):
            original_method = getattr(cls, method_name)
            wrapped_method = _create_method_wrapper(original_method)
            setattr(cls, method_name, wrapped_method)
    return cls


@_type_wrapper
class Router(SubRouter):
    pass
