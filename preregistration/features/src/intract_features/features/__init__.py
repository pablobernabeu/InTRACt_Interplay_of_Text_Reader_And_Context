"""Library code for the registered text features; stage modules call it and hold no rules of their own.

The modules of the features_gramlex stage (constants in config/stages/features_gramlex.toml):

- grammatical: the counting rules on a dependency parse (promoted from gfeat.py), a reader of external CoNLL-U
  (UD gold, earlier benchmark parses) in gfeat's shape, token alignment and mean sentence length. The pipeline's
  own parse artefacts are read with intract_features.parse.read_conllu.
- parsemean: the registered mean of the Stanza and UDPipe 2 values, with S3's long-unit rule.
- lexical: lookup normalisation, the frequency resource (interim wordfreq 3.1.1 until the OpenSubtitles 2024
  lists exist, P48), names, word length and lexical density.
- diversity: MATTR and MTLD.
- pages: word count, page count, pages per hundred words and page-break alignment.

The modules of the features_discourse stage (constants in config/stages/features_discourse.toml, which also reads
features_gramlex.toml [lexical.normalisation] and [lexical.casing] for its lookups):

- overlap: referential overlap and anaphoric continuation between adjacent sentences.
- connectives: the causal and contrastive anchors and their densities.
- dialogue: the registered dialogue detector and the dialogue share (also the G6 detector route of grammatical).
- names: the type rule for names, the name inventory and the name covariates.
- affect: MEmoLon valence and arousal.
- duration: spoken duration from eSpeak NG phones, with phonemizer run as a separate program.

The modules of the language-model and encoder stages:

- surprisal: corrected word surprisal (surprisal_goldfish and surprisal_xglm), the pinned-weight loaders and the
  pickle-to-safetensors conversion the ARC build uses.
- similarity: adjacent-sentence similarity (encode_e5 and encode_bgem3).
"""
