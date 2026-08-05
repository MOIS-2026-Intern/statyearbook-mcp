# -*- coding: utf-8 -*-
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.tools.service.contact_service import ContactService
from app.tool_descriptions import SEARCH_CONTACTS, SEARCH_CONTACTS_FIELDS


CONTACT_SERVICE = ContactService()


# MCP 등록부와 내부 호출이 같은 서비스 동작을 사용한다.
def search_contacts_data(stat_id: int) -> dict:
    return CONTACT_SERVICE.search_contacts(stat_id)


# stat_id로 특정 통계표의 담당 정보를 조회하는 도구를 등록한다.
def register(mcp: FastMCP) -> None:
    @mcp.tool(description=SEARCH_CONTACTS)
    def search_contacts(
        stat_id: Annotated[
            int,
            Field(description=SEARCH_CONTACTS_FIELDS["stat_id"], ge=1),
        ],
    ) -> dict:
        return search_contacts_data(stat_id)
