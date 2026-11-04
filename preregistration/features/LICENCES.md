# Licences

This file lists the licence of everything the feature pipeline uses: its own code, the models and the code it runs,
and the resources and corpora it reads. Each entry gives the source of the licence; for a pinned model or resource
that source is also recorded in `config/models.lock.json` or `config/resources.lock.json` (`licence`,
`licence_source`), read on 3 November 2026. Nothing listed here is redistributed by this repository unless the
entry says so: the jobs fetch models and resources at their pinned revisions, and outputs computed on them stay on
ARC (`DESIGN.md`, Tests).

## This package

The code (`src/`, `standin/`, `jobs/`, `envs/build_envs.sh`, `tests/`) and the configuration it reads are
under the repository's MIT licence, copyright (c) 2026 University of Oxford (`../../LICENSE`). The documentation is
under CC BY-NC 4.0, copyright (c) 2026 the InTRACt authors, as `../../LICENSE-content.md` sets out. Most of the code
is promoted from the project's own pre-submission benchmarks, under the same terms.

## Models

| Model (lock key) | Licence | Used by | Licence source |
|---|---|---|---|
| `segment-any-text/sat-12l-sm` | MIT | `sat` | Hugging Face model card metadata at the pinned revision |
| `FacebookAI/xlm-roberta-base` (tokeniser only) | MIT | `sat` | Hugging Face model card metadata |
| Stanza 1.15.0 English models, `stanfordnlp/stanza-en` at v1.15.0 (`stanza-1.15.0`) | Apache-2.0 | `parse_stanza` | Hugging Face model card metadata of `stanfordnlp/stanza-en` |
| UDPipe 2.17 models, `udpipe2-ud-2.17-251125`, LINDAT hdl 11234/1-6046 (`udpipe-2.17`) | CC BY-NC-SA 4.0 | `parse_udpipe` | LICENSE and README.md of the 2.17 model archive |
| `google-bert/bert-base-multilingual-uncased` (UDPipe 2's word embeddings) | Apache-2.0 | `parse_udpipe` | Hugging Face model card metadata |
| `goldfish-models/eng_latn_1000mb` and `goldfish-models/eng_latn_100mb` | Apache-2.0 | `surprisal_goldfish` | Hugging Face model card metadata |
| `facebook/xglm-4.5B` | MIT | `surprisal_xglm` | Hugging Face model card metadata |
| `intfloat/multilingual-e5-large-instruct` | MIT | `encode_e5` | Hugging Face model card metadata |
| `BAAI/bge-m3` | MIT | `encode_bgem3` | Hugging Face model card metadata |
| `ufal/corpipe26-onestage-corefud1.4-xl-260702` and its fallback `ufal/corpipe26-onestage-corefud1.4-large-260702`, LINDAT hdl 11234/1-6205 | CC BY-NC-SA 4.0 | `coref_corpipe` | Hugging Face model card metadata and the LINDAT deposit (dc.rights) |
| `google/umt5-xl`, `google/mt5-large` and `google/mt5-xl` (encoder configurations and tokenisers) | Apache-2.0 | `coref_corpipe`, `qe_metricx` | Hugging Face model card metadata |
| `google/metricx-24-hybrid-xl-v2p6` (and its optional safetensors copy, `google/metricx-24-hybrid-xl-v2p6@safetensors`) | Apache-2.0 | `qe_metricx` | Hugging Face model card metadata |
| `google-bert/bert-base-multilingual-cased` (the word aligner, for the translations) | Apache-2.0 | `reference/align.py` | Hugging Face model card metadata |

CC BY-NC-SA 4.0, the licence of the UDPipe 2.17 and CorPipe 26 models, allows non-commercial use only and requires
adaptations to be shared under the same licence; InTRACt uses them in non-commercial research.

## Code run from a checkout or as a separate program

| Software | Licence | How the pipeline uses it | Licence source |
|---|---|---|---|
| UDPipe 2, `ufal/udpipe` at 223da86 (`udpipe-2.17`) | MPL-2.0 | `udpipe2_server.py` runs unmodified in the `udpipe` environment, started by `parse/udpipe_server.py` | LICENSE of the checkout |
| CorPipe 26, `ufal/crac2026-corpipe` at ec853c3b | MPL-2.0 | `corpipe26_onestage.py` runs unmodified in the `corpipe` environment, called by `reference/corpipe_run.py` | GitHub licence detection and LICENSE at the commit |
| MetricX-24, `google-research/metricx` at fc4978eb | Apache-2.0 | run in the `metricx` environment only, to validate the port in `reference/metricx_qe.py` | GitHub licence detection and LICENSE at the commit |
| eSpeak NG 1.52.0, <https://github.com/espeak-ng/espeak-ng> at 4870adfa (`espeak-ng-1.52.0`) | GPL-3.0 | built from its tag by `jobs/arc/j0_build.sbatch` and called as an external program through phonemizer; no part of it is linked into or copied into this package | GitHub licence detection |
| phonemizer 3.4.0 | GPL-3.0 or later | run as a separate program (`python -m phonemizer.main`) by `features/duration.py`, never imported, so no GPL code becomes part of this package | the package's metadata (`License :: GNU General Public License v3 or later`) |

## Python libraries

Every Python package in `envs/<env>.lock` keeps its own licence, recorded in its distribution's metadata. Those the
stages import directly, as their installed metadata gives them: wtpsplit 2.2.2 (MIT), Stanza 1.15.0 (Apache 2.0),
transformers (Apache 2.0), tokenizers and safetensors (Apache Software License), sentencepiece (Apache-2.0), protobuf
(3-Clause BSD), NumPy (BSD-3-Clause, with bundled components under 0BSD, MIT, Zlib and CC0-1.0), pyarrow
(Apache-2.0), wordfreq 3.1.1 (Apache-2.0 for its code), minnt 1.1.1 (MPL-2.0) and torch (Apache-2.0 and BSD-style
licences for PyTorch and its bundled components). huggingface_hub (Apache-2.0) is imported by
`jobs/arc/staging.py` and the CorPipe script, and OpenCC 1.4.2 (Apache-2.0) is needed only for Traditional
Chinese. udapi 0.5.2, which the CorPipe script imports in the `corpipe` environment, is GPL-3.0 or later. In the
`udpipe` environment, TensorFlow 2.21.0 and tf-keras 2.21.0 are Apache-2.0 and `ufal.udpipe` 1.4.0.1 is MPL-2.0,
while `ufal.chu_liu_edmonds` 1.0.3 is GPLv3; it runs inside the UDPipe 2 server, a separate process that
`parse/udpipe_server.py` starts, so no GPL code becomes part of this package (PyPI metadata, checked on
3 November 2026).

## Resources and corpora

| Resource (lock key) | Licence | Used by | Licence source |
|---|---|---|---|
| SimpleStories, `SimpleStories/SimpleStories` at e63b8adc (`simplestories`) | MIT | the stand-in (`standin/`) | the dataset card at the pinned revision ("license: mit"). Neither the dataset nor the generation repository holds a licence file or names a copyright holder, so `standin/build_standin.py` writes `NOTICE-SimpleStories.txt`, with the MIT notice and the copyright given to the SimpleStories authors (Finke et al., 2025), beside every stand-in table |
| MEmoLon MTL_grouped v1.0, Zenodo record 3756607 (`memolon_mtl_grouped_en`) | CC BY 4.0 | `features_discourse` (valence and arousal) | Zenodo record metadata |
| CLDR 47's Serbian-Latin-BGN transform, `config/cldr/cldr47_Serbian-Latin-BGN.xml` (unicode-org/cldr, tag release-47, commit 2ef784e3; SHA-256 b415bc12) | Unicode License v3 | `text/sr_translit.py`, which applies its rules and is tested against this copy | the file's own header, which points to the Unicode terms of use, and the LICENSE of the CLDR repository at that tag | CC BY-SA 4.0 for the data, Apache-2.0 for the code | `features_gramlex` (interim frequency list, P48) | wordfreq 3.1.1's package metadata, which also notes data sources under similar terms |
| wordfreq 3.1.1's English list (`wordfreq-3.1.1/large_en.msgpack.gz`) | CC BY-SA 4.0 for the data, Apache-2.0 for the code | `features_gramlex` (interim frequency list, P48) | wordfreq 3.1.1's package metadata, which also notes data sources under similar terms |
| FLORES-200 (`flores200`) | CC BY-SA 4.0 | the multilingual stages, after the English dry run | README.md of facebookresearch/flores |
| The translated benchmark's English-German pairs (`translated_benchmark_mt_de`) | derived from TinyStories (CDLA-Sharing-1.0) by MADLAD-400-3B-MT (Apache-2.0) and NLLB-200-3.3B (CC BY-NC 4.0) | timing `qe_metricx` in the dry run; read in place on ARC | `config/resources.lock.json` |
| Unicode CLDR 47 quotation delimiters, `cldr-misc-full` 47.0.0, `main/en/delimiters.json` | Unicode License v3 (Unicode-3.0) | the English quotation pairs in `config/languages.toml` (dialogue detector) | recorded with the file's SHA-256 in `config/stages/features_discourse.toml` [dialogue] |
| Universal Dependencies treebanks and earlier benchmark parses | each treebank's own licence | the tests marked `models` (the hand-annotated UD 2.18 files on ARC, local copies elsewhere); not distributed here | each treebank's LICENSE |
| The *Let's Story* story texts | CC BY-NC 4.0, copyright Ferrero International and Gameloft | not read before in-principle acceptance: the catalogue lock refuses them | `../../LICENSE-content.md` |

## Third-party code copied or adapted here

- `tests/unit/test_segment.py` copies `indices_to_sentences` and the newline step of `SaT.split` from wtpsplit
  2.2.2 to test the promoted code against them, and `segment/sat.py` reimplements `SaT.split` on character offsets.
  wtpsplit's licence, which applies to the copied lines:

  ```
  MIT License

  Copyright (c) 2024 Benjamin Minixhofer, Markus Frohmann, Igor Sterner

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
  ```

- `reference/metricx_qe.py` ports the forward pass of MetricX-24's `metricx24/models.py` and the tokeniser that
  `metricx24/predict.py` builds under transformers 4.30.2 (`convert_slow_tokenizer.py`'s SpmConverter and
  T5Converter), both under the Apache License 2.0 (<https://www.apache.org/licenses/LICENSE-2.0>). The module's
  docstring names the files and the changes made.
- The CorPipe and UDPipe 2 code is run unmodified from its checkouts and is not copied into this package.
