-- Turns a fenced div whose class names one of the template's blocks into a call
-- to that block: `::: {.caption}` becomes `#caption[...]`. The div's content is
-- left as Pandoc elements, so citations in it pass through citeproc and inline
-- R through knitr, neither of which reaches text written as raw Typst.
local blocks = { caption = true, takeaway = true }

function Div(el)
  for _, cls in ipairs(el.classes) do
    if blocks[cls] then
      local out = pandoc.List({ pandoc.RawBlock("typst", "#" .. cls .. "[") })
      out:extend(el.content)
      out:insert(pandoc.RawBlock("typst", "]"))
      return out
    end
  end
end
