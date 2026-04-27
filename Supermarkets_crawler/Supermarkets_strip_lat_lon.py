import re
from pathlib import Path

FILE_PATH = Path(__file__).resolve().parent.parent / "Supermarkets.txt"

text = FILE_PATH.read_text(encoding="utf-8")
cleaned = re.sub(r",\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*$", "", text, flags=re.MULTILINE)
FILE_PATH.write_text(cleaned, encoding="utf-8", newline="\n")
print("Done: Supermarkets.txt")
