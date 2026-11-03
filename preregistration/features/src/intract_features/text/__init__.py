"""Text-layer rules that every stage shares.

normalise  the registered normalisation, applied once to each text at load time (S3)
words      the registered word function, the only one in the pipeline (Measures)
titles     the catalogue's title line (gap G1a) and S3's rule for page-initial titles (gap G1b)
keyed      registered keyed samples, ranked by the keyed hash of the story identifier

Standard library only, so that the unit tests run without the model stages' dependencies.
"""
