"""
Servicio de envío de emails.
Configura en Railway (Variables):
  SMTP_HOST     smtp.gmail.com  (o el de tu proveedor)
  SMTP_PORT     587
  SMTP_USER     tu@email.com
  SMTP_PASSWORD contraseña o app-password
  FROM_NAME     GestiónPro      (opcional)
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _cfg():
    return {
        "host":     os.getenv("SMTP_HOST", ""),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_name": os.getenv("FROM_NAME", "GestiónPro"),
    }


def smtp_configurado() -> bool:
    cfg = _cfg()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


def enviar_email(destinatario: str, asunto: str, html: str) -> bool:
    """Envía un email. Devuelve True si tuvo éxito."""
    cfg = _cfg()
    if not smtp_configurado():
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(cfg["user"], destinatario, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def email_recuperar_password(destinatario: str, nombre: str, enlace: str) -> bool:
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <body style="font-family:Arial,sans-serif;background:#f3f4f6;padding:30px;">
      <div style="max-width:480px;margin:auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <div style="background:#1E40AF;padding:28px 32px;">
          <h1 style="color:white;margin:0;font-size:22px;">⚙ GestiónPro</h1>
        </div>
        <div style="padding:32px;">
          <h2 style="color:#1f2937;margin-top:0;">Restablecer contraseña</h2>
          <p style="color:#6b7280;">Hola <strong>{nombre}</strong>,</p>
          <p style="color:#6b7280;">Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.</p>
          <p style="color:#6b7280;">Haz clic en el botón para crear una nueva contraseña. Este enlace es válido durante <strong>1 hora</strong>.</p>
          <div style="text-align:center;margin:32px 0;">
            <a href="{enlace}" style="background:#1E40AF;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;">
              Restablecer contraseña
            </a>
          </div>
          <p style="color:#9ca3af;font-size:13px;">Si no solicitaste este cambio, ignora este email. Tu contraseña no cambiará.</p>
          <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;"/>
          <p style="color:#9ca3af;font-size:12px;text-align:center;">GestiónPro · Soporte empresarial</p>
        </div>
      </div>
    </body>
    </html>
    """
    return enviar_email(destinatario, "Restablecer contraseña - GestiónPro", html)
