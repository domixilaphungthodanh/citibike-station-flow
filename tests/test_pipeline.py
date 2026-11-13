import csv
import io
from pathlib import Path
import sqlite3
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_all import FIELDS, load

AREA = [[[(0,0),(3,0),(3,3),(0,3),(0,0)]]]


class PipelineTest(unittest.TestCase):
    def test_counts(self):
        rides = [
            ('a','2025-01-06 08:50','2025-01-06 09:10','01','01'),
            ('a','2025-01-06 08:50','2025-01-06 09:10','01','01'),
            ('b','2025-01-06 08:55','2025-01-06 09:10','01',''),
            ('c','2024-12-31 23:59','2025-01-01 00:10','','01'),
            ('d','2025-01-31 23:59','2025-02-01 00:10','01','01'),
            ('e','2025-01-06 08:59','2025-01-06 08:10','01','01'),
            ('f','2025-01-06 08:10','2025-01-06 08:20','outside','01'),
        ]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for ride,start,end,a,b in rides:
            writer.writerow((ride,start,end,a,a,1,4 if a=='outside' else 1,b,b,1,1))
        path=io.BytesIO()
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('one.csv',stream.getvalue())
        con=sqlite3.connect(':memory:')
        quality=load(con,[path],AREA)
        self.assertEqual((quality['departures'],quality['arrivals']), (3,3))
        self.assertEqual((quality['duplicate_ride_id'],quality['invalid_times']), (1,1))
        self.assertEqual(con.execute("SELECT departures,arrivals,net FROM station_hour WHERE day='2025-01-06' AND hour=8").fetchone(), (2,1,1))
        self.assertEqual(con.execute("SELECT station_id,positive_days,positive_net FROM ranking").fetchone(), ('01',1,1))
        con.close()

    def test_invalid_archive(self):
        for file, message in [('one.txt','no data CSV'),('one.csv','missing columns')]:
            path=io.BytesIO()
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr(file,'ride_id\na\n')
            with self.assertRaisesRegex(ValueError,message):
                load(sqlite3.connect(':memory:'),[path],AREA)


if __name__=='__main__':
    unittest.main()
