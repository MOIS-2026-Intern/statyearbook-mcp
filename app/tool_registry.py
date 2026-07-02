# -*- coding: utf-8 -*-
import importlib
import pkgutil
from types import ModuleType

from mcp.server.fastmcp import FastMCP

import app.tools


# app/tools 아래의 도구 모듈을 파일명 순서로 가져온다.
def _iter_tool_modules() -> list[ModuleType]:
    modules = pkgutil.iter_modules(app.tools.__path__)
    module_names = sorted(
        module_info.name
        for module_info in modules
        if not module_info.ispkg and not module_info.name.startswith("_")
    )

    return [
        importlib.import_module(f"{app.tools.__name__}.{module_name}")
        for module_name in module_names
    ]


# MCP 도구를 FastMCP 앱에 등록한다.
def register_tools(mcp: FastMCP) -> None:
    for module in _iter_tool_modules():
        register = getattr(module, "register", None)
        if register is None:
            continue

        register(mcp)
