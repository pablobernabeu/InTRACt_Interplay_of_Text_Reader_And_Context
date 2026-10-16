-- Links each citation to the work it cites: its DOI where it has one, otherwise
-- its URL. Quarto runs citeproc after every Lua filter, too late to link what
-- citeproc writes, so this filter runs citeproc itself and then replaces each
-- citation with a link around its author-date text. No citation is left for
-- Quarto's own citeproc pass, which then changes nothing, and the bibliography
-- stays suppressed. The link takes no style of its own (the template sets
-- none), so a citation reads as the text around it on paper and opens its
-- source in the PDF. Each citation is also set in a Typst box, which a line
-- cannot break, so that no citation is split across two lines.

local function unbroken(inlines)
  local out = pandoc.List({ pandoc.RawInline("typst", "#box[") })
  out:extend(inlines)
  out:insert(pandoc.RawInline("typst", "]"))
  return out
end

local function target(ref)
  local doi = ref.DOI or ref.doi
  if doi then return "https://doi.org/" .. pandoc.utils.stringify(doi) end
  local url = ref.URL or ref.url
  if url then return pandoc.utils.stringify(url) end
  return nil
end

function Pandoc(doc)
  local url_of = {}
  for _, ref in ipairs(pandoc.utils.references(doc)) do
    url_of[ref.id] = target(ref)
  end
  doc = pandoc.utils.citeproc(doc)
  return doc:walk({
    Cite = function(cite)
      -- A citation of several works would need one link per work inside one
      -- formatted string, so it keeps its text unlinked; the poster has none.
      if #cite.citations == 1 then
        local url = url_of[cite.citations[1].id]
        if url then return unbroken({ pandoc.Link(cite.content, url) }) end
      end
      return unbroken(cite.content)
    end,
  })
end
