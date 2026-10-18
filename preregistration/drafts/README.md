# Earlier drafts of the protocol

Every dated draft of the protocol is kept, by the author's decision, as the record of what each
version said. The current draft sits one folder up, and this folder holds every draft
that came before it. When a render writes a new draft, `../_rename-output.R` moves the one before it here,
so nothing in this folder is edited after it arrives.

The PDFs are the faithful record. The HTML drafts load Quarto's styles and scripts from
`preregistration_files/libs/` in this folder, which holds a copy of the library files they name.
Each HTML draft also names its figures and its PDF by paths relative to the folder it was
rendered in, so here those links do not resolve. Before the move, they showed whichever
version of each figure was current when the draft was opened (register item RS-07 in
`../../ISSUES.md`). Every draft from 7 June to 29 July 2026 apart from that of 21 July
embeds everything it needs, so only its link to the PDF fails. Eleven of those, dated 17 June
to 29 July, were rendered on a parallel branch, `code-based-diagram`, and joined the others
here on 18 October 2026.
