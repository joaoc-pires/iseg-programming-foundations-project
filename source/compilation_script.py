import argparse
import csv
from datetime import date, datetime
from pathlib import Path
 
 
ORIGIN_AIRPORT = "LPPT"
 
FIRST_MONTH = "202410"
LAST_MONTH = "202510"
 
PERIOD_START = date(2024, 10, 1)
PERIOD_END = date(2025, 10, 31)
 
TIME_FORMAT = "%d-%m-%Y %H:%M:%S"
 
LARGE_DEVIATION_MIN = 24 * 60
 
DEFAULT_OUTPUT_NAME = "lisbon_flights_202410_202510.csv"
 
INPUT_COLUMNS = {
    "flight_id": "ectrl id",
    "origin": "adep",
    "destination": "ades",
    "airline": "ac operator",
    "filed_departure": "filed off block time",
    "actual_departure": "actual off block time",
    "filed_arrival": "filed arrival time",
    "actual_arrival": "actual arrival time",
    "icao_flight_type": "icao flight type",
    "statfor_market_segment": "statfor market segment",
    "ac_type": "ac type",
}
 
TIME_COLUMNS = ["filed_departure", "actual_departure",
                "filed_arrival", "actual_arrival"]
 
OUTPUT_COLUMNS = [
    "flight_id", "flight_date", "origin", "destination", "airline",
    "filed_departure", "actual_departure", "departure_deviation_min",
    "filed_arrival", "actual_arrival", "arrival_deviation_min",
    "icao_flight_type", "source_file", "statfor_market_segment", "ac_type",
]
 
 
def find_files(input_dir):
    files = []
 
    for path in sorted(input_dir.glob("Flights_??????.csv")):
        month = path.stem[8:]
        if FIRST_MONTH <= month <= LAST_MONTH:
            files.append(path)
 
    return files
 
 
def parse_time(text):
    try:
        return datetime.strptime(text, TIME_FORMAT)
    except ValueError:
        return None
 
 
def deviation_minutes(actual, filed):
    if actual is None or filed is None:
        return None
 
    difference = actual - filed
 
    return round(difference.total_seconds() / 60, 2)
 
 
def process_file(path, flights, seen_rows, stats):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, restval="")
 
        if reader.fieldnames is None:
            print("WARNING: file is empty", path.name)
            return False
 
        clean_names = []
        for name in reader.fieldnames:
            clean_names.append(" ".join(name.split()).lower())
        reader.fieldnames = clean_names
 
        missing = []
        for name in INPUT_COLUMNS.values():
            if name not in clean_names:
                missing.append(name)
        if len(missing) > 0:
            print("WARNING: file skipped, missing columns:", missing)
            return False
 
        for row in reader:
            stats["Records examined"] += 1
 
            if row["adep"].strip() != ORIGIN_AIRPORT:
                continue
            stats["LPPT departures"] += 1
 
            values = {}
            for output_name, input_name in INPUT_COLUMNS.items():
                values[output_name] = row[input_name].strip()
 
            signature = tuple(values.values())
            if signature in seen_rows:
                stats["Exact duplicates"] += 1
                print("WARNING: exact duplicate skipped", path.name,
                      reader.line_num)
                continue
            seen_rows.add(signature)
 
            times = {}
            malformed = []
            for column in TIME_COLUMNS:
                times[column] = parse_time(values[column])
                if values[column] != "" and times[column] is None:
                    malformed.append(column)
            if len(malformed) > 0:
                stats["Malformed records"] += 1
                print("WARNING: malformed", malformed, path.name,
                      reader.line_num)
 
            reference = times["filed_departure"]
            if reference is None:
                reference = times["actual_departure"]
            if reference is None:
                stats["Without any departure time"] += 1
                continue
 
            flight_date = reference.date()
            if flight_date < PERIOD_START or flight_date > PERIOD_END:
                stats["Outside requested period"] += 1
                continue
 
            departure_dev = deviation_minutes(
                times["actual_departure"], times["filed_departure"])
            arrival_dev = deviation_minutes(
                times["actual_arrival"], times["filed_arrival"])
 
            if departure_dev is not None and abs(departure_dev) > LARGE_DEVIATION_MIN:
                stats["Deviations beyond 24h"] += 1
            if arrival_dev is not None and abs(arrival_dev) > LARGE_DEVIATION_MIN:
                stats["Deviations beyond 24h"] += 1
            if times["actual_arrival"] is not None and times["actual_departure"] is not None:
                if times["actual_arrival"] < times["actual_departure"]:
                    stats["Arrival before departure"] += 1
 
            values["flight_date"] = flight_date.isoformat()
            for column in TIME_COLUMNS:
                if times[column] is None:
                    values[column] = ""
                else:
                    values[column] = times[column].isoformat()
            if departure_dev is None:
                departure_dev = ""
            if arrival_dev is None:
                arrival_dev = ""
            values["departure_deviation_min"] = departure_dev
            values["arrival_deviation_min"] = arrival_dev
            values["source_file"] = path.name
 
            flights.append(values)
 
    return True
 
 
def sort_key(row):
    departure = row["filed_departure"]
    if departure == "":
        departure = row["actual_departure"]
    return (departure, row["flight_id"])
 
 
def write_csv(flights, output_path):
    with open(output_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in flights:
            writer.writerow(row)
 
 
def main():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=script_dir)
    parser.add_argument("--output", type=Path,
                        default=script_dir / DEFAULT_OUTPUT_NAME)
    args = parser.parse_args()
 
    if not args.input_dir.is_dir():
        print("ERROR: input folder not found")
        return
 
    files = find_files(args.input_dir)
    if len(files) == 0:
        print("ERROR: no Flights_YYYYMM.csv files found")
        return
 
    stats = {
        "Records examined": 0,
        "LPPT departures": 0,
        "Outside requested period": 0,
        "Without any departure time": 0,
        "Malformed records": 0,
        "Exact duplicates": 0,
        "Deviations beyond 24h": 0,
        "Arrival before departure": 0,
    }
    flights = []
    seen_rows = set()
    processed = 0
 
    for path in files:
        print("Processing", path.name)
        if process_file(path, flights, seen_rows, stats):
            processed += 1
 
    flights.sort(key=sort_key)
    write_csv(flights, args.output)
 
    valid_departure = 0
    valid_arrival = 0
    missing_pair = 0
    for row in flights:
        if row["departure_deviation_min"] != "":
            valid_departure += 1
        if row["arrival_deviation_min"] != "":
            valid_arrival += 1
        if row["departure_deviation_min"] == "" or row["arrival_deviation_min"] == "":
            missing_pair += 1
 
    print("Monthly files discovered:", len(files))
    print("Files successfully processed:", processed)
    for label, count in stats.items():
        print(label, count)
    print("Flights written:", len(flights))
    print("Valid departure deviations:", valid_departure)
    print("Valid arrival deviations:", valid_arrival)
    print("Missing either timestamp pair:", missing_pair)
    if len(flights) > 0:
        print("First flight date:", flights[0]["flight_date"])
        print("Last flight date:", flights[-1]["flight_date"])
    print("Output CSV:", args.output.resolve())
 
 
if __name__ == "__main__":
    main()