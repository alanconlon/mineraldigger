"""Turn organiser HTML into text without keeping scripts or styles."""

import html
import re


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|h1|h2|h3|h4|li|tr|div)>", "\n", text)
    text = re.sub(r"(?i)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    lines = []
    for line in text.splitlines():
        clean = re.sub(r"[ \t]+", " ", line).strip()
        if clean:
            lines.append(clean)
    return "\n".join(lines)


def html_to_lines(raw: str) -> list[str]:
    return html_to_text(raw).split("\n") if raw else []
