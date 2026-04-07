"""MCP server for iCloud email access via IMAP/SMTP."""

import email
import email.utils
import os
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from imapclient import IMAPClient
from mcp.server.fastmcp import FastMCP

ICLOUD_IMAP_HOST = "imap.mail.me.com"
ICLOUD_IMAP_PORT = 993
ICLOUD_SMTP_HOST = "smtp.mail.me.com"
ICLOUD_SMTP_PORT = 587

mcp = FastMCP(
    "icloud-email",
    description="Accès aux emails iCloud via IMAP/SMTP",
)


def _get_credentials() -> tuple[str, str]:
    apple_id = os.environ.get("ICLOUD_EMAIL")
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not apple_id or not app_password:
        raise ValueError(
            "Variables d'environnement ICLOUD_EMAIL et ICLOUD_APP_PASSWORD requises. "
            "Génère un mot de passe d'app sur https://appleid.apple.com"
        )
    return apple_id, app_password


def _decode_header_value(value: str | None) -> str:
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _connect_imap() -> IMAPClient:
    apple_id, app_password = _get_credentials()
    client = IMAPClient(ICLOUD_IMAP_HOST, port=ICLOUD_IMAP_PORT, ssl=True)
    client.login(apple_id, app_password)
    return client


def _parse_email_summary(msg_data: dict, uid: int) -> dict:
    envelope = msg_data.get(b"ENVELOPE")
    flags = msg_data.get(b"FLAGS", ())
    if envelope is None:
        return {"uid": uid, "error": "No envelope data"}

    from_addrs = envelope.from_ or []
    from_str = ""
    if from_addrs:
        addr = from_addrs[0]
        name = addr.name.decode("utf-8", errors="replace") if addr.name else ""
        mailbox = addr.mailbox.decode() if addr.mailbox else ""
        host = addr.host.decode() if addr.host else ""
        from_str = f"{name} <{mailbox}@{host}>" if name else f"{mailbox}@{host}"

    subject = ""
    if envelope.subject:
        subject = _decode_header_value(envelope.subject.decode("utf-8", errors="replace"))

    date_str = ""
    if envelope.date:
        date_str = envelope.date.strftime("%Y-%m-%d %H:%M")

    is_read = b"\\Seen" in flags

    return {
        "uid": uid,
        "from": from_str,
        "subject": subject,
        "date": date_str,
        "read": is_read,
    }


@mcp.tool()
def list_folders() -> list[str]:
    """Liste tous les dossiers email iCloud."""
    client = _connect_imap()
    try:
        folders = client.list_folders()
        return [folder_name for _flags, _delimiter, folder_name in folders]
    finally:
        client.logout()


@mcp.tool()
def list_emails(folder: str = "INBOX", limit: int = 20, offset: int = 0) -> list[dict]:
    """Liste les emails d'un dossier.

    Args:
        folder: Nom du dossier (défaut: INBOX)
        limit: Nombre max d'emails à retourner (défaut: 20, max: 50)
        offset: Nombre d'emails à sauter depuis le plus récent (défaut: 0)
    """
    limit = min(limit, 50)
    client = _connect_imap()
    try:
        client.select_folder(folder, readonly=True)
        uids = client.search("ALL")
        uids = sorted(uids, reverse=True)  # Plus récents d'abord
        uids = uids[offset : offset + limit]
        if not uids:
            return []
        messages = client.fetch(uids, ["ENVELOPE", "FLAGS"])
        return [_parse_email_summary(messages[uid], uid) for uid in uids if uid in messages]
    finally:
        client.logout()


@mcp.tool()
def read_email(uid: int, folder: str = "INBOX") -> dict:
    """Lit le contenu complet d'un email par son UID.

    Args:
        uid: L'identifiant unique de l'email
        folder: Nom du dossier (défaut: INBOX)
    """
    client = _connect_imap()
    try:
        client.select_folder(folder, readonly=True)
        messages = client.fetch([uid], ["ENVELOPE", "FLAGS", "RFC822"])
        if uid not in messages:
            return {"error": f"Email UID {uid} non trouvé"}

        msg_data = messages[uid]
        summary = _parse_email_summary(msg_data, uid)

        raw = msg_data.get(b"RFC822")
        if not raw:
            summary["body"] = "(impossible de lire le contenu)"
            return summary

        msg = email.message_from_bytes(raw)

        # Extraire les destinataires
        summary["to"] = _decode_header_value(msg.get("To"))
        summary["cc"] = _decode_header_value(msg.get("Cc"))

        # Extraire le corps
        body_text = ""
        body_html = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    filename = part.get_filename() or "sans_nom"
                    attachments.append(
                        {"filename": _decode_header_value(filename), "type": content_type}
                    )
                elif content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_html = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body_text = payload.decode(charset, errors="replace")

        summary["body"] = body_text or body_html
        summary["attachments"] = attachments
        return summary
    finally:
        client.logout()


@mcp.tool()
def search_emails(
    query: str, folder: str = "INBOX", limit: int = 20, criteria: str = "SUBJECT"
) -> list[dict]:
    """Recherche des emails.

    Args:
        query: Texte à rechercher
        folder: Dossier dans lequel chercher (défaut: INBOX)
        limit: Nombre max de résultats (défaut: 20)
        criteria: Critère de recherche - SUBJECT, FROM, TO, BODY, TEXT (défaut: SUBJECT).
                  TEXT cherche partout (sujet + corps + headers).
    """
    limit = min(limit, 50)
    valid_criteria = {"SUBJECT", "FROM", "TO", "BODY", "TEXT"}
    if criteria.upper() not in valid_criteria:
        criteria = "SUBJECT"

    client = _connect_imap()
    try:
        client.select_folder(folder, readonly=True)
        uids = client.search([criteria.upper(), query])
        uids = sorted(uids, reverse=True)[:limit]
        if not uids:
            return []
        messages = client.fetch(uids, ["ENVELOPE", "FLAGS"])
        return [_parse_email_summary(messages[uid], uid) for uid in uids if uid in messages]
    finally:
        client.logout()


@mcp.tool()
def send_email(to: str, subject: str, body: str, cc: str = "", html: bool = False) -> str:
    """Envoie un email via iCloud.

    Args:
        to: Adresse(s) du destinataire (séparées par des virgules si plusieurs)
        subject: Sujet de l'email
        body: Corps de l'email
        cc: Adresse(s) en copie (optionnel)
        html: Si True, le corps est interprété comme HTML (défaut: False)
    """
    apple_id, app_password = _get_credentials()

    msg = MIMEMultipart("alternative") if html else MIMEMultipart()
    msg["From"] = apple_id
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    if html:
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    all_recipients = [addr.strip() for addr in to.split(",")]
    if cc:
        all_recipients.extend(addr.strip() for addr in cc.split(","))

    with smtplib.SMTP(ICLOUD_SMTP_HOST, ICLOUD_SMTP_PORT) as server:
        server.starttls()
        server.login(apple_id, app_password)
        server.send_message(msg, to_addrs=all_recipients)

    return f"Email envoyé à {to}"


@mcp.tool()
def mark_email(uid: int, folder: str = "INBOX", action: str = "read") -> str:
    """Marque un email comme lu/non lu ou le signale.

    Args:
        uid: L'identifiant unique de l'email
        folder: Nom du dossier (défaut: INBOX)
        action: "read", "unread", ou "flagged" (défaut: "read")
    """
    client = _connect_imap()
    try:
        client.select_folder(folder)
        if action == "read":
            client.add_flags([uid], [b"\\Seen"])
            return f"Email {uid} marqué comme lu"
        elif action == "unread":
            client.remove_flags([uid], [b"\\Seen"])
            return f"Email {uid} marqué comme non lu"
        elif action == "flagged":
            client.add_flags([uid], [b"\\Flagged"])
            return f"Email {uid} signalé"
        else:
            return f"Action inconnue: {action}. Utilise 'read', 'unread', ou 'flagged'."
    finally:
        client.logout()


@mcp.tool()
def move_email(uid: int, source: str = "INBOX", destination: str = "Trash") -> str:
    """Déplace un email vers un autre dossier.

    Args:
        uid: L'identifiant unique de l'email
        source: Dossier source (défaut: INBOX)
        destination: Dossier de destination (défaut: Trash)
    """
    client = _connect_imap()
    try:
        client.select_folder(source)
        client.move([uid], destination)
        return f"Email {uid} déplacé de {source} vers {destination}"
    finally:
        client.logout()


@mcp.tool()
def delete_email(uid: int, folder: str = "INBOX") -> str:
    """Supprime un email (le déplace vers la corbeille).

    Args:
        uid: L'identifiant unique de l'email
        folder: Dossier source (défaut: INBOX)
    """
    return move_email(uid, source=folder, destination="Deleted Messages")


if __name__ == "__main__":
    mcp.run()
