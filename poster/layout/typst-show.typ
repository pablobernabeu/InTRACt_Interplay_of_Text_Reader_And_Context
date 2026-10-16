#show: doc => poster(
$if(title)$
  title: [$title$],
$endif$
$if(kicker)$
  kicker-text: [$kicker$],
$endif$
$if(by-author)$
  authors: ($for(by-author)$"$it.name.literal$",$endfor$),
$endif$
$if(header-logo)$
  logo: "$header-logo$",
$endif$
$if(message)$
  message: [$message$],
$endif$
$if(bleed)$
  print-bleed: true,
$endif$
  doc,
)
