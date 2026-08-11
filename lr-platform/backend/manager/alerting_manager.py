import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


def send_alert(subject, message, severity='info'):
    results = []
    email_to = os.getenv('ALERT_EMAIL_TO')
    if email_to:
        results.append(_send_email(email_to, subject, message, severity))

    webhook = os.getenv('WHATSAPP_WEBHOOK_URL')
    if webhook:
        results.append(_send_whatsapp_webhook(webhook, subject, message, severity))

    if not results:
        return [{'channel': 'none', 'success': False, 'message': 'No alert channels configured'}]
    return results


def _send_email(email_to, subject, message, severity):
    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT', '587'))
    username = os.getenv('SMTP_USERNAME')
    password = os.getenv('SMTP_PASSWORD')
    email_from = os.getenv('ALERT_EMAIL_FROM', username or 'alerts@localhost')
    if not host:
        return {'channel': 'email', 'success': False, 'message': 'SMTP_HOST is not configured'}

    msg = EmailMessage()
    msg['Subject'] = f'[{severity.upper()}] {subject}'
    msg['From'] = email_from
    msg['To'] = email_to
    msg.set_content(message)

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return {'channel': 'email', 'success': True}
    except Exception as error:
        return {'channel': 'email', 'success': False, 'message': str(error)}


def _send_whatsapp_webhook(webhook, subject, message, severity):
    payload = json.dumps({'subject': subject, 'message': message, 'severity': severity}).encode('utf-8')
    request = urllib.request.Request(webhook, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {'channel': 'whatsapp', 'success': response.status < 300}
    except Exception as error:
        return {'channel': 'whatsapp', 'success': False, 'message': str(error)}
