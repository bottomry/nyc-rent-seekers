# Rent Freeze program evidence

The borough panel reproduces **Table 5, page 7** of the NYC Department of Finance's
[June 2025 Rent Freeze report](https://www.nyc.gov/assets/rentfreeze/downloads/pdf/2025-scrie_drie_report.pdf).
It covers 2024 DOF-administered SCRIE and DRIE benefits and excludes HPD-administered SCRIE.
These are administrative arithmetic means, not survey medians. The records overlap regulated
housing; they cannot be added to the primary survey groups as an independent population.

Current rent, frozen rent and monthly benefit are three separately published fields. Rounded means
need not subtract exactly: Queens reports $1,319 current rent, $1,043 frozen rent and a $277 benefit.
The panel preserves those values rather than manufacturing a $276 benefit from rounded inputs.
This program measure does not enter the NYCHVS market-minus-group calculation.

To reproduce the extraction, download the cited PDF, run `pdftotext -layout` on it, and pass its text
and SHA-256 to `rent_seekers.normalize.rent_freeze.parse_borough_table`. The parser requires the
specific table title, population scope and all five borough rows. The public JSON at
`web/public/data/rent-freeze/boroughs.json` records the source checksum, table, page, vintage,
statistic, scope and extraction method. Only aggregate report values are published.
