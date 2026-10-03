# NFL QB cap share, 2000–2026

How much of the NFL salary cap goes to quarterback contracts, league-wide and per player.

- `qb-cap-share.html`: an interactive page you can open in a browser
- `qb_overall.csv`: league-wide share per season (APY and cap-hit measures, all QBs and each team's top QB)
- `qb_seasons.csv`: each player's season cap hit and in-force contract APY
- `qb_contracts.csv`: every QB contract with its APY as a share of the cap at signing
- `build.py`: regenerates the CSVs

To rebuild, run this:

```
curl -sSL -o nfl-qb-cap/contracts.parquet https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet
pip install pandas pyarrow
python3 nfl-qb-cap/build.py
```

The contract data is OverTheCap's archive, distributed by nflverse. The cap figures are the official per-team caps, and 2010 (uncapped) uses the 2009 figure.
