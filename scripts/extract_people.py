#!/usr/bin/env python3
"""
Simple people extractor.

Scans E:/Dropbox for PDFs, images, txt, docx and attempts to extract text.
Finds ID/passport/NRIC-like patterns and groups files by parent folder name.
Writes per-person markdown into output/personal_profiles.
"""
import os
import re
from pathlib import Path
from collections import defaultdict

ROOTS = [r"E:/Dropbox"]
OUT_DIR = Path("output/personal_profiles")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# basic regex
chinese_id_re = re.compile(r"\b(\d{17}[0-9Xx])\b")
passport_re = re.compile(r"\b([A-Z]{1}[0-9]{7,9})\b")
sg_nric_re = re.compile(r"\b[STFG]\d{7}[A-Z]\b", re.IGNORECASE)
date_re = re.compile(r"(\d{1,2}[-/ ]\d{1,2}[-/ ]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2} \w+ \d{4})")

try:
    from pdfminer.high_level import extract_text
except Exception:
    extract_text = None

try:
    from PIL import Image
    import pytesseract
    has_ocr = True
except Exception:
    has_ocr = False

def extract_text_from_file(path: Path):
    txt = ''
    try:
        ext = path.suffix.lower()
        if ext == '.pdf' and extract_text:
            txt = extract_text(str(path))
        elif ext in ('.txt', '.md'):
            txt = path.read_text(encoding='utf-8', errors='ignore')
        elif ext in ('.jpg', '.jpeg', '.png', '.webp') and has_ocr:
            try:
                img = Image.open(str(path))
                txt = pytesseract.image_to_string(img, lang='eng+chi_sim')
            except Exception:
                txt = ''
        elif ext == '.docx':
            try:
                import docx
                doc = docx.Document(str(path))
                txt = '\n'.join(p.text for p in doc.paragraphs)
            except Exception:
                txt = ''
    except Exception:
        txt = ''
    return txt or ''

def find_entities(text):
    res = {}
    if not text:
        return res
    m = chinese_id_re.search(text)
    if m:
        res['chinese_id'] = m.group(1)
    passports = passport_re.findall(text)
    if passports:
        res['passports'] = list(dict.fromkeys(passports))
    nrics = sg_nric_re.findall(text)
    if nrics:
        res['nric'] = list(dict.fromkeys(nrics))[0]
    dates = date_re.findall(text)
    if dates:
        res['dates'] = dates[:3]
    return res

people = defaultdict(lambda: {'files': [], 'texts': [], 'entities': {}})

exts = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.txt', '.docx', '.md')
for root in ROOTS:
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(exts):
                p = Path(dirpath) / fn
                txt = extract_text_from_file(p)
                entities = find_entities(txt)
                # heuristics for person key
                parent = p.parent.name
                key = parent if parent else 'unknown'
                # if filename contains Chinese chars, use them
                stem = p.stem
                if re.search(r'[\u4e00-\u9fff]', stem):
                    cn = ''.join(re.findall(r'[\u4e00-\u9fff]+', stem)[:2])
                    if cn:
                        key = cn
                people[key]['files'].append(str(p))
                if txt:
                    people[key]['texts'].append(txt)
                # merge entities
                for k, v in entities.items():
                    if k not in people[key]['entities']:
                        people[key]['entities'][k] = v
                    else:
                        existing = people[key]['entities'][k]
                        if isinstance(existing, list) and isinstance(v, list):
                            for it in v:
                                if it not in existing:
                                    existing.append(it)
                        elif existing != v:
                            people[key]['entities'][k] = v

try:
    from slugify import slugify
except Exception:
    def slugify(x):
        return re.sub(r'[^0-9a-zA-Z]+', '_', x).strip('_').lower()

for name, info in people.items():
    slug = slugify(name) if name != 'unknown' else 'unknown_person'
    outp = OUT_DIR / f"{slug}.md"
    with outp.open('w', encoding='utf-8') as f:
        f.write(f"# 人物档案 — {name}\n\n")
        f.write("## 关联文件\n\n")
        for fn in info['files']:
            f.write(f"- {fn}\n")
        f.write('\n')
        f.write("## 抽取到的字段\n\n")
        if info['entities']:
            for k, v in info['entities'].items():
                f.write(f"- **{k}**: {v}\n")
        else:
            f.write("- （未提取到结构化字段）\n")
        f.write('\n')
        f.write("## 原文样本（节选）\n\n")
        for t in info['texts'][:3]:
            s = t.strip()[:2000]
            f.write("```")
            f.write(s)
            f.write("```\n\n")

print('WROTE', len(people), 'person files to', OUT_DIR)
