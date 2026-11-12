import os
from pathlib import Path

from imap_tools import MailBox

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

EMAIL = os.getenv("YANDEX_EMAIL")
APP_PASSWORD = os.getenv("YANDEX_APP_PASSWORD")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.yandex.ru")


def open_mailbox():
    mailbox = MailBox(IMAP_HOST).login(EMAIL, APP_PASSWORD)
    mailbox.folder.set("INBOX")
    return mailbox
