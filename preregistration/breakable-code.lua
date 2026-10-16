-- Let long inline code, such as a file path, break across lines in the PDF.
--
-- LaTeX sets inline code as one unbreakable box, so a path like
-- design_analysis/run_ordinal_analysis.R that falls near the end of a line runs
-- into the margin. This filter writes inline code as \texttt with a permitted
-- break after each slash, underscore, full stop and hyphen. \allowbreak is robust
-- in moving arguments, so the result is also safe inside figure and table captions.
-- Other output formats are left untouched.

local escapes = {
  ["\\"] = "\\textbackslash{}", ["{"] = "\\{", ["}"] = "\\}", ["_"] = "\\_",
  ["#"] = "\\#", ["$"] = "\\$", ["%"] = "\\%", ["&"] = "\\&",
  ["~"] = "\\textasciitilde{}", ["^"] = "\\textasciicircum{}",
}
local breaks_after = { ["/"] = true, ["_"] = true, ["."] = true, ["-"] = true }

function Code(el)
  if not FORMAT:match("latex") then return nil end
  local out = {}
  for ch in el.text:gmatch(utf8.charpattern) do
    out[#out + 1] = escapes[ch] or ch
    if breaks_after[ch] then out[#out + 1] = "\\allowbreak{}" end
  end
  return pandoc.RawInline("latex", "\\texttt{" .. table.concat(out) .. "}")
end
