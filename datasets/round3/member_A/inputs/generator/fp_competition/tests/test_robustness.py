from pathlib import Path
import sys
import tempfile
import json
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np

from fp_competition.robustness import broaden_channels,read_channel_signal,write_views,integrate_channel_feature


class RobustnessTests(unittest.TestCase):
    def test_central_area_centroid_and_variance(self):
        y=np.zeros(2048);y[415]=1000
        x=np.arange(2048)
        for width in (0,10,14):
            result,budget=broaden_channels(y,width)
            self.assertAlmostEqual(result.sum(),1000,places=8)
            self.assertAlmostEqual(np.dot(x,result)/result.sum(),415,places=8)
            self.assertAlmostEqual(budget['budget_residual'],0,places=8)
            if width:
                variance=np.dot((x-415)**2,result)/result.sum()
                self.assertAlmostEqual(variance,(width/2.354820045)**2+1/12,places=5)

    def test_edge_loss_not_folded_back(self):
        y=np.zeros(2048);y[0]=1000
        result,budget=broaden_channels(y,14)
        self.assertLess(result.sum(),600)
        self.assertGreater(budget['outside_window_signal'],400)
        self.assertAlmostEqual(result.sum()+budget['outside_window_signal'],1000,places=8)

    def test_input_validation(self):
        for width in (-1,float('nan'),True,100):
            with self.assertRaises(ValueError):
                broaden_channels(np.ones(2048),width)
        for y in (np.ones(10),np.array([float('nan')]*2048),-np.ones(2048)):
            with self.assertRaises(ValueError):
                broaden_channels(y,10)

    def test_source_integrity_unknown_units_and_derived_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'raw.pu'
            p.write_text('\n'.join(['1.5']*2048+['300','0.013916 0.621189']),encoding='utf-8')
            original=p.read_bytes()
            y,info=read_channel_signal(p)
            out=Path(temporary)/'views'
            write_views(y,out,source_info=info)
            self.assertEqual(p.read_bytes(),original)
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertFalse(manifest['physical_correction'])
            self.assertFalse(manifest['calibration_verified'])
            self.assertEqual(manifest['source']['signal_unit'],'unknown')
            self.assertEqual(manifest['source']['uninterpreted_footer'],['300','0.013916 0.621189'])
            with self.assertRaises(FileExistsError):
                write_views(y,out,source_info=info)

    def test_integral_does_not_require_gaussian_shape(self):
        x=np.arange(2048);baseline=2+x*.01
        y=baseline.copy();y[410:421]+=np.array([1,3,8,20,40,100,50,15,8,2,1])
        feature=integrate_channel_feature(y,395,437)
        self.assertAlmostEqual(feature['net_integral'],248,places=8)
        self.assertFalse(feature['negative_background'])
        with self.assertRaises(ValueError):
            integrate_channel_feature(y,400,401)


if __name__=='__main__':
    unittest.main()
