# Screening log guide

Reference for [screening_log.csv](screening_log.csv). 


| Column                              | Purpose and how to fill                                                                                                                      |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `record_id`                         | Sequentially set unique ID                                                                                                                   |
| `citation_key`                      | BibTeX key from your the Zotero library                                                                                                      |
| `search_input`                      | The exact search query / string                                                                                                              |
| `title`                             | Title of paper in title case                                                                                                                 |
| `authors`                           | Author list with complete last name and abbreviated first and middle names                                                                   |
| `year`                              | Publication year                                                                                                                             |
| `doi`                               | DOI or URL                                                                                                                                   |
| `abstract`                          | Paste the abstract                                                                                                                           |
| `keywords`                          | Paper keywords, if supplied.                                                                                                                 |
| `screener`                          | Initials of the person making the screening decision on this row                                                                             |
| `date`                              | Decision date (DD-MM-YYYY)                                                                                                                   |
| `decision`                          | `include`, `exclude`, or `uncertain`If `include`, fill out rest of the columns except the next one.If `exclude`, fill out the next column. |
| `exclusion_reason`                  | Short explanation of why `decision` is `exclude` (e.g. wrong population, wrong outcomes); blank if not excluded                              |
| `sample_size`                       | Main analytic *N*                                                                                                                            |
| `population_child`                  | `yes` if participants include child or adolescent readers; `no` if adults only                                                               |
| `population_age_range`              | Age range in sample                                                                                                                          |
| `using_digital_or_app`              | `yes` if reading is via app, e-book platform, or similar digital log; else `no`                                                              |
| `outcome_reading_time`              | `yes` if reading time is recorded as outcome + state the method; else `no`                                                                   |
| `outcome_comprehension`             | `yes` if comprehension questions, accuracy, or standardised comprehension is measured + state the method; else `no`                          |
| `predictors_text_features`          | `yes` if hand-crafted text indices (lexical, syntactic, coherence, etc.) are reported + state the method; else `no`                          |
| `predictors_neural_lm`              | `yes` if neural LM / embedding predictors of reading are reported + state the method; else `no`                                              |
| `moderator_age_or_development`      | `yes` if age or developmental stage is a predictor or moderator; else `no`                                                                   |
| `age_related_direction`             | `positive` or `negative`; state one line summary of result                                                                                   |
| `effect_size`                       | report effect size of age related effect; leave blank if none provided                                                                       |
| `moderator_narration_or_multimedia` | `yes` if read-aloud, narration, or comparable multimedia support is a factor; else `no`                                                      |
| `multilevel_or_hierarchical`        | `yes` if nested / clustered models or data (children within class, language, etc.); else `no`                                                |
| `multilingual_or_cross_lingual`     | `yes` if multiple languages or cross-linguistic comparison; else `no`                                                                        |
| `reviewer_conclusions`              | list the relevant conclusions from this paper + any other notes                                                                              |


