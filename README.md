# InTRACt: Interplay of Text, Reader And Context in children's digital reading comprehension

*Work in progress. This repository contains the preregistration of a study of children's reading in a storytelling app, the code behind every number the preregistration reports, and a link to the ongoing literature review.*

---

## About the project

How does the language of a story relate to how quickly a child reads it? And does that relation change with the child's age, or when the app reads the story aloud?

InTRACt is a preregistered study of the behavioural logs of children aged 7 and older who read AI-generated stories in *Let's Story*, a feature of the *Applaydu* app developed by Gameloft and Ferrero International. Children use it in any of 19 languages. The study combines computational measures of each story's language with Bayesian models of reading time, to test how lexical difficulty, grammatical load and referential continuity relate to children's reading pace outside the laboratory.

The project is hosted at the **[Department of Education, University of Oxford](https://www.education.ox.ac.uk/)**, and is embedded within the **[Learning in Families through Technology (LIFT)](https://www.education.ox.ac.uk/project/lift-learning-in-families-through-technology/)** project, which investigates how digital technologies shape learning within families. It is funded by **Ferrero International** (Kinder) and the **John Fell Fund** (University of Oxford). Neither funder has a role in the design, analysis, interpretation or decision to publish.

---

## Background

Reading comprehension depends on both the reader and the text. Laboratory research has established that measurable features of written text predict how long readers take and how much they understand. At the word level, less frequent and more abstract words slow readers down and are harder to retain. At the sentence level, longer and more structurally complex sentences place greater demands on working memory. Across a whole passage, texts that state the links between their ideas explicitly are generally easier to follow than texts that leave more to inference.

These effects are well established in adults, but children's reading differs. Younger readers have smaller vocabularies, less automatised decoding and more limited working memory, and all three change considerably across the primary-school years. At the same time, AI-generated text and reading apps now record children's naturalistic reading at a scale that laboratory studies cannot match. InTRACt brings these two traditions together.

---

## Conceptual framework

The diagram below is the framework the project started from. Reader and context variables (children's linguistic resources, sociocultural context and developmental status) and text features (lexical, syntactic, discourse and affective properties) jointly predict comprehension outcomes, with children's longitudinal progression as a cross-cutting temporal dimension. The preregistration registers a narrower model, drawn as its nomological net and generated from `preregistration/theory/intract.theory.yaml`. The logs carry no measure of an individual child's vocabulary, language background or comprehension.

![Conceptual framework of the study showing reader and context variables (linguistic resources, sociocultural context, developmental status) and text features (lexical-distributional, syntactic and discourse, affective properties) jointly predicting comprehension outcomes (processing efficiency, perceived difficulty, situation model construction), with longitudinal progression as a cross-cutting temporal dimension.](mindmap/mindmap.png)

---

## Hypotheses

The preregistration registers six confirmatory hypotheses. Hypothesis 1 predicts that, across distinct texts and within reading level and language, lexical difficulty and grammatical load will each be associated with longer reading time per word, and referential continuity with shorter reading time. Hypotheses 2 and 3 test whether the grammatical-load and referential-continuity associations differ between the platform's two age bands, 7 to 8 and 9 or older. Both are registered as two-sided tests, because rival developmental accounts predict opposite signs.

Hypothesis 4 predicts that when the app narrates the story, the lexical association will be proportionally weaker than the continuity association. Hypothesis 5 predicts that the same three text properties will be associated with the child's own post-reading difficulty rating in the same directions as in Hypothesis 1. Hypothesis 6 predicts that, within a child, more accumulated in-app reading will be followed by faster reading. Hypotheses about comprehension are registered as contingent and will be tested only if the data prove to contain comprehension items.

---

## Data

Data come from the *Let's Story* feature of *Applaydu*, in which a family chooses a setting, a hero, a companion, a plot and a theme, and a generative model writes the story. The logs were recorded passively, with no experimental manipulation. The session-level extract stays with the data controller until the preregistration is accepted in principle.

The first tier of the sample will take every eligible completed reading by a child recorded in the 7 to 8 or 9 and older age band, excluding readings faster than 400 or slower than 10 words per minute. The second tier, for the within-child hypothesis, will take children with at least three eligible sessions on distinct texts. The primary outcome is log reading time per word, and Hypothesis 5 uses the child's optional post-reading difficulty rating.

For each text, the study will compute lexical, grammatical and discourse features. Each of those families will be reduced, blind to outcomes, to one component score: lexical difficulty, grammatical load and referential continuity. Valence, arousal, narrativity and text length will enter the models as covariates.

---

## Analytic approach

All confirmatory analyses will use Bayesian crossed-effects models, in which readings are crossed with texts, languages, countries and app versions, and with children where the data allow it. Each confirmatory coefficient will be judged against a registered region of practical equivalence, set at 0.05 standard deviations for reading time and at an odds ratio between 1/1.05 and 1.05 for the difficulty rating. A verdict therefore concerns the size and direction of an effect as well as its presence. Because the text coefficients are identified between distinct texts, the preregistration reports a simulation-based design analysis of how many distinct texts each verdict needs.

---

## Repository contents

- `preregistration/`: the protocol, its supplement and cover letter, the theory object, the design analysis, the literature sizing and the count script supplied to the data controller. Its README explains how each reported number is produced and checked.
- `poster/`: a conference poster on the study, with the code and data behind each of its figures.
- `mindmap/`: the framework figure above and the Node script that renders it.

The systematic review's extraction workflow lives in a separate, private repository, which this one does not link. Within it, `batches/corrections.csv` is the single source of truth for corrections.

`ISSUES.md` records the open findings of the code audits, and `CHANGELOG.md` records changes to the code and documentation.

## Reproducing the analyses

`preregistration/` and `poster/` each pin their R packages, for R 4.6.1, in an `renv.lock` that records each package's version and the repository it comes from. To build either environment in a separate library, leaving your own untouched, run this from the folder and then run its scripts with `R_LIBS=renv-library`:

```bash
Rscript -e 'renv::restore(lockfile = "renv.lock", library = "renv-library", prompt = FALSE)'
```

On 16 October 2026, environments restored this way from the two lockfiles alone reproduced the poster pixel for pixel, and every table, figure and checked number of the protocol that can be rebuilt without re-running its simulations. The count script and its tests use only Python's standard library, and the mindmap's Node packages are pinned in `mindmap/source files/package-lock.json`.

---

## Licence

The code is released under the MIT License (`LICENSE`), copyright the University of Oxford. Everything else the authors made, including the protocol, the poster, the figures and the data files, is released under CC BY-NC 4.0, copyright the InTRACt authors. `LICENSE-content.md` says which files fall under each, and lists the third-party material that keeps its own licence.

---

## Contact

Questions and comments are welcome via the [issue tracker](https://github.com/pablobernabeu/InTRACt_Interplay_of_Text_Reader_And_Context/issues).
