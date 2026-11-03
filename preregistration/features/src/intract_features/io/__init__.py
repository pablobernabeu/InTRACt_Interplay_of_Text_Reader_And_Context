"""Reading the published story tables.

catalogue  the published story tables (story_texts/data/<lang>/stories.csv.xz) and any table in
           their schema, such as the public stand-in

The module applies no lock; stages/documents.py applies the catalogue lock before anything else is
computed on a text. The parse artefacts' CoNLL-U is written and read by intract_features.parse, the
one home of that format.
"""
