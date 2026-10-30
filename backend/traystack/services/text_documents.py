"""Strict UTF-8 text and non-executing HTML extraction; no remote resource access."""

from html.parser import HTMLParser

TEXT_TYPES = {".txt": "text/plain", ".htm": "text/html", ".html": "text/html"}
TEXT_DOCUMENT_VERSION = "utf8-html-text-v1"


def decode_text(data: bytes) -> str:
    text = data.decode("utf-8-sig", errors="strict")
    if any(ord(char) < 32 and char not in "\t\r\n\f" for char in text):
        raise ValueError("Text documents cannot contain binary control characters")
    if not text.strip():
        raise ValueError("Text documents must contain non-whitespace text")
    return text


class TextHTMLParser(HTMLParser):
    # Text reading order is approximate; all HTML outputs require manual review.
    suppressed = {"head", "script", "style", "template", "noscript", "iframe", "object", "svg"}
    blocks = {"p", "div", "br", "hr", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipped: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.suppressed:
            self.skipped.append(tag)
        elif not self.skipped and tag in self.blocks:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skipped:
            if tag == self.skipped[-1]:
                self.skipped.pop()
        elif tag in self.blocks:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if not self.skipped and tag in self.blocks:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)


def html_text(text: str) -> str:
    parser = TextHTMLParser()
    parser.feed(text)
    parser.close()
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
