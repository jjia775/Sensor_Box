# test_smtp_hardcoded.py
import smtplib, ssl, sys, datetime
from email.message import EmailMessage

HOST = "smtp-relay.brevo.com"
PORT = 587
USE_SSL = False
USE_STARTTLS = True
USER = "96cd03001@smtp-brevo.com"
PASSWORD = "HAYjKfgbwDa7pI8J"
FROM_ADDR = "sensorbox2025@gmail.com"  # Must be a Brevo-verified sender address
TO_ADDR = "sensorbox2025@gmail.com"
SUBJECT = "SMTP test"
BODY = f"SMTP test at {datetime.datetime.now().isoformat()}"
TIMEOUT = 15
DEBUG = True

def main():
    try:
        if USE_SSL:
            server = smtplib.SMTP_SSL(HOST, PORT, timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(HOST, PORT, timeout=TIMEOUT)
        if DEBUG:
            server.set_debuglevel(1)
        server.ehlo()
        if USE_STARTTLS and not USE_SSL:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(USER, PASSWORD)
        msg = EmailMessage()
        msg["From"] = FROM_ADDR
        msg["To"] = TO_ADDR
        msg["Subject"] = SUBJECT
        msg.set_content(BODY)
        server.send_message(msg)
        server.quit()
        print("OK")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
