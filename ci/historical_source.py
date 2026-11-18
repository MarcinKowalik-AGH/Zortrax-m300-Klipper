# Marcin Kowalik <mkowalik@agh.edu.pl>
# historical_source.py - Odtwarza bajty starszych źródeł do porównania, pomijając nagłówek autora i opis pliku.
"""Compare archived source identities across the project contact-header addition."""
import hashlib


def source_bytes(path):
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    contact = b'Marcin Kowalik <mkowalik@agh.edu.pl>'
    filename = path.name.encode() + b' - '
    for i, line in enumerate(lines[:4]):
        for prefix, suffix in ((b'# ', b''), (b'// ', b''), (b'<!-- ', b' -->')):
            author = prefix + contact
            if line.rstrip().startswith(author + b' | ' + filename):
                del lines[i]
                return b''.join(lines)
            if line.rstrip() == author + suffix:
                del lines[i]
                if i < len(lines) and lines[i].startswith(prefix + filename):
                    del lines[i]
                return b''.join(lines)
    return b''.join(lines)


def source_sha(path):
    return hashlib.sha256(source_bytes(path)).hexdigest()
