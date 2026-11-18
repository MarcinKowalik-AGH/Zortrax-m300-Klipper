# Marcin Kowalik <mkowalik@agh.edu.pl>
"""Compare archived source identities across the project contact-header addition."""
import hashlib


def source_bytes(path):
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    contact = b'Marcin Kowalik <mkowalik@agh.edu.pl>'
    for i, line in enumerate(lines[:3]):
        if line.rstrip() in (b'# ' + contact, b'// ' + contact, b'<!-- ' + contact + b' -->'):
            del lines[i]
            break
    return b''.join(lines)


def source_sha(path):
    return hashlib.sha256(source_bytes(path)).hexdigest()
