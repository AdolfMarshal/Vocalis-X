# structure_parser.py

import re

SECTION_REGEX = r"\[(verse|chorus|bridge|intro|outro)[^\]]*\]"

def parse_lyrics_structure(lyrics):

    sections = []

    lines = lyrics.splitlines()

    current = {"type": "verse", "lines": []}

    for line in lines:

        match = re.match(SECTION_REGEX, line.lower())

        if match:
            sections.append(current)
            current = {"type": match.group(1), "lines": []}
        else:
            current["lines"].append(line)

    sections.append(current)

    return sections