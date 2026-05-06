# InTRACt: Interplay of Text, Reader And Context in children’s digital reading comprehension

*Work in progress — this repository contains an ongoing literature review and a preregistration document that are being actively developed.*

---

## About the project

How does the language in a story shape how quickly and how well a child understands it? And does it matter whether the child is 7 or 10 years old, or whether the story is read aloud by an app?

InTRACt is a preregistered study that analyses large-scale behavioural data from children aged 7–10 who read AI-generated storybooks through *Let's Story*, a feature of the *Applaydu* edutainment app (Gameloft / Ferrero International). By combining computational psycholinguistics with Bayesian statistical modelling, the study investigates how measurable properties of text — word frequency, syntactic complexity, semantic coherence — predict children's reading behaviour in the wild, across more than 19 languages and 40 countries.

The project is hosted at the **[Department of Education, University of Oxford](https://www.education.ox.ac.uk/)** and is embedded within the **[Learning in Families through Technology (LIFT)](https://www.education.ox.ac.uk/project/lift-learning-in-families-through-technology/)** project, which investigates how digital technologies shape learning within families. It is funded by **Kinder** and the **John Fell Fund** (University of Oxford).

---

## Background

Reading comprehension depends on both the reader and the text. Laboratory research has established that measurable features of written text reliably predict how long readers take and how much they understand. At the word level, less frequent and more abstract words slow readers down and are harder to retain. At the sentence level, longer and more structurally complex sentences impose greater demands on working memory. At the level of the whole passage, texts in which sentences connect logically and explicitly — high in discourse coherence — are generally easier to follow than those that leave more to inference.

These effects are well established in adults, but children's reading is distinct. Younger readers have smaller vocabularies, less automatised decoding, and more limited working memory — all of which change considerably across the 7–10 age range. At the same time, the rise of AI-generated text and edutainment apps has opened new windows onto children's naturalistic reading at a scale that laboratory studies cannot match. InTRACt bridges these two traditions.

---

## Conceptual framework

The diagram below summarises the study's theoretical model. Reader and context variables — including children's linguistic resources, sociocultural context, and developmental status — and text features — covering lexical, syntactic, discourse, and affective properties — jointly predict comprehension outcomes, with children's longitudinal progression as a cross-cutting temporal dimension.

![Conceptual framework of the study showing reader and context variables (linguistic resources, sociocultural context, developmental status) and text features (lexical-distributional, syntactic and discourse, affective properties) jointly predicting comprehension outcomes (processing efficiency, perceived difficulty, situation model construction), with longitudinal progression as a cross-cutting temporal dimension.](mindmap/mindmap.png)

---

## Hypotheses

The study tests five pre-registered, directional predictions. The first and most general is that linguistically more demanding stories — with less frequent words, greater syntactic complexity, and lower coherence — will take children longer to read per word. The remaining four predictions concern how this relationship varies with the child and the reading context.

The effect of syntactic complexity is expected to be larger for younger children (7–8) than for older children (9–10), because working memory, which is needed to keep track of long or embedded sentences, is still developing at this age. Relatedly, discourse coherence — the degree to which a text guides the reader from one idea to the next — is expected to benefit younger readers most, as older children are better placed to generate the inferences that low-coherence text demands. The app's read-aloud narration feature, which plays an audio recording of the story, is similarly expected to produce larger gains for younger children, whose decoding fluency is less established. Finally, the study predicts that children who read more quickly will also score more accurately on in-app comprehension questions, consistent with the well-documented link between reading fluency and comprehension.

---

## Data

Data come from the *Let's Story* feature of *Applaydu*, which enables families to co-create AI-generated storybooks. In the first six months after launch in late 2024, over 2.4 million story sessions were recorded across more than 40 countries. The study sample includes children aged 7–10 who provided parental consent in-app, completed at least five distinct story sessions, and produced reading times within plausible bounds. All data are anonymised and collected passively, with no experimental manipulation. The primary outcome is how long children spend reading each word; in-app quiz accuracy serves as a secondary measure of comprehension.

For each story, the study computes a broad range of computational text indices covering word frequency, vocabulary diversity, sentence structure, semantic coherence between sentences, connective density, and affective properties such as sentiment and emotional arousal. Before modelling, these indices are reduced to a smaller number of interpretable composite scores, which then serve as predictors.

---

## Analytic approach

All confirmatory analyses use Bayesian hierarchical models, a framework suited to the present data because the scientific questions concern the size and direction of effects rather than their mere existence, and because the very large sample would render conventional significance tests uninformative. The models account for the fact that reading sessions are nested within children, who are in turn nested within languages. For each hypothesis, the study reports the estimated effect, its uncertainty, and whether the effect is large enough to be educationally meaningful — a distinction that matters when sample sizes are in the millions.

---

## Repository contents

The `preregistration/` folder contains the preregistration document in Quarto source format alongside rendered HTML drafts and the associated reference library. The `mindmap/` folder contains the conceptual framework figure and its source files.

---

## Contact

Questions and comments are welcome via the [issue tracker](../../issues).

