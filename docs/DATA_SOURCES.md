# Sources and time semantics

| Source | Public observer use | Important limits |
| --- | --- | --- |
| Kraken public AssetPairs + Ticker | Available spot USD instruments and REST prices | Receipt timestamps; no exchange timestamp, executable-depth claim or tokenized catalog in this profile |
| Yahoo chart endpoint | Indicative tracked international observations and available sampled history | Unofficial access; delays, throttling, session closure and missing instruments |
| NSE public observation helper | Source-labelled INR observations where available | Access can fail; current holiday/special-session status is not certified by this page |
| Selected publisher feeds | Headlines, original links, available publication times | Selected coverage only; no full/paywalled article reproduction |

Quote polling and view refresh are different clocks. The page displays observation/receipt times, never a refreshed timestamp as proof a source advanced.

The browser marks data stale using source/receipt age. These thresholds are UI diagnostics, not permission to execute a trade. The public observer has no execution path.

Stats can be unavailable until enough evidence exists. A recorded ticker observation is not a fill, a news headline is not an audited fundamental statement, a sampled RSI is not a forecast, and a continuously traded asset is not proof a venue is healthy.

No API credentials are required for the public feed profile. Public access is provider-dependent and may change. This repository does not claim licensed consolidated exchange coverage or permission for every downstream commercial use.
