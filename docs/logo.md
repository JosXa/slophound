# Logo

`assets/logo.png` is a 1254 x 1254 RGBA PNG with a transparent background. It was produced with an image generation model from the prompt below, after several rounds of iteration on pose and expression. Keep the prompt here so the character can be regenerated or extended (favicon, sticker, dark-mode variant) without rediscovering what worked.

## Prompt

Pass the current `assets/logo.png` as the reference image so the character stays consistent.

```text
Flat vector mascot logo for a GitHub README, pure white background, no
texture, no grain. Head-and-shoulders bust of a bloodhound detective, same
character and same style as the reference image: thick uniform charcoal
outlines, flat cel-shaded fills, warm caramel fur with droopy jowls and long
ears, navy blue plaid deerstalker cap, gold monocle on a chain, navy suit
jacket with white shirt and navy tie.

Expression: contempt. Both brows lowered and level, eyes heavy-lidded, mouth
flat. No raised eyebrow, no snarl, no bared teeth.

Two white steam puffs above the cap.

He holds a sheet of paper by one corner between two claws, at arm's length,
as if about to drop it. The page shows red squiggly underlines and one word
circled in red. No readable text on the page.

Framed inside a clean charcoal circle badge outline, white inside, with the
cap and steam breaking out of the circle at the top. No text anywhere in the
image.
```

## What the iterations taught

- Contempt reads better than rage. A snarl turns him into a guard dog; heavy lids and a flat mouth make him an editor.
- A raised eyebrow fights the steam puffs. Steam says "seething", the eyebrow says "curious", and the face ends up saying neither. Keep both brows level.
- Nothing in his mouth or paw that could read as a cigarette or vape pen: no marker, no pencil, no sigh puff at mouth level.
- The circle badge with the cap breaking the top edge gives the bust a footprint and makes it work at README width. The full-body three-quarter pose lost too much detail at 240 px.
- One saturated red only, on the page marks. Everything else stays in charcoal, caramel, navy and white so the red reads as "finding".
- The generator sometimes returns a genuinely transparent background when asked for "pure white background". Check a candidate with `sips -g hasAlpha file.png` (macOS) or the PNG IHDR colour type (6 = RGBA) before assuming.

## Regenerating

Ask for five candidates per round and compare them side by side; the hit rate for pose plus expression plus framing all landing at once is roughly one in five. Save keepers with a numbered descriptive name so the round can be discussed by file name.
