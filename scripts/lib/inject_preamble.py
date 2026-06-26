#!/usr/bin/env python3
"""inject_preamble.py SRC DST PREAMBLE_FILE

Copy a canonical agent .md to DST, inserting the plugin path-resolution preamble
immediately after the YAML frontmatter (between the 2nd `---` and the body).

Idempotent: if the preamble marker is already present, the file is copied verbatim
(the preamble is never double-injected). The injected shape is:

    ---
    <frontmatter>
    ---
    <blank>
    > **Plugin path resolution (workflow-shell).** ...
    > - ...
    > - ...
    > - ...
    <blank>
    <blank>
    <body>

This reproduces, byte-for-byte, the layout the plugin agents already ship with, so a
re-cut from canonical changes only genuine content (e.g. frontmatter `permissionMode`),
not preamble whitespace.
"""
import sys

MARKER = "> **Plugin path resolution (workflow-shell).**"


def main():
    src, dst, pre = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(src, encoding="utf-8").read()
    preamble = open(pre, encoding="utf-8").read().rstrip("\n")
    lines = text.split("\n")
    delim = [i for i, l in enumerate(lines) if l.strip() == "---"]

    if MARKER in text or len(delim) < 2:
        out = text
    else:
        fm_end = delim[1]
        head = "\n".join(lines[: fm_end + 1])  # through the closing ---
        body = lines[fm_end + 1:]
        while body and body[0].strip() == "":   # drop leading blank lines of the body
            body.pop(0)
        body_text = "\n".join(body)
        out = head + "\n\n" + preamble + "\n\n\n" + body_text

    import os
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(out)


if __name__ == "__main__":
    main()
