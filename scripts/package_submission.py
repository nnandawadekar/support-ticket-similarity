"""Build the TalentStudio submission ZIP from an explicit allowlist and check the upload rules.

Rules checked (Case Study Submission - Student Quick Guide): one ZIP under 50 MB; README.md at the top
level; design document as PDF/DOCX/PPTX of at most 20 pages with at most 6 embedded pictures; no
standalone image or legacy .doc/.ppt files. Generated assets (diagram exports, Postman files) and
authoring scripts stay in the repository so the reviewer's 15-file budget goes to source and tests.
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "support-ticket-similarity-submission.zip"

FILES = [
    "README.md",
    "SOLUTION_DESIGN.pdf",
    "SOLUTION_DESIGN.md",  # deliverable named in the brief; same content as the PDF
    # key source files, in the order listed in the README
    "ticket_similarity/service.py",
    "ticket_similarity/lexical.py",
    "ticket_similarity/text.py",
    "ticket_similarity/semantic.py",
    "ticket_similarity/server.py",
    "ticket_similarity/evaluate.py",
    "ticket_similarity/cli.py",
    "ticket_similarity/data.py",
    "ticket_similarity/__init__.py",
    "ticket_similarity/__main__.py",
    "tests/test_service.py",
    "tests/test_lexical.py",
    "tests/test_server.py",
    "tests/test_evaluate.py",
    "tests/test_hybrid.py",
    "tests/test_text.py",
    "tests/test_cli.py",
    "scripts/benchmark.py",
    # needed to install and run; small inputs, not generated output
    "pyproject.toml",
    "requirements-semantic.txt",
    "eval/queries.json",
    "starter_kit/data/tickets.json",
    "starter_kit/data/new_tickets_example.json",
]

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_DESIGN_PAGES = 20
MAX_DESIGN_PICTURES = 6
BLOCKED_SUFFIXES = {".png", ".svg", ".drawio", ".jpg", ".jpeg", ".gif", ".webp", ".doc", ".ppt", ".html"}


def check_design_pdf(path):
    data = path.read_bytes()
    if b"/Encrypt" in data:
        return ["design PDF is encrypted"]
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    pictures = len(re.findall(rb"/Subtype\s*/Image\b", data))
    problems = []
    if not 1 <= pages <= MAX_DESIGN_PAGES:
        problems.append(f"design PDF has {pages} pages (limit {MAX_DESIGN_PAGES})")
    if not 1 <= pictures <= MAX_DESIGN_PICTURES:
        problems.append(f"design PDF has {pictures} embedded pictures (expected 1-{MAX_DESIGN_PICTURES})")
    print(f"design PDF: {pages} pages, {pictures} embedded picture(s)")
    return problems


def main():
    problems = [f"missing: {name}" for name in FILES if not (ROOT / name).is_file()]
    problems += [f"unsupported file type: {name}" for name in FILES if Path(name).suffix.lower() in BLOCKED_SUFFIXES]
    if not problems:
        problems += check_design_pdf(ROOT / "SOLUTION_DESIGN.pdf")
    if problems:
        sys.exit("cannot package:\n  " + "\n  ".join(problems))

    OUTPUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, arcname=name)

    size = OUTPUT.stat().st_size
    if size >= MAX_ZIP_BYTES:
        OUTPUT.unlink()
        sys.exit(f"ZIP is {size / 1e6:.1f} MB; the limit is 50 MB")
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(FILES)} files, {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
