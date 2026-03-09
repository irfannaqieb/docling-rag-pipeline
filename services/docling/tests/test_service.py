import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from fastapi import HTTPException, UploadFile  # noqa: E402

from main import app  # noqa: E402
from routes import health, parse  # noqa: E402
from parser import DoclingParseError, extract_pages, export_docling_artifacts, parse_with_docling  # noqa: E402


class ExportArtifactsTests(unittest.TestCase):
    def test_export_uses_fallback_methods(self) -> None:
        doc = SimpleNamespace(
            to_markdown=lambda: "# Report",
            model_dump=lambda: {"pages": []},
            to_text=lambda: "Report text",
        )

        artifacts, warnings = export_docling_artifacts(doc)

        self.assertEqual(artifacts["markdown"], "# Report")
        self.assertEqual(artifacts["json"], {"pages": []})
        self.assertEqual(artifacts["text"], "Report text")
        self.assertEqual(warnings, [])

    def test_export_raises_when_all_formats_fail(self) -> None:
        doc = SimpleNamespace()

        with self.assertRaises(DoclingParseError):
            export_docling_artifacts(doc)


class ParseWithDoclingTests(unittest.TestCase):
    def test_parse_uses_result_document_when_present(self) -> None:
        doc = SimpleNamespace(
            export_to_markdown=lambda: "# Title",
            export_to_dict=lambda: {"pages": [{"page_number": 1, "text": "Hello"}]},
            export_to_text=lambda: "Hello",
        )
        result = SimpleNamespace(document=doc, status="success")
        converter = SimpleNamespace(convert=lambda _: result)
        fake_docling = SimpleNamespace(DocumentConverter=lambda: converter)
        fake_module = SimpleNamespace(document_converter=fake_docling)

        with patch.dict(sys.modules, {"docling": fake_module, "docling.document_converter": fake_docling}):
            parsed = parse_with_docling("sample.pdf")

        self.assertEqual(parsed["artifacts"]["markdown"], "# Title")
        self.assertEqual(parsed["pages"][0]["text"], "Hello")
        self.assertEqual(parsed["meta"]["docling_meta"]["status"], "success")

    def test_extract_pages_uses_synthetic_fallback(self) -> None:
        pages, warnings = extract_pages(SimpleNamespace(), {"text": "Fallback text"})

        self.assertEqual(pages, [{"page_number": 1, "text": "Fallback text", "blocks": []}])
        self.assertTrue(warnings)


class RouteTests(unittest.TestCase):
    def test_health(self) -> None:
        self.assertEqual(health(), {"status": "ok"})

    def test_app_registers_expected_routes(self) -> None:
        route_paths = {route.path for route in app.routes}

        self.assertIn("/health", route_paths)
        self.assertIn("/parse", route_paths)

    def test_parse_rejects_non_pdf(self) -> None:
        upload = UploadFile(
            filename="notes.txt",
            file=io.BytesIO(b"hello"),
            headers={"content-type": "text/plain"},
        )

        with self.assertRaises(HTTPException) as exc:
            import asyncio

            asyncio.run(parse(upload))

        self.assertEqual(getattr(exc.exception, "status_code", None), 400)
        self.assertEqual(getattr(exc.exception, "detail", None), "Only PDF files are supported")

    def test_parse_returns_payload(self) -> None:
        parsed_payload = {
            "artifacts": {"markdown": "# R", "json": {"pages": []}, "text": "R"},
            "pages": [{"page_number": 1, "text": "R", "blocks": []}],
            "meta": {"parser": "docling", "warnings": [], "artifact_keys": ["json", "markdown", "text"]},
        }
        upload = UploadFile(
            filename="report.pdf",
            file=io.BytesIO(b"%PDF-1.4"),
            headers={"content-type": "application/pdf"},
        )

        with patch("routes.parse_with_docling", return_value=parsed_payload), patch("routes.cleanup_path") as cleanup_mock:
            import asyncio

            response = asyncio.run(parse(upload))

        self.assertTrue(response.ok)
        self.assertEqual(response.file_name, "report.pdf")
        self.assertTrue(response.document_id.startswith("doc_"))
        self.assertEqual(response.meta["parser"], "docling")
        self.assertEqual(response.pages[0].page_number, 1)
        cleanup_mock.assert_called_once()

    def test_parse_returns_500_on_parser_error(self) -> None:
        upload = UploadFile(
            filename="report.pdf",
            file=io.BytesIO(b"%PDF-1.4"),
            headers={"content-type": "application/pdf"},
        )

        with patch("routes.parse_with_docling", side_effect=DoclingParseError("boom")):
            with self.assertRaises(HTTPException) as exc:
                import asyncio

                asyncio.run(parse(upload))

        self.assertEqual(getattr(exc.exception, "status_code", None), 500)
        self.assertEqual(getattr(exc.exception, "detail", None), "boom")


if __name__ == "__main__":
    unittest.main()
