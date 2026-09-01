import os
import csv
import time
from datetime import datetime, timezone, timedelta
import requests

# Retrieve API keys from GitHub Secrets
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
OPENWEATHER_KEY = os.environ.get('OPENWEATHER_API_KEY')

# Standardized Srinagar Arterial Corridors (Fixed Lat/Lng Highway Junctions)
CORRIDORS = [
    {
        "id": 1,
        "name": "Lal Chowk to Hyderpora",
        "origin_lat": 34.0728, "origin_lng": 74.8097,  # Lal Chowk (Ghanta Ghar Junction)
        "dest_lat": 34.0360, "dest_lng": 74.7876       # Hyderpora Bypass Flyover Junction
    },
    {
        "id": 2,
        "name": "Dalgate to Pantha Chowk",
        "origin_lat": 34.0740, "origin_lng": 74.8285,  # Dalgate Bridge Junction
        "dest_lat": 34.0298, "dest_lng": 74.8645       # Pantha Chowk Expressway Junction
    },
    {
        "id": 3,
        "name": "Jahangir Chowk to Parimpora",
        "origin_lat": 34.0718, "origin_lng": 74.8023,  # Jahangir Chowk Flyover Junction
        "dest_lat": 34.0882, "dest_lng": 74.7554       # Parimpora Fruit Mandi Bypass Junction
    }
]

RAW_DIST_CSV = "raw_distance_api.csv"
ENRICHED_DIST_CSV = "enriched_distance_api.csv"
RAW_ROUTES_CSV = "raw_routes_api.csv"
ENRICHED_ROUTES_CSV = "enriched_routes_api.csv"

def fetch_with_retry(url, method="GET", json_payload=None, headers=None, max_attempts=3, timeout=15):
    """Executes HTTP GET/POST requests with retry logic and status logging."""
    for attempt in range(1, max_attempts + 1):
        try:
            if method == "POST":
                res = requests.post(url, json=json_payload, headers=headers, timeout=timeout)
            else:
                res = requests.get(url, headers=headers, timeout=timeout)
            
            if res.status_code != 200:
                print(f"API HTTP Error ({res.status_code}) on attempt {attempt}: {res.text}")
                if attempt == max_attempts:
                    return None, f"HTTP_{res.status_code}"
                time.sleep(2)
                continue
                
            return res.json(), "OK"
        except requests.exceptions.RequestException as e:
            print(f"Network Exception on attempt {attempt}: {e}")
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

def get_distance_matrix_data(o_lat, o_lng, d_lat, d_lng):
    origin_str = f"{o_lat},{o_lng}"
    dest_str = f"{d_lat},{d_lng}"
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_str}&destinations={dest_str}&departure_time=now&key={GOOGLE_MAPS_KEY}"
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

def get_routes_api_data(o_lat, o_lng, d_lat, d_lng):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters"
    }
    payload = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": o_lat,
                    "longitude": o_lng
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": d_lat,
                    "longitude": d_lng
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
    }
    
    data, http_status = fetch_with_retry(url, method="POST", json_payload=payload, headers=headers)
    
    if not data or "routes" not in data or len(data["routes"]) == 0:
        return {
            "route_status": http_status if not data else "ZERO_RESULTS",
            "traffic_data_status": "UNAVAILABLE",
            "distance_km": None, "reference_duration_min": None,
            "actual_duration_min": None, "reference_speed_kmh": None,
            "actual_speed_kmh": None, "delay_ratio": None
        }

    try:
        route = data["routes"][0]
        distance_m = route.get("distanceMeters", 0)
        ref_duration_s = float(route.get("staticDuration", "0s").replace("s", ""))
        act_duration_s = float(route.get("duration", "0s").replace("s", ""))
        
        distance_km = round(distance_m / 1000, 2)
        ref_duration_min = round(ref_duration_s / 60, 2)
        act_duration_min = round(act_duration_s / 60, 2)
        
        delay_ratio = round(act_duration_min / ref_duration_min, 3) if ref_duration_min > 0 else 1.0
        ref_speed_kmh = round(distance_km / (ref_duration_min / 60), 2) if ref_duration_min > 0 else 0.0
        act_speed_kmh = round(distance_km / (act_duration_min / 60), 2) if act_duration_min > 0 else 0.0

        return {
            "route_status": "OK",
            "traffic_data_status": "AVAILABLE",
            "distance_km": distance_km,
            "reference_duration_min": ref_duration_min,
            "actual_duration_min": act_duration_min,
            "reference_speed_kmh": ref_speed_kmh,
            "actual_speed_kmh": act_speed_kmh,
            "delay_ratio": delay_ratio
        }
    except Exception as e:
        return {
            "route_status": f"EXCEPTION_{type(e).__name__}",
            "traffic_data_status": "UNAVAILABLE",
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
    time_decimal = dt.hour + (dt.minute / 60.0)
    if (8.5 <= time_decimal <= 10.5) or (17.0 <= time_decimal <= 19.5):
        return 1
    return 0

def write_data(raw_csv, enriched_csv, raw_rows, enriched_rows):
    raw_exists = os.path.isfile(raw_csv)
    enriched_exists = os.path.isfile(enriched_csv)
    
    if raw_rows:
        with open(raw_csv, mode="a", newline="", encoding="utf-8") as file:
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
        with open(enriched_csv, mode="a", newline="", encoding="utf-8") as file:
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

def main():
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    timestamp_ist = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    current_hour_slot = timestamp_ist[:13]
    
    hour_of_day = now_ist.hour
    day_of_week = now_ist.strftime("%A")
    is_peak_hour = check_peak_hour_srinagar(now_ist)
    
    existing_dist_slots = get_existing_slots(RAW_DIST_CSV)
    existing_routes_slots = get_existing_slots(RAW_ROUTES_CSV)
    weather = get_weather()
    
    dist_raw_rows = []
    dist_enriched_rows = []
    routes_raw_rows = []
    routes_enriched_rows = []
    
    for c in CORRIDORS:
        c_id = str(c["id"])
        
        # 1. Process Distance Matrix API (Lat/Lng)
        if (c_id, current_hour_slot) not in existing_dist_slots:
            traffic_dist = get_distance_matrix_data(c["origin_lat"], c["origin_lng"], c["dest_lat"], c["dest_lng"])
            delay_ratio = traffic_dist["delay_ratio"]
            ci = round(delay_ratio - 1.0, 3) if delay_ratio is not None else None
            
            raw_row = [
                timestamp_ist, c["id"], c["name"],
                traffic_dist["route_status"], traffic_dist["traffic_data_status"], weather["weather_api_status"],
                traffic_dist["distance_km"], traffic_dist["reference_duration_min"],
                traffic_dist["actual_duration_min"], traffic_dist["reference_speed_kmh"],
                traffic_dist["actual_speed_kmh"], delay_ratio, ci,
                weather["temp"], weather["humidity"], weather["weather_main"], weather["rain_1h"]
            ]
            enriched_row = [timestamp_ist, hour_of_day, day_of_week, is_peak_hour] + raw_row[1:]
            dist_raw_rows.append(raw_row)
            dist_enriched_rows.append(enriched_row)

        # 2. Process Routes API v2 (Lat/Lng)
        if (c_id, current_hour_slot) not in existing_routes_slots:
            traffic_routes = get_routes_api_data(c["origin_lat"], c["origin_lng"], c["dest_lat"], c["dest_lng"])
            delay_ratio = traffic_routes["delay_ratio"]
            ci = round(delay_ratio - 1.0, 3) if delay_ratio is not None else None
            
            raw_row = [
                timestamp_ist, c["id"], c["name"],
                traffic_routes["route_status"], traffic_routes["traffic_data_status"], weather["weather_api_status"],
                traffic_routes["distance_km"], traffic_routes["reference_duration_min"],
                traffic_routes["actual_duration_min"], traffic_routes["reference_speed_kmh"],
                traffic_routes["actual_speed_kmh"], delay_ratio, ci,
                weather["temp"], weather["humidity"], weather["weather_main"], weather["rain_1h"]
            ]
            enriched_row = [timestamp_ist, hour_of_day, day_of_week, is_peak_hour] + raw_row[1:]
            routes_raw_rows.append(raw_row)
            routes_enriched_rows.append(enriched_row)
            
    write_data(RAW_DIST_CSV, ENRICHED_DIST_CSV, dist_raw_rows, dist_enriched_rows)
    write_data(RAW_ROUTES_CSV, ENRICHED_ROUTES_CSV, routes_raw_rows, routes_enriched_rows)
    print(f"Logged dual API data for slot: {current_hour_slot}")

if __name__ == "__main__":
    main()
