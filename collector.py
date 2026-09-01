import os
import csv
import time
from datetime import datetime, timezone, timedelta
import requests

# Retrieve API keys from GitHub Secrets
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
OPENWEATHER_KEY = os.environ.get('OPENWEATHER_API_KEY')

# Standardized ~7 km Srinagar Traffic Corridors
CORRIDORS = [
    {"id": 1, "name": "Lal Chowk to Hyderpora", "origin": "Lal Chowk, Srinagar", "destination": "Hyderpora, Srinagar"},
    {"id": 2, "name": "Dalgate to Pantha Chowk", "origin": "Dalgate, Srinagar", "destination": "Pantha Chowk, Srinagar"},
    {"id": 3, "name": "Jahangir Chowk to Parimpora", "origin": "Jahangir Chowk, Srinagar", "destination": "Parimpora, Srinagar"}
]

RAW_CSV_FILE = "raw_traffic_data.csv"
ENRICHED_CSV_FILE = "enriched_traffic_data.csv"

def fetch_with_retry(url, max_attempts=3, timeout=15):
    """Executes HTTP GET requests with max_attempts retry logic and HTTP status validation."""
    for attempt in range(1, max_attempts + 1):
        try:
            res = requests.get(url, timeout=timeout)
            res.raise_for_status()
            return res.json(), "OK"
        except requests.exceptions.RequestException as e:
            if attempt == max_attempts:
                return None, f"HTTP_ERROR_{type(e).__name__}"
            time.sleep(2)

def get_weather():
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Srinagar,IN&appid={OPENWEATHER_KEY}&units=metric"
    data, status = fetch_with_retry(url)
    
    if data and data.get("cod") == 200:
        return {
            "weather_api_status": "OK",
            "temp": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "weather_main": data["weather"][0]["main"],
            "rain_1h": data.get("rain", {}).get("1h", 0)
        }
    return {
        "weather_api_status": status if status != "OK" else f"API_COD_{data.get('cod') if data else 'NO_DATA'}",
        "temp": None, "humidity": None, "weather_main": None, "rain_1h": None
    }

def get_traffic_data(origin, destination):
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin}&destinations={destination}&departure_time=now&key={GOOGLE_MAPS_KEY}"
    data, http_status = fetch_with_retry(url)
    
    if not data:
        return {
            "route_status": http_status, "traffic_data_status": "UNAVAILABLE",
            "distance_km": None, "reference_duration_min": None,
            "actual_duration_min": None, "reference_speed_kmh": None,
            "actual_speed_kmh": None, "delay_ratio": None
        }

    api_status = data.get("status", "UNKNOWN_ERROR")
    if api_status == "OK":
        element = data["rows"][0]["elements"][0]
        route_status = element.get("status", "UNKNOWN_ELEMENT_STATUS")
        
        if route_status == "OK":
            distance_m = element["distance"]["value"]
            ref_duration_s = element["duration"]["value"]
            
            traffic_elem = element.get("duration_in_traffic")
            if traffic_elem and "value" in traffic_elem:
                act_duration_s = traffic_elem["value"]
                traffic_data_status = "AVAILABLE"
            else:
                act_duration_s = None
                traffic_data_status = "UNAVAILABLE"
            
            distance_km = round(distance_m / 1000, 2)
            ref_duration_min = round(ref_duration_s / 60, 2)
            
            if act_duration_s is not None:
                act_duration_min = round(act_duration_s / 60, 2)
                delay_ratio = round(act_duration_min / ref_duration_min, 3) if ref_duration_min > 0 else 1.0
                ref_speed_kmh = round(distance_km / (ref_duration_min / 60), 2) if ref_duration_min > 0 else 0.0
                act_speed_kmh = round(distance_km / (act_duration_min / 60), 2) if act_duration_min > 0 else 0.0
            else:
                act_duration_min = None
                delay_ratio = None
                ref_speed_kmh = round(distance_km / (ref_duration_min / 60), 2) if ref_duration_min > 0 else 0.0
                act_speed_kmh = None

            return {
                "route_status": route_status,
                "traffic_data_status": traffic_data_status,
                "distance_km": distance_km,
                "reference_duration_min": ref_duration_min,
                "actual_duration_min": act_duration_min,
                "reference_speed_kmh": ref_speed_kmh,
                "actual_speed_kmh": act_speed_kmh,
                "delay_ratio": delay_ratio
            }
        return {
            "route_status": route_status, "traffic_data_status": "UNAVAILABLE",
            "distance_km": None, "reference_duration_min": None,
            "actual_duration_min": None, "reference_speed_kmh": None,
            "actual_speed_kmh": None, "delay_ratio": None
        }
    return {
        "route_status": api_status, "traffic_data_status": "UNAVAILABLE",
        "distance_km": None, "reference_duration_min": None,
        "actual_duration_min": None, "reference_speed_kmh": None,
        "actual_speed_kmh": None, "delay_ratio": None
    }

def get_existing_slots(csv_file):
    existing = set()
    if os.path.isfile(csv_file):
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp_ist", "")
                c_id = row.get("corridor_id", "")
                if ts and c_id:
                    hour_slot = ts[:13]
                    existing.add((str(c_id), hour_slot))
    return existing

def check_peak_hour_srinagar(dt):
    # Morning Peak: 8:30 AM - 10:30 AM | Evening Peak: 5:00 PM - 7:30 PM IST
    time_decimal = dt.hour + (dt.minute / 60.0)
    if (8.5 <= time_decimal <= 10.5) or (17.0 <= time_decimal <= 19.5):
        return 1
    return 0

def main():
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    timestamp_ist = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    current_hour_slot = timestamp_ist[:13]
    
    hour_of_day = now_ist.hour
    day_of_week = now_ist.strftime("%A")
    is_peak_hour = check_peak_hour_srinagar(now_ist)
    
    raw_exists = os.path.isfile(RAW_CSV_FILE)
    enriched_exists = os.path.isfile(ENRICHED_CSV_FILE)
    
    existing_slots = get_existing_slots(RAW_CSV_FILE)
    weather = get_weather()
    
    raw_rows = []
    enriched_rows = []
    
    for c in CORRIDORS:
        c_id = str(c["id"])
        
        if (c_id, current_hour_slot) in existing_slots:
            print(f"Skipping corridor {c_id}: Slot {current_hour_slot} already logged.")
            continue
            
        traffic = get_traffic_data(c["origin"], c["destination"])
        delay_ratio = traffic["delay_ratio"]
        congestion_index = round(delay_ratio - 1.0, 3) if delay_ratio is not None else None
        
        # Raw Dataset Row (17 Fields)
        raw_rows.append([
            timestamp_ist, c["id"], c["name"],
            traffic["route_status"], traffic["traffic_data_status"], weather["weather_api_status"],
            traffic["distance_km"], traffic["reference_duration_min"],
            traffic["actual_duration_min"], traffic["reference_speed_kmh"],
            traffic["actual_speed_kmh"], delay_ratio, congestion_index,
            weather["temp"], weather["humidity"], 
            weather["weather_main"], weather["rain_1h"]
        ])
        
        # Enriched Dataset Row (20 Fields including Temporal Features)
        enriched_rows.append([
            timestamp_ist, hour_of_day, day_of_week, is_peak_hour,
            c["id"], c["name"],
            traffic["route_status"], traffic["traffic_data_status"], weather["weather_api_status"],
            traffic["distance_km"], traffic["reference_duration_min"],
            traffic["actual_duration_min"], traffic["reference_speed_kmh"],
            traffic["actual_speed_kmh"], delay_ratio, congestion_index,
            weather["temp"], weather["humidity"], 
            weather["weather_main"], weather["rain_1h"]
        ])
        
    if raw_rows:
        with open(RAW_CSV_FILE, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not raw_exists:
                writer.writerow([
                    "timestamp_ist", "corridor_id", "corridor_name",
                    "route_status", "traffic_data_status", "weather_api_status",
                    "distance_km", "reference_duration_min", "actual_duration_min",
                    "reference_speed_kmh", "actual_speed_kmh",
                    "delay_ratio", "congestion_index",
                    "temperature_c", "humidity_pct", "weather_condition", "rain_1h_mm"
                ])
            writer.writerows(raw_rows)
            
    if enriched_rows:
        with open(ENRICHED_CSV_FILE, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not enriched_exists:
                writer.writerow([
                    "timestamp_ist", "hour_of_day", "day_of_week", "is_peak_hour",
                    "corridor_id", "corridor_name",
                    "route_status", "traffic_data_status", "weather_api_status",
                    "distance_km", "reference_duration_min", "actual_duration_min",
                    "reference_speed_kmh", "actual_speed_kmh",
                    "delay_ratio", "congestion_index",
                    "temperature_c", "humidity_pct", "weather_condition", "rain_1h_mm"
                ])
            writer.writerows(enriched_rows)
            for r in enriched_rows:
                print(f"Logged raw & enriched data for: {r[5]}")

if __name__ == "__main__":
    main()
