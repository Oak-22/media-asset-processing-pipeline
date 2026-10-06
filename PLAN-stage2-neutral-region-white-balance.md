# Plan: Stage 2 – Neutral-Region White Balance


## Context

Stage 2 Operation 2B sets a scene-level color baseline. White balance is
part of that, and today it is set by hand: the operator picks the WB
dropper and clicks a neutral spot in each photo.

Lightroom's own Auto WB is not a substitute. On `JB106006` (a JPEG from
the working catalog, 2026-10-01) the operator compared Auto with a
manual dropper result and preferred the manual one, because Auto leaves
too much yellow and orange:

| | Temp | Tint |
|---|---|---|
| Auto | −2 | −8 |
| Custom (dropper) | −6 | −3 |

The operator also found that clicking the large white wall in that
photo gives nearly the same result as clicking a small hand-picked gray
patch. That suggests a large neutral surface can stand in for a small
gray object, which is the hard part of automating the dropper.

Goal: set Temp and Tint for each photo in a background batch, with no
cursor takeover, and keep the operator's review as the quality guard.
This follows the same shape as the Upright Level straighten plug-in
([spike](docs/future-work/crop-auto-vs-upright-level-spike.md)): the
Lightroom SDK cannot press the WB dropper, but it can set Temperature
and Tint through `photo:applyDevelopSettings`.


## Status

Idea only. Nothing is built, and the design below is untested. The
operator has not yet given a go-ahead to build.

Observed so far (one photo, `JB106006`):

- Lightroom shows JPEG Temp and Tint on a small relative scale
  (values such as −2 and −6), not Kelvin. The SDK should accept the same
  numbers; this is not yet tested.
- Wall and gray-patch dropper results were close. How close, and across
  how many photos, is not measured.


## Open Questions

Answer these with data before building:

1. **Is the wall result consistent across the event?** Collect the
   operator's Custom WB values on 10 or more photos from different
   parts of the event, including some with no wall in frame.
2. **Is Auto's error a consistent offset?** If Custom minus Auto is
   roughly constant, the plug-in could apply that offset and need no
   image analysis. On one photo the offset is Temp −4, Tint +5, which is
   too little to rely on.
3. **How does the SDK behave on JPEG WB?** Check that setting `Temperature`
   and `Tint` through the SDK produces the same Basic panel values the
   operator sees, and whether they interact with `WhiteBalance = "Custom"`.
4. **How often is there no usable neutral region?** Close-ups, tables,
   crowds, and warm or colored walls (the curtain behind the star in
   `JB106006` is clearly warmer) are likely failures.


## Design (proposed)

```text
selected photo(s)
  -> read pixels from a preview or exported JPEG (outside Lightroom)
  -> find the largest bright, low-saturation region
  -> average its color
  -> compute the Temp and Tint that neutralize it
  -> apply through the SDK
  -> operator review (Operation 2B)
```

- **Region choice:** prefer a large, flat, bright, low-saturation area,
  such as a wall. A large area averages out noise, which matters at the
  ISO 32000 seen in the working catalog.
- **Confidence gate:** if no region passes thresholds for size,
  brightness, and low saturation, skip the photo and list it. Do not
  guess.
- **No clicking:** values are applied with the SDK, so the batch runs in
  the background like the straighten plug-in.
- **Fallback:** photos with no confident region keep their current WB
  for manual handling.

Alternative worth testing first if Open Question 2 comes out well: a
fixed offset from Auto. It needs no image analysis.


## Risks

- A wrong neutral region produces a plausible but wrong color cast. A
  missed click is obvious; a wrong cast is not.
- Mixed lighting: a "white" surface lit by stage light is not neutral.
- The operator's taste (killing yellow and orange) is not the same as
  neutral. Neutralizing a wall may still leave a cast the operator
  dislikes in warm venues.
- Pixel analysis runs outside Lightroom and needs a preview or export,
  which adds a step and a source of mismatch with what Lightroom shows.


## Validation

- Compare computed Temp and Tint with the operator's Custom values on a
  sample set. Report the difference per photo, not only the average.
- Record the skip rate and which photos were skipped.
- Count photos where the operator still changes WB after the batch,
  matching the residual-correction measures in the Stage 2 README.


## Boundaries

This plan does not claim the wall method generalizes beyond one venue,
and it does not judge which WB looks better. It aims to reproduce the
operator's own preference at batch speed.


## Next Step

Wait for the operator's go-ahead. Then collect the Open Question 1 and 2
data from the catalog (read-only), and decide between the fixed-offset
and neutral-region approaches.
