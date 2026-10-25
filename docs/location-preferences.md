# Location preferences

Each city segment has a separate lodging location preference:

- **Any location**: no geographic exclusion. If a built-in city reference and
  hotel coordinates are known, its straight-line distance is still displayed.
- **Near downtown**: use a named approximate reference point, displayed in the
  UI, plus a maximum radius in kilometers. Built-in references: Boston City Hall
  area, Chicago Loop, and Lower Manhattan. These anchors do not define official
  neighborhood boundaries; users may choose another reference instead.
- **Near a specific place**: supply a name, latitude, longitude and radius.
  Names are labels only; there is no automatic address lookup.

The Haversine calculation uses coordinates, not hotel names. Active filters
exclude hotels outside the radius and hotels without usable coordinates. An
unsupported downtown reference produces an explicit empty result, not an
unconstrained fallback. No matches produce no recommendation; partial trips are
clearly identified. Baseline savings use the same constrained hotel set as the
recommendation. Offer tables, custom-promotion previews, and reports are derived
from the same optimized result.

Demo hotel positions and area labels are illustrative fixtures, not verified
addresses. A fictional Downtown Commons Stay was added so the Boston demo can
contrast a central stay with Back Bay, Cambridge/Kendall Square, and Seaport.
Boston's approximate reference is near City Hall; coordinate context:
https://www.wikidata.org/wiki/Q250773 .

Live mode preserves coordinates from hotel search responses and falls back to
coordinates in the provider's hotel directory. Missing/invalid positions stay
unknown. Search coverage remains limited to returned provider candidates; this
is not an exhaustive search of every hotel within the chosen radius.

Distances are straight-line kilometers. The app does not infer walking routes,
transit times, traffic, neighborhood safety, or transportation costs.

## Demo

Search a Boston segment with **Near downtown**, **1 km**: the central demo hotel
is eligible. Change to **Near a specific place**, label **Kendall Square**,
latitude **42.3628**, longitude **-71.0900**, radius **0.5 km**: the Cambridge demo
hotel becomes the eligible choice. Default unrestricted demo totals retain the
same winning offers; the extra central hotel's quotes change the average-offer
baseline and total number of candidates.
