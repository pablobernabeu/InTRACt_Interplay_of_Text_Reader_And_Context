"""Which variety of Portuguese the delivered pt-pt texts are written in, from markers that separate European from
Brazilian Portuguese. Counts only; no text is printed, no per-text value is kept, and nothing reads an outcome.

Run on 4 November 2026, at the PI's request, to settle plan decision (h) (pending_benchmarks.md, P85), and recorded in
Supplementary Section S7. Markers, each counted as whole-word matches over every text:
  - the progressive: European "estar a" + infinitive against Brazilian "estar" + gerund;
  - accents before m or n, where European writes é/ó and Brazilian ê/ô (género/gênero, económico/econômico);
  - enclitic pronouns joined by a hyphen (disse-lhe), far more frequent in European writing;
  - vocabulary pairs (autocarro/ônibus, comboio/trem, telemóvel/celular, pequeno-almoço/café da manhã,
    casa de banho/banheiro, frigorífico/geladeira, sumo/suco, gelado/sorvete, ecrã/tela, castanho/marrom).

Usage: python -I -X utf8 portuguese_variety.py [stories.csv.xz]   (default: ../data/pt-pt/stories.csv.xz)
"""
import csv
import lzma
import re
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(2**31 - 1)
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "pt-pt" / "stories.csv.xz"
ESTAR = r"(?:estou|estás|está|estamos|estão|estava|estavas|estávamos|estavam|esteve|estiveram|estar|estará|estarão)"
PATTERNS = {
    "progressive_ep_estar_a_inf": rf"\b{ESTAR}\s+a\s+\w+(?:ar|er|ir)\b",
    "progressive_bp_estar_gerund": rf"\b{ESTAR}\s+\w+(?:ando|endo|indo)\b",
    "accent_ep_e_o_acute_before_nasal": r"\b\w*[éó][mn]\w*\b",
    "accent_bp_e_o_circumflex_before_nasal": r"\b\w*[êô][mn]\w*\b",
    "enclitic_hyphen_ep": r"\b\w+-(?:me|te|se|lhe|lhes|nos|vos|o|a|os|as|lo|la|los|las)\b",
}
PAIRS = [("autocarro", "ônibus"), ("comboio", "trem"), ("telemóvel", "celular"), ("pequeno-almoço", "café da manhã"),
         ("casa de banho", "banheiro"), ("frigorífico", "geladeira"), ("sumo", "suco"), ("gelado", "sorvete"),
         ("ecrã", "tela"), ("castanho", "marrom")]
counts, texts = Counter(), 0
pats = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
pair_pats = [(re.compile(rf"\b{re.escape(a)}\b", re.I), re.compile(rf"\b{re.escape(b)}\b", re.I)) for a, b in PAIRS]
with lzma.open(SRC, "rt", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        text = row["text"]
        texts += 1
        for k, p in pats.items():
            counts[k] += len(p.findall(text))
        for (a, b), (pa, pb) in zip(PAIRS, pair_pats, strict=True):
            counts[f"ep:{a}"] += len(pa.findall(text))
            counts[f"bp:{b}"] += len(pb.findall(text))
print(f"texts {texts:,} ({SRC.parent.name})")
for k in PATTERNS:
    print(f"  {k:40s} {counts[k]:>10,}")
ep = sum(counts[f"ep:{a}"] for a, _ in PAIRS)
bp = sum(counts[f"bp:{b}"] for _, b in PAIRS)
for a, b in PAIRS:
    print(f"  {a + ' / ' + b:40s} {counts[f'ep:{a}']:>10,} / {counts[f'bp:{b}']:,}")
print(f"  vocabulary pairs, European / Brazilian   {ep:>10,} / {bp:,}")
