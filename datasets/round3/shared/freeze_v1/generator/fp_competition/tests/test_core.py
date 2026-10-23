"""Engineering/numerical checks. These do not certify scientific or blind accuracy."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import numpy as np
from scipy.integrate import quad
from scipy.special import exp1

from fp_competition.core import Profile,composition,simulate,source_spectrum,gaussian_bin_weights,_kernel_primitive,cross
from fp_competition.app import generate_batch,read_samples,design_compositions


class ForwardModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.percent={'Fe':70.,'Cr':20.,'Ni':10.}
        cls.profile=Profile(source_step_keV=.2,secondary_layers=64)
        cls.result=simulate(cls.percent,cls.profile,seed=42)

    def test_area_conservation_for_different_peak_widths(self):
        edges=np.linspace(0,20,10001)
        for fwhm in (.05,.13,.4):
            self.assertAlmostEqual(gaussian_bin_weights(edges,6.4,fwhm).sum(),1,places=12)

    def test_truncation_not_renormalized(self):
        weights=gaussian_bin_weights(np.linspace(6.4,7,501),6.4,.13)
        self.assertAlmostEqual(weights.sum(),.5,places=10)

    def test_response_escape_and_window_accounting(self):
        result=self.result
        modeled=sum(result['expected_counts'])-sum(result['components_expected_counts']['background'])
        self.assertAlmostEqual((modeled+sum(result['outside_window_counts'].values()))/result['detected_signal_before_window_counts'],1,places=10)

    def test_poisson_reproducibility_and_expected_signal(self):
        a=simulate(self.percent,self.profile,seed=42)
        b=simulate(self.percent,self.profile,seed=43)
        self.assertEqual(a['counts'],self.result['counts'])
        self.assertNotEqual(a['counts'],b['counts'])
        self.assertEqual(a['expected_counts'],b['expected_counts'])
        self.assertTrue(all(isinstance(v,int) and v>=0 for v in a['counts']))

    def test_time_scaling_and_rate_single_conversion(self):
        result=simulate(self.percent,replace(self.profile,live_time_s=300),poisson=False)
        np.testing.assert_allclose(result['expected_counts'],np.array(self.result['expected_counts'])*2,rtol=1e-12)

    def test_zero_element_does_not_emit(self):
        result=simulate({'Fe':100.,'Cu':0},replace(self.profile,scatter=False,secondary=False),poisson=False)
        self.assertEqual({line['element'] for line in result['lines']},{'Fe'})

    def test_below_edge_does_not_generate_K_lines(self):
        result=simulate({'Fe':100.},replace(self.profile,voltage_kV=6,scatter=False),poisson=False)
        self.assertFalse(any(line['element']=='Fe' and line['line'].startswith('K') for line in result['lines']))

    def test_absorption_edge_is_preserved(self):
        self.assertGreater(cross('CS_Total',26,7.113),cross('CS_Total',26,7.111)*5)

    def test_incident_grid_covers_voltage_not_detector_window(self):
        energy,weights=source_spectrum(self.profile,{'Fe':1.})
        self.assertGreater(energy.max(),48.8)
        self.assertLess(self.profile.zero_keV+self.profile.gain_keV_channel*self.profile.channels,30)
        self.assertAlmostEqual(weights.sum(),1,places=12)

    def test_silicon_width_obeys_fano_term(self):
        widths=self.profile.fwhm_keV(np.array([1,5.9,20]))
        self.assertTrue(np.all(np.diff(widths)>0))
        self.assertGreater(widths[1],.116)

    def test_secondary_enhances_and_converges(self):
        fine=simulate(self.percent,replace(self.profile,secondary_layers=128),poisson=False)
        coarse=sum(self.result['components_expected_counts']['secondary'])
        refined=sum(fine['components_expected_counts']['secondary'])
        self.assertGreater(refined,0)
        self.assertLess(abs(coarse-refined)/refined,.03)
        no_secondary=simulate(self.percent,replace(self.profile,secondary=False),poisson=False)
        self.assertAlmostEqual(sum(no_secondary['components_expected_counts']['secondary']),0)

    def test_secondary_kernel_against_independent_quadrature(self):
        z=.003;left=.001;right=.005;mu=45.
        exact=quad(lambda s:exp1(mu*abs(s-z)),left,right,points=[z],epsabs=1e-12)[0]
        cell=float(_kernel_primitive(np.array([right-z]),mu)[0]-_kernel_primitive(np.array([left-z]),mu)[0])
        self.assertAlmostEqual(cell,exact,places=10)

    def test_thin_slab_primary_increases_with_thickness(self):
        a=simulate(self.percent,replace(self.profile,mass_thickness_g_cm2=.0001,secondary=False,scatter=False),poisson=False)
        b=simulate(self.percent,replace(self.profile,mass_thickness_g_cm2=.001,secondary=False,scatter=False),poisson=False)
        self.assertGreater(sum(b['expected_counts']),sum(a['expected_counts']))

    def test_original_composition_is_not_mutated_or_silently_closed(self):
        original={'Fe':68.,'Cr':22.,'Ni':4.7}
        saved=copy.deepcopy(original)
        with self.assertRaises(ValueError):
            composition(original)
        weights,provenance=composition(original,closure='normalize_explicit')
        self.assertEqual(original,saved)
        self.assertEqual(provenance['original_percent'],original)
        self.assertAlmostEqual(sum(weights.values()),1)
        self.assertTrue(provenance['notes'])

    def test_al_alias_requires_explicit_choice(self):
        with self.assertRaises(ValueError):
            composition({'Fe':99.9,'Als':.04,'Alt':.06})
        _,summed=composition({'Fe':99.9,'Als':.04,'Alt':.06},legacy_al='sum_as_written')
        self.assertAlmostEqual(summed['used_percent']['Al'],.1)

    def test_invalid_inputs_rejected(self):
        for percent in ({'Fe':float('nan')},{'Fe':-1},{'Bad':100},{'Fe':True},{'Fe':0}):
            with self.assertRaises(ValueError):
                simulate(percent,self.profile)
        for value in ({'channels':True},{'secondary':1},{'live_time_s':0},{'gain_keV_channel':-1},{'voltage_kV':float('inf')},{'secondary_layers':4},{'unknown':1}):
            with self.assertRaises(ValueError):
                Profile.from_dict(value)

    def test_batch_grouping_repeatability_blind_inputs_and_overwrite_protection(self):
        samples=[{'id':'A','composition_percent':self.percent},{'id':'alias-of-A','composition_percent':self.percent}]
        with tempfile.TemporaryDirectory() as temporary:
            first=Path(temporary)/'one';second=Path(temporary)/'two'
            p=replace(self.profile,secondary=False,scatter=False)
            generate_batch(samples,p,first,replicates=2,seed=8,jitter={'gain_keV_channel':[.013,.015]})
            generate_batch(samples,p,second,replicates=2,seed=8,jitter={'gain_keV_channel':[.013,.015]})
            one=json.loads((first/'manifest.json').read_text(encoding='utf-8'))
            two=json.loads((second/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(one,two)
            self.assertEqual(one['status'],'complete')
            self.assertEqual(len({r['family'] for r in one['records']}),1)
            self.assertEqual(len({r['split'] for r in one['records']}),1)
            for record in one['records']:
                data=(first/record['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
                blind=json.loads(data)
                self.assertNotIn('energy_keV',blind)
                self.assertNotIn('profile',blind)
                self.assertNotIn('composition',blind)
            sentinel=(first/'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError):
                generate_batch(samples,p,first)
            self.assertEqual(sentinel,(first/'manifest.json').read_bytes())

    def test_bad_batch_fails_before_any_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'new'
            with self.assertRaises(ValueError):
                generate_batch([{'id':'bad','composition_percent':{'Fe':10}}],self.profile,out)
            self.assertFalse(out.exists())

    def test_three_or_more_compositions_populate_all_splits(self):
        with tempfile.TemporaryDirectory() as temporary:
            samples=[{'id':str(i),'composition_percent':{'Fe':70+i,'Cr':20-i,'Ni':10}} for i in range(5)]
            out=Path(temporary)/'split'
            generate_batch(samples,replace(self.profile,secondary=False,scatter=False),out)
            manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual({r['split'] for r in manifest['records']},{'train','validation','test'})

    def test_composition_design_is_closed_reproducible_and_within_ranges(self):
        spec={'ranges_percent':{'Cr':[10,30],'Ni':[0,25]},'balance_element':'Fe','balance_range_percent':[40,90]}
        one=design_compositions(spec,20,123)
        self.assertEqual(one,design_compositions(spec,20,123))
        for sample in one['samples']:
            row=sample['composition_percent']
            self.assertAlmostEqual(sum(row.values()),100)
            self.assertTrue(10<=row['Cr']<=30 and 0<=row['Ni']<=25 and 40<=row['Fe']<=90)
        with self.assertRaises(ValueError):
            design_compositions({'ranges_percent':{'Ni':[90,100]},'balance_element':'Fe','balance_range_percent':[30,40]},1,0)

    def test_excel_and_csv_samples_preserve_percentages(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'samples.xlsx'
            book=openpyxl.Workbook();sheet=book.active
            sheet.append(['编号','Fe','Cr','Ni']);sheet.append(['A',70,20,10]);book.save(path);book.close()
            rows=read_samples(path)
            self.assertEqual(rows,[{'id':'A','composition_percent':{'Fe':70.,'Cr':20.,'Ni':10.}}])
            csvpath=Path(temporary)/'samples.csv'
            csvpath.write_text('编号,Fe,Cr,Ni\nA,70,20,10\n',encoding='utf-8-sig')
            self.assertEqual(read_samples(csvpath),rows)


if __name__=='__main__':
    unittest.main()
