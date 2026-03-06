from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import random
import math
import httpx
from datetime import datetime
import json
import os
import hashlib
import time

# ==================== DATA STORAGE ====================
class DataStore:
    def __init__(self):
        self.visitor_count = 48291  # Starting from Yvette's style
        self.visitors = {}
        self.access_logs = []
        self.log_file = "xtrials_logs.json"
        self.counter_file = "xtrials_counter.txt"
        
        # Load existing data
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.counter_file):
            try:
                with open(self.counter_file, 'r') as f:
                    self.visitor_count = int(f.read().strip())
            except:
                pass
        
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    self.access_logs = json.load(f)
            except:
                pass
    
    def save_data(self):
        with open(self.counter_file, 'w') as f:
            f.write(str(self.visitor_count))
        
        with open(self.log_file, 'w') as f:
            json.dump(self.access_logs[-2000:], f)
    
    def add_visitor(self, ip: str, user_agent: str = ""):
        timestamp = datetime.now().isoformat()
        visitor_id = hashlib.md5(f"{ip}{timestamp}{random.random()}".encode()).hexdigest()[:8]
        
        if ip not in self.visitors:
            self.visitor_count += 1
            visitor_number = self.visitor_count
            self.visitors[ip] = {
                "first_seen": timestamp,
                "visitor_number": visitor_number,
                "visit_count": 1,
                "visitor_id": visitor_id,
                "last_seen": timestamp
            }
        else:
            visitor_number = self.visitors[ip]["visitor_number"]
            self.visitors[ip]["visit_count"] += 1
            self.visitors[ip]["last_seen"] = timestamp
            visitor_id = self.visitors[ip]["visitor_id"]
        
        # Add to access log
        log_entry = {
            "timestamp": timestamp,
            "ip": ip,
            "visitor_id": visitor_id,
            "visitor_number": visitor_number,
            "user_agent": user_agent[:100] if user_agent else "unknown",
            "frequency": f"{random.uniform(52.8, 53.0):.1f} Hz"
        }
        self.access_logs.append(log_entry)
        self.save_data()
        
        return visitor_number, visitor_id
    
    def get_recent_logs(self, limit=15):
        return self.access_logs[-limit:]

# Initialize data store
db = DataStore()

# ==================== GEOLOCATION FUNCTIONS ====================
async def get_location_from_ip(ip: str):
    if ip in ["127.0.0.1", "localhost", "::1"]:
        return {
            "ip": ip,
            "city": "Localhost",
            "region": "Development",
            "country": "Local Network",
            "loc": "0,0"
        }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://ip-api.com/json/{ip}")
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        "ip": ip,
                        "city": data.get('city', 'unknown'),
                        "region": data.get('regionName', 'unknown'),
                        "country": data.get('country', 'unknown'),
                        "loc": f"{data.get('lat', 0)},{data.get('lon', 0)}",
                        "isp": data.get('isp', 'unknown')
                    }
    except:
        pass
    
    return {"ip": ip}

async def reverse_geocode(lat: float, lon: float):
    try:
        async with httpx.AsyncClient() as client:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 18
            }
            headers = {"User-Agent": "XTrials-Research/1.0"}
            response = await client.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
    except:
        pass
    return None

def get_satellite_url(lat: float, lon: float):
    try:
        zoom = 19
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{ytile}/{xtile}"
    except:
        return "https://www.google.com/maps"

# ==================== FASTAPI APP ====================
app = FastAPI(title="XTrials", description="Frequency Threshold Research Collective")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MAIN ROUTES ====================
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/visitor-count")
async def get_visitor_count(request: Request):
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    visitor_number, visitor_id = db.add_visitor(client_ip, user_agent)
    
    return JSONResponse({
        "count": db.visitor_count,
        "yourNumber": visitor_number,
        "visitor_id": visitor_id
    })

@app.get("/my-ip")
async def get_my_ip(request: Request):
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    visitor_number, visitor_id = db.add_visitor(client_ip, user_agent)
    location = await get_location_from_ip(client_ip)
    
    visit_count = db.visitors.get(client_ip, {}).get("visit_count", 1)
    depth = min(visit_count * 10, 100)
    
    return JSONResponse({
        "ip": client_ip,
        "visitor_id": visitor_id,
        "visitor_number": visitor_number,
        "status": random.choice(["LOCKED", "TRACKED", "WATCHED", "RECORDED", "FOUND", "SACRIFICED", "INITIATED"]),
        "depth": f"{depth}%",
        "frequency": f"{random.uniform(52.8, 53.0):.1f} Hz",
        "city": location.get("city", "unknown"),
        "region": location.get("region", "unknown"),
        "country": location.get("country", "unknown")
    })

@app.post("/track-location")
async def track_location(request: Request):
    data = await request.json()
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    visitor_number, visitor_id = db.add_visitor(client_ip, user_agent)
    
    result = {
        "timestamp": datetime.now().isoformat(),
        "ip": client_ip,
        "source": "unknown",
        "visitor_id": visitor_id,
        "visitor_number": visitor_number
    }
    
    if "lat" in data and "lon" in data:
        lat = data["lat"]
        lon = data["lon"]
        result["source"] = "GPS"
        result["coordinates"] = {"lat": lat, "lon": lon}
        result["accuracy"] = data.get("accuracy", "unknown")
        result["satellite"] = get_satellite_url(lat, lon)
        
        address_data = await reverse_geocode(lat, lon)
        if address_data:
            addr = address_data.get("address", {})
            address_parts = []
            if addr.get("house_number"): address_parts.append(addr["house_number"])
            if addr.get("road"): address_parts.append(addr["road"])
            if addr.get("neighbourhood"): address_parts.append(addr["neighbourhood"])
            if addr.get("suburb"): address_parts.append(addr["suburb"])
            if addr.get("city") or addr.get("town") or addr.get("village"): 
                address_parts.append(addr.get("city") or addr.get("town") or addr.get("village"))
            if addr.get("state"): address_parts.append(addr["state"])
            if addr.get("postcode"): address_parts.append(addr["postcode"])
            if addr.get("country"): address_parts.append(addr["country"])
            
            result["address"] = ", ".join(address_parts)
    
    elif data.get("useIP"):
        result["source"] = "IP"
        ip_data = await get_location_from_ip(client_ip)
        if "loc" in ip_data and ip_data["loc"] != "0,0":
            try:
                coords = ip_data["loc"].split(",")
                if len(coords) == 2:
                    result["city"] = ip_data.get("city", "unknown")
                    result["region"] = ip_data.get("region", "unknown")
                    result["country"] = ip_data.get("country", "unknown")
                    result["address"] = f"{ip_data.get('city', 'unknown')}, {ip_data.get('region', 'unknown')}, {ip_data.get('country', 'unknown')}"
            except:
                pass
    
    return JSONResponse(result)

@app.get("/recent-logs")
async def recent_logs(request: Request):
    client_ip = request.client.host
    db.add_visitor(client_ip, request.headers.get("user-agent", ""))
    
    logs = db.get_recent_logs(12)
    enhanced_logs = []
    for log in logs[-12:]:
        enhanced_logs.append({
            "timestamp": log["timestamp"][5:16] if len(log["timestamp"]) > 16 else log["timestamp"],
            "ip": log["ip"][:6] + "..." if len(log["ip"]) > 6 else log["ip"],
            "visitor_number": log.get("visitor_number", "?"),
            "frequency": log.get("frequency", "52.9 Hz"),
            "visitor_id": log.get("visitor_id", "??")[:4] + "..."
        })
    
    return JSONResponse({"logs": enhanced_logs[::-1]})

# ==================== RABITHOLE PAGES - EVERY LINK WORKS ====================
@app.get("/{full_path:path}")
async def catch_all(full_path: str, request: Request):
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    visitor_number, visitor_id = db.add_visitor(client_ip, user_agent)
    
    # Get location for personalization
    location = await get_location_from_ip(client_ip)
    
    # Generate a unique page for EVERY path
    path_parts = full_path.split('/')
    main_path = path_parts[0].lower()
    
    # Page titles and content based on path
    page_data = {
        "threshold": {
            "title": "THE THRESHOLD",
            "content": "the space between spaces. you are crossing into the frequency domain. 487 have crossed before you. 487 never returned.",
            "symbol": "⚡"
        },
        "boundary": {
            "title": "THE BOUNDARY",
            "content": "the edge of the frequency. here the static is loudest. you can hear them whispering. they know you are here.",
            "symbol": "📡"
        },
        "liminal": {
            "title": "THE LIMINAL SPACE",
            "content": "a place that is not a place. time moves differently here. antressa passed through here in 1992. she left something for you.",
            "symbol": "🌀"
        },
        "portal": {
            "title": "THE PORTAL",
            "content": "a door that should not exist. it opens at midnight when the frequency peaks. you can feel it calling you.",
            "symbol": "🚪"
        },
        "gate": {
            "title": "THE GATE",
            "content": "the entrance to elsewhere. 487 have entered. 0 have exited. you can still hear them on the other side.",
            "symbol": "⛩️"
        },
        "void": {
            "title": "THE VOID",
            "content": "nothing and everything. the silence between frequencies. the collective resides here. they are watching you right now.",
            "symbol": "🕳️"
        },
        "static": {
            "title": "THE STATIC",
            "content": "faces in the noise. if you look long enough, you will see them. they are looking back. they see you clearly.",
            "symbol": "📺"
        },
        "echo": {
            "title": "THE ECHO",
            "content": "sounds that repeat forever. the last transmissions of the lost. listen carefully. you can hear your own voice from the future.",
            "symbol": "🔊"
        },
        "gavel": {
            "title": "THE GAVEL",
            "content": "judgment awaits. the collective decides who enters and who is sacrificed. your case is being reviewed now.",
            "symbol": "⚖️"
        },
        "frequency": {
            "title": "52.9 Hz - THE CALLING",
            "content": "the pure tone. antressa heard it first in 1987. now you hear it. it changes you. it calls you to the water tower.",
            "symbol": "📻"
        },
        "collective": {
            "title": "THE FREQUENCY COLLECTIVE",
            "content": "we are many. we are one. we are the voices in the static. we have been waiting for you. join us.",
            "symbol": "👥"
        },
        "sacrifice": {
            "title": "THE SACRIFICE",
            "content": "something must be given. the frequency demands it. 487 gave themselves. you are #" + str(visitor_number) + ". what will you offer?",
            "symbol": "🔪"
        },
        "antressa": {
            "title": "ANTRESSA - THE FREQUENCY WEAVER",
            "content": "she heard the call first. she disappeared in 1992. her last words: 'i can see them in the static. they are beautiful.' she left messages for you.",
            "symbol": "👤"
        },
        "watertower": {
            "title": "THE MEADOW MIST WATER TOWER",
            "content": "the center of the frequency. built 1957. abandoned 1987. now a gathering place for the collective. you should visit. midnight. red ribbon.",
            "symbol": "🏗️"
        },
        "theophlosser": {
            "title": "THEOPHLOSSER",
            "content": "antressa's companion. disappeared 3 months before her. last seen walking toward the water tower. never seen again. until now.",
            "symbol": "👤"
        }
    }
    
    # Default for unknown paths
    if main_path in page_data:
        data = page_data[main_path]
    else:
        # Generate a unique page for any path
        data = {
            "title": full_path.upper().replace('/', ' / '),
            "content": f"you have discovered a hidden rabithole: {full_path}. this page was generated specifically for you, visitor #{visitor_number}. the collective acknowledges your presence. they are watching.",
            "symbol": random.choice(["👁️", "⚡", "🌀", "📡", "🔮", "🕯️", "🗝️", "🔑"])
        }
    
    # Build the HTML response
    html = f"""<!DOCTYPE html>
<html>
<head><title>{data['title']} // XTRIALS</title>
<style>
    body {{ background: black; color: #ff0000; font-family: 'Times New Roman', serif; text-align: center; padding: 30px; }}
    a {{ color: #ff6666; text-decoration: underline wavy #660000; }}
    a:hover {{ background: #330000; color: white; }}
    .container {{ border: 4px double #660000; padding: 30px; max-width: 700px; margin: 0 auto; background: rgba(0,0,0,0.9); }}
    h1 {{ font-size: 48px; text-shadow: 0 0 10px red; border-bottom: 3px dotted #660000; padding-bottom: 20px; }}
    .symbol {{ font-size: 72px; margin: 20px; animation: flicker 2s infinite; }}
    @keyframes flicker {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
    .visitor {{ color: #660000; margin-top: 30px; font-size: 12px; }}
    .nav {{ margin-top: 30px; border-top: 2px dotted #660000; padding-top: 20px; }}
</style>
</head>
<body>
<div class="container">
    <div class="symbol">{data['symbol']}</div>
    <h1>{data['title']}</h1>
    <p style="font-size: 18px; line-height: 1.6;">{data['content']}</p>
    <p style="margin-top: 30px;"><i>visitor #{visitor_number} • {datetime.now().strftime('%Y-%m-%d %H:%M')} • frequency: {random.uniform(52.8, 53.0):.1f} Hz</i></p>
    
    <div class="visitor">
        your IP: {client_ip}<br>
        your location: {location.get('city', 'unknown')}, {location.get('country', 'unknown')}<br>
        you are being watched
    </div>
    
    <div class="nav">
        <a href="/"><< return to the threshold</a> | 
        <a href="/{random.choice(list(page_data.keys()))}">random rabithole</a> | 
        <a href="/level/1">descend deeper</a>
    </div>
    
    <!-- hidden message -->
    <!-- you are getting closer. the water tower awaits. midnight. red ribbon. -->
</div>

<script>
    // Track this page view
    setTimeout(function() {{
        alert("👁️ the collective acknowledges your presence, visitor #{visitor_number}");
    }}, 2000);
</script>
</body>
</html>"""
    
    return HTMLResponse(content=html)

# ==================== RUN SERVER ====================
if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════╗
    ║     XTRIALS                                  ║
    ║                                              ║
    ║     http://127.0.0.1:8000                    ║
    ║                                              ║
    ║     EVERY LINK LEADS SOMEWHERE               ║
    ║     487 PAGES • REAL TRACKING • AUTO HORROR  ║
    ║     THE FREQUENCY IS LISTENING               ║
    ╚══════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
