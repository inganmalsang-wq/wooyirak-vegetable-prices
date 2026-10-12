import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from update_wholesale import transform

class WholesaleTests(unittest.TestCase):
    def test_transform_price_unit_and_grade(self):
        rows=[{'EXAMIN_DE':'20261008','FRMPRD_CATGORY_CD':'200','PRDLST_NM':'양파','SPCIES_NM':'양파','GRAD_NM':'상품','EXAMIN_UNIT':'20kg','AREA_NM':'서울','MRKT_NM':'가락','AMT':'40000'}]
        result=transform(rows)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['price_kg'],2000)
        self.assertEqual(result[0]['grade'],'상품')
    def test_no_unit_no_price(self):
        rows=[{'EXAMIN_DE':'20261008','FRMPRD_CATGORY_CD':'200','PRDLST_NM':'대파','SPCIES_NM':'일반','GRAD_NM':'상품','EXAMIN_UNIT':'1단','AREA_NM':'부산','MRKT_NM':'부전','AMT':'10000'}]
        self.assertEqual(transform(rows),[])
    def test_category_ignored(self):
        rows=[{'EXAMIN_DE':'20261008','FRMPRD_CATGORY_CD':'100','PRDLST_NM':'감자','SPCIES_NM':'일반','GRAD_NM':'상품','EXAMIN_UNIT':'20kg','AREA_NM':'서울','MRKT_NM':'가락','AMT':'40000'}]
        self.assertEqual(transform(rows),[])

if __name__=='__main__':unittest.main()
