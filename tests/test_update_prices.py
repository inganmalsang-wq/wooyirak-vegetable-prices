import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import datetime as dt
from update_prices import classify, unit_kg, transform_rows, select_target_dates

class CollectorTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(unit_kg('10kg 상자'),10)
        self.assertEqual(unit_kg('500g 망'),0.5)
        self.assertIsNone(unit_kg('1박스'))
        self.assertIsNone(unit_kg('1단'))
    def test_classification(self):
        self.assertEqual(classify('고추','청양'), '청양고추')
        self.assertEqual(classify('마늘','깐마늘'),'깐마늘')
        self.assertEqual(classify('오이','오이'),'오이')
    def test_group_median(self):
        raw=[]
        for p in (10000,20000,90000):
            raw.append({'MIDNAME':'고추','SMALLNAME':'청양','SALEDATE':'20261012','WHSALCD':'110001','STD':'10kg 상자','COST':str(p)})
        rows=transform_rows(raw)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['price_kg'],2000)
        self.assertEqual(rows[0]['trade_count'],3)
    def test_backfill_refreshes_recent_and_fills_oldest_missing_dates(self):
        today=dt.date(2026,10,12)
        existing=[{'date':'2026-07-15'},{'date':'2026-10-10'}]
        targets=select_target_dates(existing,[],today,refresh_days=2,history_days=90,backfill_batch=2)
        self.assertEqual(targets,[today,today-dt.timedelta(days=1),dt.date(2026,7,16),dt.date(2026,7,17)])
    def test_checked_empty_date_is_not_retried_as_backfill(self):
        today=dt.date(2026,10,12)
        targets=select_target_dates([],['2026-07-15'],today,2,90,1)
        self.assertEqual(targets[-1],dt.date(2026,7,16))

if __name__=='__main__': unittest.main()
