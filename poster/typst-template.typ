// InTRACt poster: page geometry, type and the reusable blocks the body calls.
// Quarto inserts this file before the body (template-partials in poster.qmd).
//
// The sheet is A1 portrait, 594 x 841 mm. Sizes are set for reading at one to
// two metres: body 26 pt, section heads 36 pt, the message 46 pt, and nothing
// smaller than 22 pt anywhere on the sheet.

// The theme takes its two colours from the department's lockup: Oxford blue,
// and the green of the department's tree. That green clears only 2.8:1 against
// white, so it draws rules and bars, and a darker shade of the same hue (5.2:1)
// carries text and data. The tint behind the bands is Oxford blue at 8%.
#let ox-blue     = rgb("#002147")
#let ox-mid      = rgb("#0b3a6f")
#let ox-pale     = rgb("#b9c7d8")
#let edu-green   = rgb("#1dad89")
#let green-ink   = rgb("#127b61")
#let ink         = rgb("#16202b")
#let ink-soft    = rgb("#4a5966")
#let tint        = rgb("#eaeff5")

// Figtree, an open-licence geometric-humanist sans, stands in for Abadi, which
// is licensed for Microsoft 365 apps only and cannot be shared with the source.
#let face = "Figtree"

// The two body columns are (594 - 2 x 18 - 20) / 2 = 269 mm wide. COL_MM in
// poster.qmd draws every figure at that width, so change the three together.
#let page-margin-x = 18mm
#let col-gutter    = 20mm

// A short line above a heading names the part of the argument it belongs to.
#let kicker(body, colour: green-ink) = text(size: 23pt, weight: "bold", fill: colour,
  tracking: 0.08em)[#upper(body)]

// One sentence the reader should leave with, set apart from the running text.
#let takeaway(body) = block(width: 100%, inset: (left: 7mm, y: 3mm), above: 7mm, below: 7mm,
  stroke: (left: 2.4mm + edu-green))[
  #set text(size: 27pt, weight: "semibold", fill: ink)
  #body
]

#let caption(body) = block(above: 4mm, below: 6mm)[
  #set text(size: 22pt, fill: ink-soft)
  #set par(leading: 0.42em)
  #body
]

// The study's question, in a tinted box that opens the right-hand column.
#let question(body) = block(width: 100%, fill: tint, radius: 3mm,
  inset: (x: 8mm, y: 6mm), above: 5mm, below: 4mm)[
  #set text(size: 29pt, weight: "semibold", fill: ox-blue)
  #set par(leading: 0.42em)
  #body
]

// The safeguards strip: numbered steps in a row, each number beside its text.
#let steps(..items) = {
  let xs = items.pos()
  grid(columns: (1fr,) * xs.len(), column-gutter: 8mm,
    ..xs.enumerate().map(((i, it)) => grid(columns: (auto, 1fr), column-gutter: 4mm,
      align: (center + horizon, left + horizon),
      text(size: 64pt, weight: "bold", fill: green-ink)[#(i + 1)],
      block[
        #set text(size: 24pt)
        #set par(leading: 0.4em)
        #it
      ])))
}

// A band across the full width of the sheet, bled to its edges, with its title
// at the left and its content beside it.
#let band(title, body, fill: tint) = block(width: 100%, fill: fill,
  outset: (x: page-margin-x), inset: (y: 5mm), above: 6mm, below: 0mm)[
  #grid(columns: (auto, 1fr), column-gutter: 12mm, align: (left + horizon, left + horizon),
    block(width: 118mm)[
      #set par(leading: 0.3em)
      #text(size: 36pt, weight: "semibold", fill: ox-blue)[#title]
    ],
    body)
]

// A small label over a logo, saying what the logo stands for here.
#let logo-label(body) = text(size: 22pt, fill: ink-soft)[#body]

// The foot of the sheet, in two rows. The lower row holds the project's logo,
// the funders', the acknowledgement with the contact address, and the QR code
// that carries what the sheet leaves out, the reference list included, all
// centred on one line. Above it, short labels say what the first two logos
// stand for. The QR code's caption carries its short address, for readers who
// would rather type than scan. The funders' two logos are stacked at one
// width, so they share a single slot.
#let footer(qr: none, qr-url: none, qr-caption: none, short-url: none, project-logo: none,
            funder-logos: (), funder-text: none, thanks: none, contact: none) = block(
  width: 100%, above: 6mm)[
  #grid(columns: (auto, auto, 1fr, auto), column-gutter: 13mm, row-gutter: 2mm,
    align: (x, y) => if y == 0 { left + bottom }
      else { (left, left, center, right).at(x) + horizon },
    logo-label[Part of], logo-label[Funded by], [], [],
    image(project-logo, height: 32mm, width: auto),
    grid(columns: (auto, auto), column-gutter: 7mm, align: (center + horizon, left + horizon),
      stack(spacing: 3.5mm, ..funder-logos.map(f => image(f, width: 54mm))),
      block[
        #set text(size: 24pt, fill: ink)
        #set par(leading: 0.4em)
        #funder-text
      ]),
    block[
      #set par(leading: 0.4em)
      #text(size: 23pt, fill: ink)[#thanks]
      #v(3mm)
      #text(size: 23pt, fill: ox-mid)[#contact]
    ],
    grid(columns: (auto, 35mm), column-gutter: 6mm, align: (right + horizon, center + horizon),
      block[
        #set par(leading: 0.36em, justify: false)
        #set align(right)
        #text(size: 23pt, weight: "semibold", fill: ox-blue)[#qr-caption]
        #v(2.5mm)
        #text(size: 23pt, weight: "bold", fill: ox-blue)[#short-url]
      ],
      // On screen the code opens what it encodes, so the PDF works unprinted.
      link(qr-url, image(qr, width: 35mm))))
]

// A figure with links laid over it. Typst draws an SVG's text without the links
// it might carry, so each entry of the JSON file, which R/figures.R writes with
// the figure, places an invisible link box over the citation it opens, in mm
// from the figure's top-left corner. The figure is printed at the width it was
// drawn, so its millimetres are the page's.
#let linked-image(path, links) = block(width: 100%)[
  #image(path)
  #for l in json(links) {
    place(top + left, dx: l.x * 1mm, dy: l.y * 1mm,
      link(l.url, box(width: l.w * 1mm, height: l.h * 1mm)))
  }
]

#let poster(
  title: none,
  kicker-text: none,
  authors: (),
  logo: none,
  message: none,
  doc,
) = {
  set document(title: title, author: authors)
  set page(width: 594mm, height: 841mm, numbering: none,
    margin: (x: page-margin-x, top: 0mm, bottom: 12mm))
  // Ragged lines are broken for the paragraph as a whole, as justified text is,
  // and a last line of a single word is made costly enough that a paragraph
  // rewraps before it leaves a word stranded.
  set text(font: face, size: 26pt, fill: ink, lang: "en", region: "GB", hyphenate: false,
    costs: (runt: 20000%))
  set par(justify: false, linebreaks: "optimized", leading: 0.46em, spacing: 0.85em)
  set image(width: 100%)

  // Quarto shifts Markdown headings up one level for Typst, so the body's `##`
  // arrives here as level 1 and its `###` as level 2.
  show heading.where(level: 1): it => block(above: 10mm, below: 4mm, sticky: true)[
    #set text(size: 36pt, weight: "semibold", fill: ox-blue)
    #set par(leading: 0.3em)
    #it.body
  ]
  show heading.where(level: 2): it => block(above: 8mm, below: 3mm, sticky: true)[
    #set text(size: 30pt, weight: "bold", fill: ox-blue)
    #it.body
  ]
  // Links take no colour or underline of their own: a citation linked to its
  // DOI reads as the text around it. The footer colours the contact address.

  // Header band, bled to the sheet's edges: the study's name, the title and the
  // authors at the left, and the department's logo at the right, which stands
  // in for a printed affiliation. The logo's navy is the band's own, and a thin
  // rule in the department's green closes the band.
  block(width: 100%, fill: ox-blue, outset: (x: page-margin-x), inset: (top: 13mm, bottom: 12mm),
    stroke: (bottom: 2mm + edu-green), below: 0mm)[
    #grid(columns: (1fr, auto), column-gutter: 14mm, align: (left + horizon, right + horizon),
      [
        // Not upper-cased: the study's name carries its own capitals (InTRACt).
        #if kicker-text != none [
          #text(size: 25pt, weight: "bold", fill: ox-pale, tracking: 0.03em)[#kicker-text]
          #v(3mm)
        ]
        #block[
          #set par(leading: 0.26em)
          #text(size: 64pt, weight: "bold", fill: white)[#title]
        ]
        #v(6mm)
        // Each name is kept whole, so a line can break only between two names.
        #text(size: 31pt, weight: "semibold", fill: white)[#authors.map(a => box[#a]).join([  ·  ])]
      ],
      if logo != none { image(logo, width: 106mm) })
  ]

  // The message, in a band only as deep as its two lines.
  block(width: 100%, fill: tint, outset: (x: page-margin-x), inset: (y: 6mm), below: 7mm)[
    #set par(leading: 0.34em)
    #text(size: 46pt, weight: "semibold", fill: ox-blue)[#message]
  ]

  doc
}
