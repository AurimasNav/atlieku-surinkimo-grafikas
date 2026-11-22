"""The text of a Word 97-2003 document (.doc, Word's old binary format), in pure Python.

A .doc is a compound file (OLE2, the container of .xls too), read here with xlrd's reader of
compound files, which the pipeline already has for Skuodo r.'s .xls. Its "WordDocument" stream
starts with the File Information Block (FIB), which says which table stream ("0Table" or
"1Table") holds the piece table (Clx); the piece table says where each run of the text is in
the WordDocument stream, and whether it is stored as 8-bit Windows-1252 or as UTF-16 (Word's
binary file format, [MS-DOC] 2.5 and 2.9). The main document is the first `ccpText`
characters; footnotes, headers and text boxes follow it and aren't returned.

No Word, LibreOffice, antiword or catdoc: the build runs on GitHub's runners and on Windows,
and these would have to be installed on both. A document that isn't a .doc of Word 97 or later,
or is encrypted, raises ValueError.
"""

from __future__ import annotations

import io
import struct

from xlrd.compdoc import CompDoc, CompDocError

_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # a compound file
_WORD = 0xA5EC  # FibBase.wIdent of a Word document
_ENCRYPTED = 0x0100  # FibBase.fEncrypted
_TABLE_1 = 0x0200  # FibBase.fWhichTblStm: the piece table is in "1Table"
_COMPRESSED = 0x40000000  # FcCompressed.fCompressed: 8-bit characters
_CLX_PAIR = 33  # fcClx/lcbClx is the 34th pair of FibRgFcLcb97
_CCP_TEXT = 3  # ccpText is the 4th value of FibRgLw97
# Characters of the text that aren't text: pictures, drawn objects, footnote and comment
# marks, the optional hyphen. A line break or a page break ends a line as a paragraph does.
_DROP = dict.fromkeys(map(ord, "\x01\x02\x03\x04\x05\x08\x1f"))
_LINES = {ord("\x0b"): "\r", ord("\x0c"): "\r", ord("\x1e"): "-"}


def is_document(content: bytes) -> bool:
    """Whether `content` is a compound file (a .doc, but also a .xls)."""
    return content[:8] == _SIGNATURE


def text(content: bytes) -> str:
    """The main document's text: paragraphs end with "\\r", and in a table every cell and
    every row ends with "\\x07". Fields keep their result, not their code ("PAGE")."""
    if not is_document(content):
        raise ValueError("not a Word 97-2003 document")
    try:
        doc = CompDoc(content, logfile=io.StringIO())
        word = doc.get_named_stream("WordDocument")
        if word is None or len(word) < 34:
            raise ValueError("not a Word document: no WordDocument stream")
        ident, flags = struct.unpack_from("<H8xH", word, 0)
        if ident != _WORD:
            raise ValueError(f"not a Word document (wIdent {ident:#x})")
        if flags & _ENCRYPTED:
            raise ValueError("an encrypted Word document")
        table = doc.get_named_stream("1Table" if flags & _TABLE_1 else "0Table")
    except (CompDocError, IndexError, AssertionError, struct.error) as error:
        # xlrd's reader checks a file's sectors with asserts and indexes, as it reads them
        raise ValueError(f"a damaged Word document: {error!r}") from error
    if table is None:
        raise ValueError("a Word document without its table stream")
    try:
        ccp_text, (fc_clx, lcb_clx) = _fib(word)
        pieces = _pieces(table[fc_clx : fc_clx + lcb_clx])
        chars: list[str] = []
        for start, end, fc in pieces:
            count = end - start
            if fc & _COMPRESSED:
                offset = (fc & ~_COMPRESSED) // 2
                chars.append(_slice(word, offset, count).decode("cp1252"))
            else:
                chars.append(_slice(word, fc, 2 * count).decode("utf-16-le"))
    except (struct.error, UnicodeDecodeError) as error:
        raise ValueError(f"a damaged Word document: {error}") from error
    main = "".join(chars)[:ccp_text]
    return _without_field_codes(main).translate(_DROP).translate(_LINES)


def _fib(word: bytes) -> tuple[int, tuple[int, int]]:
    """ccpText and the place of the Clx in the table stream, from the FIB: FibBase (32 bytes),
    then counted arrays of 16-bit, 32-bit and (fc, lcb) values."""
    pos = 32
    (csw,) = struct.unpack_from("<H", word, pos)
    pos += 2 + 2 * csw
    (cslw,) = struct.unpack_from("<H", word, pos)
    lw = struct.unpack_from(f"<{cslw}i", word, pos + 2)
    pos += 2 + 4 * cslw
    (pairs,) = struct.unpack_from("<H", word, pos)
    if cslw <= _CCP_TEXT or pairs <= _CLX_PAIR:
        raise ValueError("a Word document older than Word 97")
    fc_lcb = struct.unpack_from(f"<{2 * pairs}I", word, pos + 2)
    return lw[_CCP_TEXT], (fc_lcb[2 * _CLX_PAIR], fc_lcb[2 * _CLX_PAIR + 1])


def _pieces(clx: bytes) -> list[tuple[int, int, int]]:
    """(first character, end, fc) of each piece of the text: the Clx is property lists
    (type 1) and then the piece table (type 2), CPs followed by 8-byte piece descriptors."""
    pos = 0
    while pos < len(clx) and clx[pos] == 1:
        (size,) = struct.unpack_from("<h", clx, pos + 1)
        pos += 3 + size
    if pos >= len(clx) or clx[pos] != 2:
        raise ValueError("a Word document without a piece table")
    (size,) = struct.unpack_from("<I", clx, pos + 1)
    plc = clx[pos + 5 : pos + 5 + size]
    count, rest = divmod(len(plc) - 4, 12)
    if rest or count < 1 or len(plc) != size:
        raise ValueError("a Word document with a damaged piece table")
    cps = struct.unpack_from(f"<{count + 1}I", plc, 0)
    fcs = [struct.unpack_from("<I", plc, 4 * (count + 1) + 8 * i + 2)[0] for i in range(count)]
    if any(b < a for a, b in zip(cps, cps[1:], strict=False)):
        raise ValueError("a Word document with a damaged piece table")
    return [(cps[i], cps[i + 1], fcs[i]) for i in range(count)]


def _slice(data: bytes, start: int, size: int) -> bytes:
    if start + size > len(data):
        raise ValueError("a Word document whose text runs past its stream")
    return data[start : start + size]


def _without_field_codes(text: str) -> str:
    """A field is "\\x13 code \\x14 result \\x15" (or without a result): its result is kept.
    Fields can be nested in a code or a result."""
    result: list[str] = []
    in_code: list[bool] = []  # per open field, whether its code is being read
    for ch in text:
        if ch == "\x13":
            in_code.append(True)
        elif ch == "\x14" and in_code:
            in_code[-1] = False
        elif ch == "\x15" and in_code:
            in_code.pop()
        elif not any(in_code):
            result.append(ch)
    return "".join(result)
