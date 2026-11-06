#!/usr/bin/env python3


import csv
from datetime import datetime
from pathlib import Path

import airportsdata
from flask import Flask, render_template, request, send_from_directory

# Settings
ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "source" / "analysis"
ORIGIN_AIRPORT = "LPPT"
TOP_N = 15             # airlines shown in the ranking chart
MIN_FLIGHTS = 100      # hours with fewer flights are left out of the hour chart

# Distribution page: the strip chart shows this range of minutes.
STRIP_MIN = -30
STRIP_MAX = 60

# Menu: (function name of the page, text shown in the menu).
NAV = [
    ("overview", "Overview"),
    ("distribution", "Distribution"),
    ("when", "When"),
    ("airlines", "Airlines"),
    ("destinations", "Destinations"),
    ("about", "About"),
]

# Names shown for the rows of overall.csv.
STAT_LABELS = {
    "flights": "Flights",
    "mean_min": "Mean (min)",
    "median_min": "Median (min)",
    "std_dev_min": "Standard deviation (min)",
    "min_min": "Minimum (min)",
    "q1_min": "1st quartile, Q1 (min)",
    "q3_min": "3rd quartile, Q3 (min)",
    "p90_min": "90th percentile (min)",
    "max_min": "Maximum (min)",
    "early_pct": "Early (%)",
    "on_time_pct": "On time, ≤ 15 min (%)",
    "delayed_over_15_pct": "Delayed > 15 min (%)",
    "delayed_over_60_pct": "Delayed > 60 min (%)",
}

# Loading the data

# Converts the text of a CSV cell into an int or a float when possible.
def to_number(text: str):
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


# Reads one table from the analysis folder as a list of dictionaries.
# The first column (month, airline, ...) is also stored under "label", so
# that the templates can treat every table the same way.
def load_table(name: str) -> list:
    rows = []
    with open(ANALYSIS_DIR / f"{name}.csv", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        first_column = reader.fieldnames[0]
        for row in reader:
            clean = {}
            for column, value in row.items():
                clean[column] = to_number(value)
            clean["label"] = clean[first_column]
            rows.append(clean)
    return rows


# overall.csv has one row per statistic and two columns (departure, arrival).
# Returns e.g. overall["median_min"]["departure"].
def load_overall() -> dict:
    overall = {}
    for row in load_table("overall"):
        overall[row["label"]] = {"departure": row["departure"], "arrival": row["arrival"]}
    return overall


# Adds name, city, country and coordinates to every destination.
# Returns Lisbon's airport, the destinations found, and the codes not found.
def add_airport_details(destinations: list) -> tuple:
    airports = airportsdata.load("ICAO")
    found = []
    missing = []
    for row in destinations:
        airport = airports.get(row["label"])
        if airport is None:
            missing.append(row["label"])
            continue
        row["name"] = airport["name"]
        row["city"] = airport["city"]
        row["country"] = airport["country"]
        row["lat"] = airport["lat"]
        row["lon"] = airport["lon"]
        found.append(row)
    return airports[ORIGIN_AIRPORT], found, missing


# "2025-08" -> "Aug 2025"
def month_name(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


if not ANALYSIS_DIR.is_dir():
    raise SystemExit(f"ERROR: {ANALYSIS_DIR} not found. Run process_lisbon_flights.py "
                     "and then analyse_lisbon_flights.py in the source folder first.")

# The tables are small, so they are read once, when the app starts.
OVERALL = load_overall()
BY_MONTH = load_table("by_month")
BY_WEEKDAY = load_table("by_weekday")
BY_HOUR = load_table("by_hour")
BY_SEGMENT = load_table("by_segment")
BY_AIRLINE = load_table("by_airline")
BY_DESTINATION = load_table("by_destination")
LISBON, MAPPED_DESTINATIONS, UNMAPPED_DESTINATIONS = add_airport_details(BY_DESTINATION)


# web app

app = Flask(__name__)

# Number formats used in the templates, e.g. {{ value | pct }}.
@app.template_filter("count")
def format_count(value) -> str:
    return f"{int(value):,}"

@app.template_filter("minutes")
def format_minutes(value) -> str:
    return f"{value:.1f} min"

@app.template_filter("pct")
def format_pct(value) -> str:
    return f"{value:.1f}%"

# Makes the menu available in every template.
@app.context_processor
def add_menu() -> dict:
    return {"nav": NAV}

# Page 1: KPI cards.
@app.route("/")
def overview():
    total = OVERALL["flights"]["departure"]

    worst_month = BY_MONTH[0]
    for row in BY_MONTH:
        if row["dep_delayed_over_15_pct"] > worst_month["dep_delayed_over_15_pct"]:
            worst_month = row

    busiest = BY_AIRLINE[0]     # the table is already sorted by number of flights
    busiest_share = busiest["flights"] / total * 100

    cards = [
        {"icon": "🛫", "tone": "blue", "label": "Scheduled flights",
         "value": f"{int(total):,}", "sub": "Nov 2024 – Oct 2025"},
        {"icon": "✅", "tone": "green", "label": "On-time departures",
         "value": format_pct(OVERALL["on_time_pct"]["departure"]),
         "sub": "left at most 15 min after the filed time"},
        {"icon": "🛬", "tone": "green", "label": "On-time arrivals",
         "value": format_pct(OVERALL["on_time_pct"]["arrival"]),
         "sub": "arrived at most 15 min after the filed time"},
        {"icon": "⏱️", "tone": "purple", "label": "Median departure delay",
         "value": format_minutes(OVERALL["median_min"]["departure"]),
         "sub": f"mean {format_minutes(OVERALL['mean_min']['departure'])}"},
        {"icon": "⏱️", "tone": "purple", "label": "Median arrival delay",
         "value": format_minutes(OVERALL["median_min"]["arrival"]),
         "sub": f"mean {format_minutes(OVERALL['mean_min']['arrival'])}"},
        {"icon": "🐢", "tone": "pink", "label": "Delayed over 1 hour",
         "value": format_pct(OVERALL["delayed_over_60_pct"]["departure"]),
         "sub": f"of departures · arrivals {format_pct(OVERALL['delayed_over_60_pct']['arrival'])}"},
        {"icon": "🐇", "tone": "blue", "label": "Left early",
         "value": format_pct(OVERALL["early_pct"]["departure"]),
         "sub": "departed before the filed time"},
        {"icon": "☀️", "tone": "amber", "label": "Worst month",
         "value": month_name(worst_month["label"]),
         "sub": f"{format_pct(worst_month['dep_delayed_over_15_pct'])} of departures delayed > 15 min"},
        {"icon": "👑", "tone": "amber", "label": "Busiest airline",
         "value": busiest["label"],
         "sub": f"{busiest['flights']:,} flights · {busiest_share:.0f}% of all"},
    ]
    return render_template("index.html", title="Overview", cards=cards)

# Position of a value on the strip chart, as a percentage of its width.
def strip_position(value: float) -> float:
    value = max(STRIP_MIN, min(STRIP_MAX, value))
    return (value - STRIP_MIN) / (STRIP_MAX - STRIP_MIN) * 100

# Page 2: histogram, strip chart and the full statistics table.
@app.route("/distribution")
def distribution():
    strips = []
    for direction in ["departure", "arrival"]:
        values = {}
        for stat in ["q1_min", "median_min", "mean_min", "q3_min", "p90_min"]:
            values[stat] = OVERALL[stat][direction]
        positions = {}
        for stat, value in values.items():
            positions[stat] = strip_position(value)
        strips.append({"name": direction.capitalize(), "numbers": values, "positions": positions})

    ticks = []
    for minute in range(STRIP_MIN, STRIP_MAX + 1, 15):
        ticks.append({"label": minute, "position": strip_position(minute)})

    stats = []
    for key, label in STAT_LABELS.items():
        stats.append({"label": label, "departure": OVERALL[key]["departure"],
                      "arrival": OVERALL[key]["arrival"]})

    return render_template("distribution.html", title="Distribution", strips=strips,
                           ticks=ticks, limit_position=strip_position(15),
                           stats=stats, overall=OVERALL)

# The histogram PNG made by the analysis script.
@app.route("/charts/<path:name>")
def chart_image(name):
    return send_from_directory(ANALYSIS_DIR, name)

# Turns a table into the lists Chart.js needs: labels and one list per series.
def chart_data(rows: list, labels: list) -> dict:
    departure = []
    arrival = []
    for row in rows:
        departure.append(row["dep_delayed_over_15_pct"])
        arrival.append(row["arr_delayed_over_15_pct"])
    return {"labels": labels, "departure": departure, "arrival": arrival}

# Page 3: by month, by day of the week, by hour.
@app.route("/when")
def when():
    month_labels = []
    for row in BY_MONTH:
        month_labels.append(month_name(row["label"]))

    weekday_labels = []
    for row in BY_WEEKDAY:
        weekday_labels.append(row["label"])

    # Night hours have very few flights, so only busy hours are drawn.
    busy_hours = []
    hour_labels = []
    for row in BY_HOUR:
        if row["flights"] >= MIN_FLIGHTS:
            busy_hours.append(row)
            hour_labels.append(f"{row['label']:02d}:00")

    return render_template("when.html", title="When",
                           by_month=chart_data(BY_MONTH, month_labels),
                           by_weekday=chart_data(BY_WEEKDAY, weekday_labels),
                           by_hour=chart_data(busy_hours, hour_labels))

# Page 4: airline ranking, one airline compared with all flights, segments.
@app.route("/airlines")
def airlines():
    top = BY_AIRLINE[:TOP_N]
    top_labels = []
    for row in top:
        top_labels.append(f"{row['label']} ({row['flights']:,})")

    # The airline chosen in the drop-down list (?code=RYR), TAP by default.
    code = request.args.get("code", BY_AIRLINE[0]["label"])
    selected = BY_AIRLINE[0]
    for row in BY_AIRLINE:
        if row["label"] == code:
            selected = row

    # (text, airline column, overall statistic, overall column)
    metrics = [
        ("Departures delayed > 15 min", "dep_delayed_over_15_pct", "delayed_over_15_pct", "departure"),
        ("Arrivals delayed > 15 min", "arr_delayed_over_15_pct", "delayed_over_15_pct", "arrival"),
        ("Median departure delay", "dep_median_min", "median_min", "departure"),
        ("Median arrival delay", "arr_median_min", "median_min", "arrival"),
        ("Mean departure delay", "dep_mean_min", "mean_min", "departure"),
        ("Mean arrival delay", "arr_mean_min", "mean_min", "arrival"),
    ]
    comparison = []
    for text, airline_column, stat, direction in metrics:
        airline_value = selected[airline_column]
        overall_value = OVERALL[stat][direction]
        comparison.append({
            "label": text,
            "airline": airline_value,
            "overall": overall_value,
            "is_pct": airline_column.endswith("_pct"),
            "better": airline_value <= overall_value,    # lower delay is better
        })

    return render_template("airlines.html", title="Airlines",
                           top=chart_data(top, top_labels), airlines=BY_AIRLINE,
                           selected=selected, comparison=comparison, segments=BY_SEGMENT)

# Page 5: map of the routes from Lisbon.
@app.route("/destinations")
def destinations():
    return render_template("destinations.html", title="Destinations",
                           lisbon=LISBON, destinations=MAPPED_DESTINATIONS,
                           missing=UNMAPPED_DESTINATIONS)

# Page 6: data source and method.
@app.route("/about")
def about():
    return render_template("about.html", title="About")

# Runs the app only when this file is started directly with python3.
if __name__ == "__main__":
    app.run(debug=True)
