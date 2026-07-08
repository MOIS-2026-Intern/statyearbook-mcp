# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.gateways.model_gateway import ModelGatewayConfigurationError
from backend.models.chat import ChatRequest, ChatResponse
from backend.services.chat_service import ChatService


router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        return await ChatService(settings).respond(request)
    except ModelGatewayConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
