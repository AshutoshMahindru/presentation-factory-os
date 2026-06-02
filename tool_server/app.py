from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from tool_server.parsers.web_parser import WebParser
from tool_server.parsers.pdf_parser import PDFParser
from tool_server.parsers.deterministic_doc_parser import DeterministicDocParser
from tool_server.policy import SourceQualityPolicy

app = FastAPI(title="PFOS Tool Server", version="3.2.4")

web_parser = WebParser()
pdf_parser = PDFParser()
doc_parser = DeterministicDocParser()
policy = SourceQualityPolicy()


class ParseWebRequest(BaseModel):
    uri: str
    html: str


class ParseWebResponse(BaseModel):
    uri: str
    title: str | None
    text: str
    quality_score: dict[str, Any]
    parser_provenance: dict[str, Any]


@app.post("/tools/parse_web", response_model=ParseWebResponse)
async def parse_web(req: ParseWebRequest) -> ParseWebResponse:
    result = web_parser.parse(req.html, req.uri)
    score = policy.score_web(req.uri, result.title, result.text)
    return ParseWebResponse(
        uri=result.uri,
        title=result.title,
        text=result.text,
        quality_score=score,
        parser_provenance=result.parser_provenance,
    )


@app.post("/tools/parse_pdf")
async def parse_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    result = pdf_parser.parse(raw, filename=file.filename)
    score = policy.score_pdf(file.filename, result.text, result.page_count)
    return {
        "filename": result.filename,
        "title": result.title,
        "text": result.text[:2000],  # truncate for API response; full text in storage
        "page_count": result.page_count,
        "quality_score": score,
        "parser_provenance": result.parser_provenance,
    }


@app.post("/tools/parse_document")
async def parse_document(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    result = doc_parser.parse(raw, filename=file.filename)
    score = policy.score_document(file.filename, result.paragraphs)
    return {
        "filename": result.filename,
        "paragraphs": result.paragraphs[:50],  # truncate
        "text_preview": result.text[:2000],
        "quality_score": score,
        "parser_provenance": result.parser_provenance,
    }


# --- Step 109: deterministic formula compilation ---


class CompileFinancialSpecRequest(BaseModel):
    project_id: str
    spec: dict[str, Any]


class CompileFinancialSpecResponse(BaseModel):
    project_id: str
    scenario: str
    cells: list[dict[str, Any]]
    warnings: list[str]


@app.post("/tools/compile_financial_spec", response_model=CompileFinancialSpecResponse)
async def compile_financial_spec(
    req: CompileFinancialSpecRequest,
) -> CompileFinancialSpecResponse:
    from financial_model.spec_compiler import FinancialSpecCompiler
    from financial_model.validator import FinancialModelValidator

    compiler = FinancialSpecCompiler()
    result = compiler.compile(req.spec, project_id=req.project_id)

    # The compile result is then run through the existing validator so the
    # caller gets a guarantee that the cells are export-ready (modulo
    # the actual storage write, which lives in step 141).
    cells_as_dicts = [c.to_validator_dict() for c in result.cells]
    validation = FinancialModelValidator().validate_cells(cells_as_dicts)
    if not validation.valid:
        # Compilation succeeded but the cells are malformed — surface
        # the validation errors as a 422-style failure. The agent will
        # see both warnings and validation errors.
        return CompileFinancialSpecResponse(
            project_id=req.project_id,
            scenario=str(req.spec.get("scenario", "base")),
            cells=[],
            warnings=[
                *result.warnings,
                f"validation failed: {'; '.join(validation.errors)}",
            ],
        )

    return CompileFinancialSpecResponse(
        project_id=req.project_id,
        scenario=str(req.spec.get("scenario", "base")),
        cells=cells_as_dicts,
        warnings=list(result.warnings),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("TOOL_SERVER_PORT", "8001")))
