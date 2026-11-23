from common import pdf


def _result(gaps):
    return {
        "score": 67,
        "summary": "Engineer <b>with</b> Python & AWS experience.",
        "bullets": ["Built REST APIs in Python & Flask.", "Deployed to AWS Lambda."],
        "gaps": gaps,
    }


def test_build_pdf_with_gaps():
    gaps = [{"requirement": "Kubernetes", "category": "nice_to_have", "reason": "Not mentioned <anywhere>"}]
    data = pdf.build_pdf(_result(gaps))
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_build_pdf_without_gaps():
    assert pdf.build_pdf(_result([])).startswith(b"%PDF")
