Version: v1.0.0
Date: 2026-06-27
Time: 23:22

Type: MINOR

Files:

* data/DataHouse/config.py
* data/DataHouse/coletores/RiskSentiment.py

Description:

* Added raw_dir config pointing to data/raw/
* Added per-asset raw data export to data/raw/<symbol>.csv on each pipeline run
* Each raw file contains columns: date, value

Reason:

* Enable downstream consumption of individual asset raw time series
* Decouple raw data from the consolidated RiskSentiment.csv pipeline

Rollback:

* Git checkpoint: dde7049
