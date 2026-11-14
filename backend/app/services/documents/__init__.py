"""The Document Upload Service.

The Interface Contracts give it one responsibility - "extracts text from
the file and splits it into sections" - and two jobs around it: it "saves
the original file to File Storage (U2) and the sections to the Main
Database (U3), and passes the sections on to be turned into vectors and
saved (U4)".

`storage.py` is U2 from ON-39, `extraction.py` and `indexing.py` are U3
from ON-40. U4 - handing the sections on to be turned into vectors - is
ON-41 and will arrive beside them; the Documents API imports
`app.services.documents` and should not have to change when it does.
"""

from app.services.documents.extraction import (
    SectionText,
    UnreadableDocument,
    clean_heading,
    extract_text,
    looks_like_a_heading,
    split_into_sections,
)
from app.services.documents.indexing import index_document
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
    "SectionText",
    "StoredFile",
    "UnsupportedDocument",
    "UnusableDocument",
    "UnreadableDocument",
    "UploadRefused",
    "clean_heading",
    "delete_stored_file",
    "detect_content_type",
    "extract_text",
    "index_document",
    "looks_like_a_heading",
    "safe_filename",
    "save_upload",
    "split_into_sections",
]
