"""Pydantic request/response models for the OpenAI-compatible API."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class MessageAttachment(BaseModel):
    """A document attached to a chat message (see ``server/attachments.py``)."""

    name: str
    format: str = ""
    text: str = ""
    truncated: bool = False
    note: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str = ""
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    # Locus extensions, read from /v1/attachments. Images are base64 JPEGs for
    # vision models; attachments are documents, folded into the prompt.
    images: Optional[List[str]] = None
    attachments: Optional[List[MessageAttachment]] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    # Locus extension: search the web for the latest user message first.
    web_search: bool = False
    # Locus extension: "chat" answers with the model alone, "agent" runs a
    # tool-using agent, and "developer" runs one kept inside project_dir.
    # Unset keeps the server's configured agent.
    mode: Optional[Literal["chat", "agent", "developer"]] = None
    project_dir: Optional[str] = None


class ApprovalAnswer(BaseModel):
    # "approve_tool" also approves later calls to the same tool in this run;
    # "always" saves a lasting rule (change-level calls only).
    decision: Literal["approve", "approve_tool", "always", "deny"]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AudioMeta(BaseModel):
    url: str


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: Optional[str] = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    audio: Optional[AudioMeta] = None


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class ComplexityInfo(BaseModel):
    score: float
    tier: str
    suggested_max_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[Choice] = Field(default_factory=list)
    usage: UsageInfo = Field(default_factory=UsageInfo)
    complexity: Optional[ComplexityInfo] = None


# ---------------------------------------------------------------------------
# Streaming chunk models
# ---------------------------------------------------------------------------


class DeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    # Streaming tool_calls (OpenAI delta shape, with `index`). Present only
    # on streamed raw function-calling responses (stream:true + tools).
    tool_calls: Optional[List[Dict[str, Any]]] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[StreamChoice] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Models endpoint
# ---------------------------------------------------------------------------


class ModelObject(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "locus"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelObject] = Field(default_factory=list)


__all__ = [
    "ChatCompletionChunk",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "Choice",
    "ChoiceMessage",
    "ComplexityInfo",
    "DeltaMessage",
    "ModelListResponse",
    "ModelObject",
    "StreamChoice",
    "UsageInfo",
]
