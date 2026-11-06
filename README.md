# iseg-programming-foundations-project

Descriptive statistics of the scheduled flights departing Lisbon (LPPT),
November 2024 - October 2025, from EUROCONTROL data, plus a small Flask web
app to explore the results.

## How to run

1. Put the monthly EUROCONTROL files (`Flights_YYYYMM.csv`) in `raw-data/`.
2. Create a virtual environment and install the libraries:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install pandas matplotlib -r webapp/requirements.txt
   ```

3. Build the dataset and the statistics (from the `source` folder):

   ```bash
   cd source
   python3 process_lisbon_flights.py --input-dir ../raw-data --output lisbon_flights_202410_202510.csv
   python3 analyse_lisbon_flights.py --input lisbon_flights_202410_202510.csv --output-dir analysis
   ```

4. Start the web app (from the `webapp` folder) and open http://127.0.0.1:5000:

   ```bash
   cd ../webapp
   python3 app.py
   ```

## Pages

- **Overview**: KPI cards with the headline numbers.
- **Distribution**: how the deviations are spread (quartiles, mean, histogram).
- **When**: delays by month, day of the week and hour.
- **Airlines**: ranking, compare one airline with all flights, market segments.
- **Destinations**: map of every route from Lisbon; colour = % delayed, thickness = mean delay.
- **About**: data source and method.
