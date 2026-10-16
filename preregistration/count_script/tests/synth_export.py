"""Synthetic export generator shared by the test runners. No real data is used."""
import csv
import gzip
import random

HEADER = ['user_id', 'game_version', 'finished_reading_at', 'user_country', 'user_age_group',
          'story_title', 'story_id', 'story_location', 'story_hero', 'story_sidekick',
          'story_plot', 'story_theme', 'is_customized', 'is_speech_on', 'time_spent_reading',
          'read_language', 'user_reading_level', 'max_page_reached', 'total_page_available',
          'story_rating', 'minigame_trace_word_ts', 'minigame_arrange_tile_ts',
          'minigame_find_tile_ts', 'minigame_pair_tiles_ts', 'minigame_match_word_ts',
          'minigame_assemble_word_ts', 'minigame_fold_paper_ts',
          'minigame_arrange_illustration_ts', 'word_explorer_ts', 'inkmagination_ts']

LANGS = ["English", "German", "Polish", "Italian", "Spanish", "Korean", "Portuguese",
         "Dutch", "French", "Greek"]
AGES = ["Age 3-4", "Age 5-6", "Age 7-8", "Age 9+"]
LEVELS = ["Age 3-5", "Age 5-7", "Age 7+"]
COUNTRIES = ["Germany", "Italy", "Poland", "Spain", "France", "Korea", "Greece", "Brazil"]


def synth(n_accounts, n_texts, seed, title_trouble=False):
    """Rows as dicts of strings, plus the ground truth."""
    rng = random.Random(seed)
    texts = []
    for t in range(n_texts):
        crafted = rng.random() < 0.6
        title = "Crafted story" if crafted else "classic story"
        if title_trouble and crafted:
            title = rng.choice(['The fox, the owl and "Pip"', 'Line one\nline two',
                                'A "quoted" title', 'Commas, commas, commas'])
        texts.append({"sid": str(100000 + t), "title": title,
                      "pages": str(rng.choice([6, 7, 10, 11, 17]))})
    rows, truth_accounts = [], set()
    for a in range(n_accounts):
        uid = rng.randrange(10**17, 9 * 10**18)
        truth_accounts.add(uid)
        age, lang, ctry = rng.choice(AGES), rng.choice(LANGS), rng.choice(COUNTRIES)
        for _ in range(rng.choice([1, 1, 1, 2, 3, 5])):
            tx = rng.choice(texts)
            day = f"2026-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}"
            when = f"{day} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00"
            rows.append({
                "user_id": uid, "game_version": rng.choice(["6.2.0", "6.5.1", "6.7.2"]),
                "finished_reading_at": when, "user_country": ctry, "user_age_group": age,
                "story_title": tx["title"], "story_id": tx["sid"],
                "story_location": "forest", "story_hero": "fox", "story_sidekick": "owl",
                "story_plot": "lost", "story_theme": "friendship",
                "is_customized": "1", "is_speech_on": rng.choice(["1", "1", "1", "0"]),
                "time_spent_reading": str(rng.randint(20, 900)),
                "read_language": lang, "user_reading_level": rng.choice(LEVELS),
                "max_page_reached": tx["pages"], "total_page_available": tx["pages"],
                "story_rating": rng.choice(["", "", "Just Right", "Easy", "Difficult"]),
            })
    for r in rows:
        for c in HEADER:
            r.setdefault(c, "0")
    truth = {"sessions": len(rows), "accounts": len(truth_accounts),
             "texts": len({r["story_id"] for r in rows})}
    return rows, truth


def write_csv(path, rows, header=HEADER, with_header=True, uid_format=int, gz=False):
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8", newline="")) if gz else \
             (lambda p: open(p, "w", encoding="utf-8", newline=""))
    with opener(path) as fh:
        w = csv.writer(fh)
        if with_header:
            w.writerow(header)
        for r in rows:
            vals = []
            for c in header:
                v = r[c]
                if c == "user_id":
                    v = uid_format(v)
                vals.append(str(v))
            w.writerow(vals)
