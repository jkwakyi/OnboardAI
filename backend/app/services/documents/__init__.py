"""The Document Upload Service.

The Interface Contracts give it one responsibility - "extracts text from
the file and splits it into sections" - and two jobs around it: it "saves
the original file to File Storage (U2) and the sections to the Main
Database (U3), and passes the sections on to be turned into vectors and
saved (U4)".

What is here so far is U2, from ON-39. Extraction and sections are ON-40
and will arrive as `extraction.py` beside `storage.py`; the Documents API
imports `app.services.documents` and should not have to change when they
do.
"""

from app.services.documents.storage import (
    PDF,
    TXT,
    DocumentTooLarge,
    StoredFile,
    UnsupportedDocument,
    UnusableDocument,
    UploadRefused,
    delete_stored_file,
    detect_content_type,
    safe_filename,
    save_upload,
)

__all__ = [
    "PDF",
    "TXT",
    "DocumentTooLarge",
    "StoredFile",
    "UnsupportedDocument",
    "UnusableDocument",
    "UploadRefused",
    "delete_stored_file",
    "detect_content_type",
    "safe_filename",
    "save_upload",
]
