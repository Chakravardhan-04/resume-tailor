import pytest
from botocore.exceptions import ClientError

from common import mailer

RESULT = {
    "score": 75,
    "summary": "Python engineer.",
    "bullets": ["Built APIs."],
    "gaps": [{"requirement": "Kubernetes", "category": "nice_to_have", "reason": "Not in resume."}],
}


class FakeSes:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise ClientError({"Error": {"Code": self.error, "Message": "x"}}, "SendEmail")


def test_message_has_text_gaps_and_pdf_attachment():
    msg = mailer.build_message("sender@example.com", "me@example.com", RESULT, b"%PDF-1")
    body = msg.get_body(("plain",)).get_content()
    assert "Match score: 75/100" in body and "Kubernetes (nice to have)" in body
    attachment = next(msg.iter_attachments())
    assert attachment.get_filename() == "tailored-resume.pdf"
    assert attachment.get_content() == b"%PDF-1"
    assert msg["To"] == "me@example.com" and msg["From"] == "sender@example.com"


def test_send_success(monkeypatch):
    ses = FakeSes()
    monkeypatch.setattr(mailer, "_ses", lambda: ses)
    assert mailer.send_result_email("me@example.com", RESULT, b"%PDF") == ("SENT", None)
    call = ses.calls[0]
    assert call["FromEmailAddress"] == "sender@example.com"
    assert call["Destination"] == {"ToAddresses": ["me@example.com"]}


def test_sandbox_rejection_gives_clear_message(monkeypatch):
    monkeypatch.setattr(mailer, "_ses", lambda: FakeSes("MessageRejected"))
    status, message = mailer.send_result_email("me@example.com", RESULT, b"%PDF")
    assert status == "FAILED" and "sandbox" in message and "download the PDF" in message


def test_other_ses_errors_do_not_raise(monkeypatch):
    monkeypatch.setattr(mailer, "_ses", lambda: FakeSes("Throttling"))
    assert mailer.send_result_email("me@example.com", RESULT, b"%PDF")[0] == "FAILED"


def test_missing_sender_config(monkeypatch):
    monkeypatch.delenv("SENDER_EMAIL")
    assert mailer.send_result_email("me@example.com", RESULT, b"")[0] == "FAILED"


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "a b@c.com", "a@b.com\nBcc: x@y.com", None, 5])
def test_validate_email_rejects(bad):
    from common.errors import InputError
    from common.guardrails import validate_email

    with pytest.raises(InputError):
        validate_email(bad)
