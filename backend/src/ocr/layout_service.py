"""HTTP común de los servicios de challengers de layout (solo perfil lab)."""

from __future__ import annotations

import base64
import binascii

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ocr.extraction import DocumentPage
from ocr.layout import DocumentLayoutEngine, LayoutEvidence


class LayoutPageRequest(BaseModel):
    content_base64: str = Field(min_length=1)
    content_type: str = Field(min_length=1)


class LayoutRequest(BaseModel):
    pages: list[LayoutPageRequest] = Field(min_length=1, max_length=100)


def create_layout_app(engine: DocumentLayoutEngine) -> FastAPI:
    """Crea un servicio aislado que expone solo la medición comparable de layout."""
    app = FastAPI(title=f"Autoken {engine.name} layout challenger", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "engine": engine.name}

    @app.post("/layout", response_model=LayoutEvidence)
    async def layout(request: LayoutRequest) -> LayoutEvidence:
        try:
            pages = [
                DocumentPage(
                    base64.b64decode(page.content_base64, validate=True), page.content_type
                )
                for page in request.pages
            ]
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="content_base64 no es válido") from exc
        return await engine.extract_layout(pages)

    return app
