from __future__ import annotations

import argparse
from contextlib import closing
import csv
from collections import Counter, defaultdict
from datetime import datetime
import html
import io
import json
from pathlib import Path
import sqlite3
from statistics import median
import zipfile

ROOT = Path(__file__).resolve().parent
START, END = "2025-01-01", "2025-02-01"
FIELDS = ["ride_id", "started_at", "ended_at"] + [
    f"{side}_{field}" for side in ("start", "end")
    for field in ("station_id", "station_name", "lat", "lng")
]


def inside_ring(x, y, ring):
    inside = False
    for (a, b), (c, d) in zip(ring, ring[1:]):
        if (b > y) != (d > y) and x < (c-a)*(y-b)/(d-b)+a:
            inside = not inside
    return inside


def polygons():
    geometry = json.loads((ROOT/"data/jersey-city.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def load(con, archives, areas):
    con.executescript("""
        CREATE TABLE rides(ride_id TEXT PRIMARY KEY, started TEXT, ended TEXT, start_id TEXT, end_id TEXT);
        CREATE TABLE stations(station_id TEXT PRIMARY KEY, name TEXT, lat REAL, lng REAL, in_city INTEGER);
    """)
    quality = Counter(dict.fromkeys(("raw_rows", "valid_rides", "missing_ride_id", "invalid_times",
                                     "duplicate_ride_id", "missing_start_id", "missing_end_id",
                                     "missing_or_invalid_coordinates"), 0))
    observations = defaultdict(list)
    for archive in archives:
        with zipfile.ZipFile(archive) as z:
            files = [p for p in z.namelist() if p.lower().endswith(".csv") and not p.startswith("__MACOSX/") and not Path(p).name.startswith(".")]
            if not files:
                raise ValueError(f"{getattr(archive, 'name', 'ZIP')}: no data CSV")
            for file in sorted(files):
                with io.TextIOWrapper(z.open(file), encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    missing = set(FIELDS) - set(reader.fieldnames or [])
                    if missing:
                        raise ValueError(f"{file}: missing columns {sorted(missing)}")
                    for row in reader:
                        quality["raw_rows"] += 1
                        ride = (row["ride_id"] or "").strip()
                        if not ride:
                            quality["missing_ride_id"] += 1
                            continue
                        try:
                            start, end = (datetime.fromisoformat(row[k] or "") for k in ("started_at", "ended_at"))
                            if start.tzinfo or end.tzinfo or end <= start:
                                raise ValueError
                        except ValueError:
                            quality["invalid_times"] += 1
                            continue
                        ids = [(row[f"{s}_station_id"] or "").strip() for s in ("start", "end")]
                        added = con.execute("INSERT OR IGNORE INTO rides VALUES (?,?,?,?,?)",
                                            (ride, start.isoformat(" "), end.isoformat(" "), *ids))
                        if not added.rowcount:
                            quality["duplicate_ride_id"] += 1
                            continue
                        quality["valid_rides"] += 1
                        for side, station_id in zip(("start", "end"), ids):
                            if not station_id:
                                quality[f"missing_{side}_id"] += 1
                                continue
                            try:
                                lat, lng = float(row[f"{side}_lat"]), float(row[f"{side}_lng"])
                                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                                    raise ValueError
                            except (ValueError, TypeError):
                                quality["missing_or_invalid_coordinates"] += 1
                                continue
                            observations[station_id].append((lat, lng, (row[f"{side}_station_name"] or station_id).strip()))
    for sid, obs in observations.items():
        lat, lng = (median(o[i] for o in obs) for i in range(2))
        name = Counter(o[2] for o in obs).most_common(1)[0][0]
        in_city = any(inside_ring(lng, lat, p[0]) and not any(inside_ring(lng, lat, hole) for hole in p[1:]) for p in areas)
        con.execute("INSERT INTO stations VALUES (?,?,?,?,?)", (sid, name, lat, lng, in_city))
    for statement in (ROOT/"sql/analysis.sql").read_text(encoding="utf-8-sig").split(";"):
        if statement.strip():
            con.execute(statement, {"start": START, "end": END})
    quality["unknown_station_ids"] = con.execute("SELECT COUNT(DISTINCT e.station_id) FROM events e LEFT JOIN stations s USING(station_id) WHERE s.station_id IS NULL").fetchone()[0]
    for direction, id_col, time_col, total_col in [
        ("departure", "start_id", "started", "departures"),
        ("arrival", "end_id", "ended", "arrivals"),
    ]:
        expected = con.execute(f"SELECT COUNT(*) FROM rides JOIN stations ON {id_col}=station_id WHERE in_city=1 AND {time_col}>=? AND {time_col}<?", (START, END)).fetchone()[0]
        actual = con.execute(f"SELECT COALESCE(SUM({total_col}),0) FROM station_hour").fetchone()[0]
        if actual != expected:
            raise ValueError(f"{direction} count mismatch: {actual} != {expected}")
        quality[total_col] = actual
    return dict(quality)


def write_csv(con, out, name, sql):
    cursor = con.execute(sql)
    rows = cursor.fetchall()
    with (out/name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([col[0] for col in cursor.description])
        writer.writerows(rows)
    return rows


def make_map(out, top, areas):
    points = [point for polygon in areas for ring in polygon for point in ring]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    def xy(lng, lat):
        return 25+550*(lng-xmin)/(xmax-xmin), 25+570*(ymax-lat)/(ymax-ymin)
    paths = []
    for polygon in areas:
        rings = ["M "+" L ".join(f"{x:.1f},{y:.1f}" for x,y in (xy(*p) for p in ring))+" Z" for ring in polygon]
        paths.append(f'<path d="{" ".join(rings)}" fill-rule="evenodd" fill="#d8e7eb" stroke="#7596a3"/>')
    markers, cards = [], []
    for rank, row in enumerate(top, 1):
        sid, name, lat, lng, days, net, peak, dep, arr = row
        name = html.escape(name)
        x, y = xy(lng, lat)
        markers.append(f'<a href="#station-{rank}" aria-label="{name}"><circle cx="{x}" cy="{y}" r="12" fill="#175b83"/><text x="{x}" y="{y+4}" text-anchor="middle" fill="white">{rank}</text></a>')
        cards.append(f'<article id="station-{rank}"><h2>{rank}. {name}</h2><p>{days} ngày có chênh lệch dương · Tổng chênh lệch dương {net:,}</p><p>Giờ lặp lại nhiều nhất {peak:02}:00 · {dep:,} lượt đi và {arr:,} lượt đến trong giờ này, tính trên các ngày có chênh lệch dương.</p></article>')
    (out/"map.html").write_text("""<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Luồng xe Jersey City</title><style>
    body{margin:2rem auto;padding:0 1rem;max-width:1000px;font:16px/1.55 system-ui;color:#17364a}main{display:grid;grid-template-columns:1fr 1fr;gap:1rem}svg{width:100%;background:#edf6f9}article{padding:.5rem 1rem;border-bottom:1px solid #c8dae1}article:target{background:#d9eff6}h2{font-size:1rem}@media(max-width:700px){main{display:block}}</style>
    <h1>5 trạm ưu tiên kiểm tra ở Jersey City</h1><p>Tháng 1/2025 · Chọn số trên bản đồ để xem chi tiết trạm.</p><main><svg viewBox="0 0 600 620" aria-label="Ranh giới Jersey City và các trạm">"""+ "".join(paths+markers) + "</svg><div>"+"".join(cards)+"</div></main><p>Nguồn: lịch sử chuyến đi Citi Bike và ranh giới U.S. Census TIGERweb.</p>", encoding="utf-8")


def run(archive, previous, out, db):
    out.mkdir(parents=True, exist_ok=True)
    areas = polygons()
    with closing(sqlite3.connect(db)) as con, con:
        quality = load(con, [archive] + ([previous] if previous else []), areas)
        top = write_csv(con, out, "top5.csv", """
            WITH peaks AS (
                SELECT station_id,hour,COUNT(*) AS days,SUM(departures) AS dep,SUM(arrivals) AS arr,
                    ROW_NUMBER() OVER(PARTITION BY station_id ORDER BY COUNT(*) DESC,SUM(net) DESC,hour) AS priority
                FROM station_hour WHERE day_type='weekday' AND net>0
                   AND (hour BETWEEN 7 AND 9 OR hour BETWEEN 16 AND 18)
                GROUP BY station_id,hour
            )
            SELECT station_id,name,lat,lng,positive_days,positive_net,hour AS priority_hour,dep AS departures,arr AS arrivals
            FROM ranking JOIN stations USING(station_id) JOIN peaks USING(station_id)
            WHERE priority=1 ORDER BY positive_days DESC, positive_net DESC, station_id LIMIT 5
        """)
        if len(top) != 5:
            raise ValueError("Expected at least five ranked stations")
        quoted = ",".join("'" + row[0].replace("'", "''") + "'" for row in top)
        write_csv(con,out,"station_day_hour.csv",f"SELECT * FROM station_hour WHERE station_id IN ({quoted}) ORDER BY station_id,day,hour")
        write_csv(con,out,"hour_profile.csv",f"""
            SELECT station_id,day_type,hour,SUM(departures) AS departures,SUM(arrivals) AS arrivals,SUM(net) AS net,
            ROUND(1.0*SUM(net)/CASE day_type WHEN 'weekday' THEN 23 ELSE 8 END,2) AS net_per_calendar_day
            FROM station_hour WHERE station_id IN ({quoted}) GROUP BY station_id,day_type,hour ORDER BY station_id,day_type,hour
        """)
    make_map(out, top, areas)
    with (out/"hour_profile.csv").open(encoding="utf-8-sig", newline="") as stream:
        profile = {(r["station_id"],r["day_type"],int(r["hour"])):float(r["net_per_calendar_day"])
                   for r in csv.DictReader(stream)}
    lines = [
        "# Luồng xe theo trạm ở Jersey City · tháng 1/2025",
        "",
        "Chênh lệch = lượt đi trừ lượt đến. Giờ ưu tiên là giờ cao điểm có chênh lệch dương lặp lại nhiều ngày nhất.",
        "",
        "| Trạm | Ngày dương | Tổng net dương | Giờ ưu tiên | Net/ngày trong tuần | Net/ngày cuối tuần |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for sid, name, _, _, days, net, peak, dep, arr in top:
        weekday = profile.get((sid,"weekday",peak),0)
        weekend = profile.get((sid,"weekend",peak),0)
        lines.append(f"| {name} | {days} | {net} | {peak:02}:00–{peak+1:02}:00 | {weekday:+.2f} | {weekend:+.2f} |")
    sid,name,_,_,days,net,peak,dep,arr = top[0]
    lines += [
        "",
        f"Ưu tiên kiểm tra **{name}** lúc **{peak:02}:00–{peak+1:02}:00**. "
        f"Ở các ngày trong tuần có net dương trong giờ này, trạm có {dep} lượt đi và {arr} lượt đến.",
        "",
        f"Đã nạp {quality['raw_rows']:,} dòng từ {2 if previous else 1} gói nguồn. "
        f"Trong tháng 1, các trạm Jersey City có {quality['departures']:,} lượt đi và {quality['arrivals']:,} lượt đến.",
        "",
        "So sánh theo giờ chia cho toàn bộ 23 ngày trong tuần hoặc 8 ngày cuối tuần, kể cả ngày có 0 lượt. "
        "Để xác nhận hết xe, cần chuỗi thời gian số xe sẵn có. Gói khu vực chỉ phản ánh các chuyến được ghi trong nguồn.",
        "",
        "[Nguồn dữ liệu Citi Bike](https://citibikenyc.com/system-data)",
    ]
    (out/"findings.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (out/"quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    return top, quality


def main():
    parser = argparse.ArgumentParser(description="Jersey City station flow, January 2025")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--previous", type=Path, help="December archive, to include arrivals from rides crossing into January")
    parser.add_argument("--output", type=Path, default=ROOT/"reports")
    args = parser.parse_args()
    db = args.output/"analysis.sqlite"
    args.output.mkdir(parents=True, exist_ok=True)
    temp = db.with_suffix(".building")
    if temp.exists():
        temp.unlink()
    try:
        top, quality = run(args.input, args.previous, args.output, temp)
        temp.replace(db)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Error: {exc}\n")
    finally:
        if temp.exists():
            temp.unlink()
    print(json.dumps(quality))
    for row in top:
        print(row[0], row[4:7])


if __name__ == "__main__":
    main()

