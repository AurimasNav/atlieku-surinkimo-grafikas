"""The text of a Word 97-2003 document (worddoc.py), from Panevėžio r.'s mixed waste schedule."""

import struct

import pytest
from test_parsers import fixture

from schedule_pipeline import worddoc

DOC = fixture("pratc/panevezio-r-mka.doc")
FIB = 512  # the WordDocument stream starts in the file's first sector


def test_the_main_text_of_a_document():
    text = worddoc.text(DOC)
    paragraphs = [p.strip() for p in text.split("\r") if p.strip()]
    assert paragraphs[0] == "Panevėžio rajono gyventojų buitinių atliekų išvežimo grafikai 2026 m."
    # Lithuanian letters are stored as UTF-16 pieces, the rest as Windows-1252.
    assert "1. Geležių, Karsakiškio, Sodelių" in text
    assert "UAB „Švaros komanda“" in text
    # A table: every cell and row ends with \x07.
    assert text.count("\x07") == 41
    assert "Gruodis                   10d.\x072. Paliūniškio" in text
    # No headers or footers after the main text.
    assert text.rstrip().endswith("75772\xa0.")


def test_field_codes_are_left_out_and_their_results_kept():
    assert worddoc._without_field_codes("p. \x13 PAGE \x143\x15 iš 5") == "p. 3 iš 5"
    nested = "a\x13 IF \x13 PAGE \x141\x15 = 1 \x14b\x13 X \x14c\x15\x15d"
    assert worddoc._without_field_codes(nested) == "abcd"


def test_what_is_not_a_word_document_is_refused():
    with pytest.raises(ValueError, match="not a Word 97-2003 document"):
        worddoc.text(b"PK\x03\x04 a .docx is a zip")
    assert worddoc.is_document(DOC)
    assert not worddoc.is_document(b"{\\rtf1 ...")


def test_an_encrypted_document_is_refused():
    (flags,) = struct.unpack_from("<H", DOC, FIB + 10)
    content = bytearray(DOC)
    struct.pack_into("<H", content, FIB + 10, flags | 0x0100)
    with pytest.raises(ValueError, match="encrypted"):
        worddoc.text(bytes(content))


def test_a_damaged_document_fails_loudly():
    content = bytearray(DOC)
    struct.pack_into("<H", content, FIB, 0x1234)  # not Word's wIdent
    with pytest.raises(ValueError, match="not a Word document"):
        worddoc.text(bytes(content))
    with pytest.raises(ValueError):
        worddoc.text(DOC[:4096])  # cut short
