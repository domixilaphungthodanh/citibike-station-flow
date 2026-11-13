CREATE VIEW events AS
SELECT ride_id, start_id AS station_id, started AS ts, 'departure' AS direction FROM rides WHERE start_id <> ''
UNION ALL
SELECT ride_id, end_id, ended, 'arrival' FROM rides WHERE end_id <> '';

CREATE TABLE station_hour AS
SELECT station_id, date(ts) AS day, CAST(strftime('%H',ts) AS INTEGER) AS hour,
       CASE WHEN strftime('%w',ts) IN ('0','6') THEN 'weekend' ELSE 'weekday' END AS day_type,
       SUM(direction='departure') AS departures, SUM(direction='arrival') AS arrivals,
       SUM(CASE direction WHEN 'departure' THEN 1 ELSE -1 END) AS net
FROM events JOIN stations USING(station_id)
WHERE in_city=1 AND ts >= :start AND ts < :end
GROUP BY station_id, day, hour;

CREATE VIEW ranking AS
SELECT station_id, COUNT(DISTINCT day) AS positive_days, SUM(net) AS positive_net
FROM station_hour
WHERE day_type='weekday' AND (hour BETWEEN 7 AND 9 OR hour BETWEEN 16 AND 18) AND net>0
GROUP BY station_id
ORDER BY positive_days DESC, positive_net DESC, station_id;
