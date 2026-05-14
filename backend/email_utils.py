import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.database import settings

logger = logging.getLogger(__name__)

# Set to False after the first auth failure so we stop spamming the log
# with the same traceback on every single lead save.
_smtp_available: bool | None = None  # None = untested, True = ok, False = broken


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_otp_email(to_email: str, otp_code: str) -> None:
    # Always log OTP so it's visible in Railway logs as a fallback
    logger.info("OTP for %s: %s", to_email, otp_code)

    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP not configured — using log-only mode")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your verification code"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email

    text = f"Your verification code is: {otp_code}\n\nIt expires in 10 minutes."
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px">
      <h2 style="margin-bottom:8px">Verify your email</h2>
      <p style="color:#555;margin-bottom:24px">Enter the code below to continue creating your account.</p>
      <div style="font-size:36px;font-weight:700;letter-spacing:8px;color:#4f46e5;margin-bottom:24px">{otp_code}</div>
      <p style="color:#888;font-size:13px">This code expires in 10 minutes. If you didn't request this, ignore this email.</p>
    </div>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], to_email, msg.as_string())
        logger.info("OTP email sent to %s", to_email)
    except smtplib.SMTPAuthenticationError:
        logger.warning("SMTP auth failed — OTP for %s is %s (check Railway logs)", to_email, otp_code)
    except Exception as exc:
        logger.warning("SMTP send failed (%s) — OTP for %s is %s", exc, to_email, otp_code)


def _smtp_send(msg: MIMEMultipart, to_email: str) -> None:
    global _smtp_available

    if _smtp_available is False:
        return  # already known broken — skip silently

    if not _smtp_configured():
        logger.debug("SMTP not configured — skipping send to %s", to_email)
        return

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], to_email, msg.as_string())
        _smtp_available = True
    except smtplib.SMTPAuthenticationError:
        _smtp_available = False
        logger.warning(
            "SMTP authentication failed — email alerts disabled. "
            "Update SMTP_PASSWORD in .env with a valid Gmail App Password: "
            "https://myaccount.google.com/apppasswords"
        )
    except Exception:
        logger.exception("SMTP send failed for %s", to_email)


def send_new_lead_alert(
    to_email: str,
    platform: str,
    intent_score: float,
    summary: str,
    author_name: str | None,
    author_location: str | None,
    source_url: str | None,
) -> None:
    if not _smtp_configured() or _smtp_available is False:
        return

    pct = round(intent_score * 100)
    score_color = "#16a34a" if intent_score >= 0.8 else "#ca8a04" if intent_score >= 0.5 else "#6b7280"
    author_line = author_name or "Unknown"
    if author_location:
        author_line += f" · {author_location}"

    view_link = (
        f'<a href="{source_url}" style="color:#4f46e5">View original post →</a>'
        if source_url else ""
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New {platform.capitalize()} lead — {pct}% intent"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email

    text = (
        f"New lead detected on {platform.capitalize()}\n\n"
        f"Intent score: {pct}%\n"
        f"From: {author_line}\n\n"
        f"Summary: {summary}\n\n"
        f"{source_url or ''}"
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;padding:32px">
      <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">
        New lead · {platform.capitalize()}
      </p>
      <h2 style="margin:0 0 20px;font-size:20px;color:#111827">High-intent signal detected</h2>

      <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:20px">
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="font-size:13px;color:#6b7280;padding:6px 0">Intent score</td>
            <td style="font-size:14px;font-weight:600;color:{score_color};text-align:right;padding:6px 0">{pct}%</td>
          </tr>
          <tr>
            <td style="font-size:13px;color:#6b7280;padding:6px 0;border-top:1px solid #f3f4f6">From</td>
            <td style="font-size:14px;color:#111827;text-align:right;padding:6px 0;border-top:1px solid #f3f4f6">{author_line}</td>
          </tr>
        </table>
      </div>

      <p style="font-size:13px;color:#6b7280;margin:0 0 6px">Summary</p>
      <p style="font-size:14px;color:#111827;margin:0 0 24px;line-height:1.6">{summary}</p>

      {view_link}

      <p style="font-size:12px;color:#d1d5db;margin-top:32px">
        You're receiving this because you have lead monitoring active.
      </p>
    </div>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    _smtp_send(msg, to_email)
