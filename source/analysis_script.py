import argparse
from pathlib import Path
 
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
 
 
DEFAULT_INPUT_NAME = "lisbon_flights_202410_202510.csv"
DEFAULT_OUTPUT_DIR_NAME = "analysis"
 
ON_TIME_LIMIT = 15
LONG_DELAY_LIMIT = 60
 
MIN_FLIGHTS = 100
 
TOP_N = 15
 
UNDISCLOSED_OPERATOR = "ZZZ"
 
DEPARTURE = "departure_deviation_min"
ARRIVAL = "arrival_deviation_min"
 
TIME_COLUMNS = ["filed_departure", "actual_departure",
                "filed_arrival", "actual_arrival"]
 
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]
 
CHART_NOTE = ("Scheduled flights departing Lisbon (LPPT), Nov 2024 - "
              "Oct 2025. Deviation = actual minus filed flight-plan "
              "time. Times in UTC. Source: EUROCONTROL.")
 
 
def load_flights(input_path):
    flights = pd.read_csv(input_path, parse_dates=TIME_COLUMNS)
    total = len(flights)
 
    flights = flights[flights["icao_flight_type"] == "S"].copy()
 
    print("Flights in file:", total)
    print("Scheduled flights kept:", len(flights))
    print("Non-scheduled left out:", total - len(flights))
 
    flights["month"] = flights["filed_departure"].dt.strftime("%Y-%m")
    flights["weekday"] = flights["filed_departure"].dt.day_of_week
    flights["hour"] = flights["filed_departure"].dt.hour
 
    return flights
 
 
def percent_above(values, limit):
    values = values.dropna()
    if len(values) == 0:
        return float("nan")
    return (values > limit).mean() * 100
 
 
def describe_deviation(values):
    values = values.dropna()
    return pd.Series({
        "flights": len(values),
        "mean_min": values.mean(),
        "median_min": values.median(),
        "std_dev_min": values.std(),
        "min_min": values.min(),
        "q1_min": values.quantile(0.25),
        "q3_min": values.quantile(0.75),
        "p90_min": values.quantile(0.90),
        "max_min": values.max(),
        "early_pct": (values < 0).mean() * 100,
        "on_time_pct": (values <= ON_TIME_LIMIT).mean() * 100,
        "delayed_over_15_pct": (values > ON_TIME_LIMIT).mean() * 100,
        "delayed_over_60_pct": (values > LONG_DELAY_LIMIT).mean() * 100,
    })
 
 
def overall_statistics(flights):
    table = pd.DataFrame()
    table["departure"] = describe_deviation(flights[DEPARTURE])
    table["arrival"] = describe_deviation(flights[ARRIVAL])
    return table.round(2)
 
 
def summarise_by(flights, column):
    groups = flights.groupby(column)
 
    table = pd.DataFrame()
    table["flights"] = groups.size()
    table["dep_mean_min"] = groups[DEPARTURE].mean()
    table["dep_median_min"] = groups[DEPARTURE].median()
    table["dep_delayed_over_15_pct"] = groups[DEPARTURE].apply(
        percent_above, ON_TIME_LIMIT)
    table["arr_mean_min"] = groups[ARRIVAL].mean()
    table["arr_median_min"] = groups[ARRIVAL].median()
    table["arr_delayed_over_15_pct"] = groups[ARRIVAL].apply(
        percent_above, ON_TIME_LIMIT)
 
    return table.round(1)
 
 
def keep_large_groups(table):
    table = table[table["flights"] >= MIN_FLIGHTS]
    return table.sort_values("flights", ascending=False)
 
 
def show_and_save(table, title, file_path):
    print("=== " + title + " ===")
    print(table.to_string())
    table.to_csv(file_path)
 
 
def finish_chart(figure, axes, title, x_label, y_label, file_path):
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel(y_label)
    axes.grid(axis="y", alpha=0.3)
    figure.text(0.01, 0.01, CHART_NOTE, fontsize=7, color="grey")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(file_path, dpi=150)
    plt.close(figure)
    print("Chart saved:", file_path)
 
 
def chart_distribution(flights, file_path):
    bins = range(-30, 121, 5)
 
    figure, axes = plt.subplots(figsize=(10, 5))
    axes.hist(flights[DEPARTURE].dropna(), bins=bins, alpha=0.6,
              label="Departure")
    axes.hist(flights[ARRIVAL].dropna(), bins=bins, alpha=0.6,
              label="Arrival")
    axes.axvline(ON_TIME_LIMIT, color="black", linestyle="--", linewidth=1,
                 label="15-minute limit")
    axes.legend()
    finish_chart(figure, axes,
                 "Distribution of deviations (-30 to +120 min shown)",
                 "Deviation (minutes)", "Number of flights", file_path)
 
 
def chart_by_month(table, file_path):
    figure, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
 
    top.plot(table.index, table["dep_delayed_over_15_pct"], marker="o",
             label="Departure")
    top.plot(table.index, table["arr_delayed_over_15_pct"], marker="o",
             label="Arrival")
    top.set_title("Flights delayed more than 15 minutes, by month")
    top.set_ylabel("% of flights")
    top.grid(axis="y", alpha=0.3)
    top.legend()
 
    bottom.plot(table.index, table["dep_median_min"], marker="o",
                label="Departure")
    bottom.plot(table.index, table["arr_median_min"], marker="o",
                label="Arrival")
    bottom.legend()
    bottom.tick_params(axis="x", rotation=45)
    finish_chart(figure, bottom, "Median deviation, by month",
                 "Month", "Minutes", file_path)
 
 
def chart_delayed_bars(table, title, x_label, file_path):
    figure, axes = plt.subplots(figsize=(10, 5))
    columns = table[["dep_delayed_over_15_pct", "arr_delayed_over_15_pct"]]
    columns.columns = ["Departure", "Arrival"]
    columns.plot.bar(ax=axes)
    axes.tick_params(axis="x", rotation=0)
    finish_chart(figure, axes, title, x_label,
                 "% delayed more than 15 minutes", file_path)
 
 
def chart_top(table, title, file_path):
    top = table.head(TOP_N)
    columns = top[["dep_delayed_over_15_pct",
                   "arr_delayed_over_15_pct"]].copy()
    columns.columns = ["Departure", "Arrival"]
 
    labels = []
    for code, count in zip(top.index, top["flights"]):
        labels.append(f"{code} ({count:,})")
    columns.index = labels
 
    columns = columns.iloc[::-1]
 
    figure, axes = plt.subplots(figsize=(10, 7))
    columns.plot.barh(ax=axes)
    axes.grid(axis="x", alpha=0.3)
    finish_chart(figure, axes, title, "% delayed more than 15 minutes", "",
                 file_path)
 
 
def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path,
                        default=script_dir / DEFAULT_INPUT_NAME)
    parser.add_argument("--output-dir", type=Path,
                        default=script_dir / DEFAULT_OUTPUT_DIR_NAME)
    args = parser.parse_args()
 
    if not args.input.is_file():
        print("ERROR: input file not found")
        return
 
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
 
    flights = load_flights(args.input)
 
    overall = overall_statistics(flights)
    show_and_save(overall, "Overall statistics", output_dir / "overall.csv")
 
    by_month = summarise_by(flights, "month")
    show_and_save(by_month, "By month", output_dir / "by_month.csv")
 
    by_weekday = summarise_by(flights, "weekday")
    by_weekday.index = DAY_NAMES
    by_weekday.index.name = "weekday"
    show_and_save(by_weekday, "By day of the week",
                  output_dir / "by_weekday.csv")
 
    by_hour = summarise_by(flights, "hour")
    show_and_save(by_hour, "By hour of filed departure (UTC)",
                  output_dir / "by_hour.csv")
 
    by_segment = keep_large_groups(
        summarise_by(flights, "statfor_market_segment"))
    show_and_save(by_segment, "By market segment (at least 100 flights)",
                  output_dir / "by_segment.csv")
 
    undisclosed = flights[flights["airline"] == UNDISCLOSED_OPERATOR]
    print("Flights with undisclosed operator (ZZZ), left out of the airline ranking:",
          len(undisclosed))
    known_airlines = flights[flights["airline"] != UNDISCLOSED_OPERATOR]
    by_airline = keep_large_groups(summarise_by(known_airlines, "airline"))
    show_and_save(by_airline, "By airline (at least 100 flights)",
                  output_dir / "by_airline.csv")
 
    by_destination = keep_large_groups(summarise_by(flights, "destination"))
    show_and_save(by_destination, "By destination (at least 100 flights)",
                  output_dir / "by_destination.csv")
 
    chart_distribution(flights, output_dir / "chart_distribution.png")
    chart_by_month(by_month, output_dir / "chart_by_month.png")
    chart_delayed_bars(by_weekday,
                       "Flights delayed more than 15 minutes, by day of the week",
                       "Day of the week", output_dir / "chart_by_weekday.png")
 
    busy_hours = by_hour[by_hour["flights"] >= MIN_FLIGHTS]
    chart_delayed_bars(busy_hours,
                       "Flights delayed more than 15 minutes, by hour of filed departure",
                       "Hour (UTC)", output_dir / "chart_by_hour.png")
 
    chart_delayed_bars(by_segment,
                       "Flights delayed more than 15 minutes, by market segment",
                       "Market segment", output_dir / "chart_by_segment.png")
    chart_top(by_airline,
              "Top 15 airlines by number of flights: % delayed more than 15 minutes",
              output_dir / "chart_top_airlines.png")
    chart_top(by_destination,
              "Top 15 destinations by number of flights: % delayed more than 15 minutes",
              output_dir / "chart_top_destinations.png")
 
    print("All tables and charts are in:", output_dir.resolve())
 
 
if __name__ == "__main__":
    main()