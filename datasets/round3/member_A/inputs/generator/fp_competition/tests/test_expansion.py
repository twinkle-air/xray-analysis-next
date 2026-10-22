"""Elemental expansion checks; no real-device accuracy certification."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
import xraylib as xl
from fp_competition.core import Profile, line_data, line_cs, element_support, simulate, air_transmission, TARGET_ELEMENTS
from fp_competition.minerals import components_to_elements, design_minerals
from fp_competition.app import generate_batch,read_samples


class ExpansionTests(unittest.TestCase):
    def test_sio2_mass_conversion_and_ppm_units(self):
        used,source=components_to_elements({'SiO2':99.}, {'Cu':10000.})
        si=xl.AtomicWeight(14)/(xl.AtomicWeight(14)+2*xl.AtomicWeight(8))*99
        self.assertAlmostEqual(used['Si'],si,places=9)
        self.assertAlmostEqual(used['Cu'],1.)
        self.assertAlmostEqual(sum(used.values()),100.)

    def test_compound_closure_duplicates_and_reporting_convention(self):
        with self.assertRaises(ValueError):
            components_to_elements({'SiO2':90.})
        with self.assertRaises(ValueError):
            components_to_elements({'Fe2O3':100.},{'Fe':1.})
        used,p=components_to_elements({'Fe2O3T':99.},closure='normalize_explicit')
        self.assertTrue(any('valence' in n for n in p['notes']))
        self.assertEqual(p['input_sum_percent'],99.)
        for c,t in [({'SiO2':True},{}),({'SiO2':100.},{'Bad':1}),({'SiO2':float('nan')},{})]:
            with self.assertRaises(ValueError): components_to_elements(c,t)

    def test_individual_line_codes_do_not_double_count_shell_rates(self):
        for z in (11,26,30,56,82):
            lines=line_data(z)
            self.assertEqual(len({code for _,code,_ in lines}),len(lines))
            for prefix,shell in [('K',xl.K_SHELL),('L1',xl.L1_SHELL),('L2',xl.L2_SHELL),('L3',xl.L3_SHELL),('M5',xl.M5_SHELL)]:
                subtotal=sum(line_cs(z,code,49.) for name,code,_ in lines if name.startswith(prefix))
                try: total=xl.CS_FluorShell_Kissel_Cascade(z,shell,49.)
                except ValueError: total=0.
                # xraylib tabulated radiative rates can sum slightly above 1:
                # Pb L2=1.00000450818, M5=1.000003550356 at 49 keV.
                self.assertLessEqual(subtotal,total*(1+1e-5)+1e-10)

    def test_lead_M_interference_with_sulfur_is_present(self):
        lines=line_data(82)
        sulfur=xl.LineEnergy(16,xl.KA1_LINE)
        self.assertTrue(any(name.startswith('M') and abs(energy-sulfur)<.06 for name,_,energy in lines))

    def test_exit_air_reduces_low_energy_more_and_is_not_renormalized(self):
        p=Profile(scatter=False,secondary=False,source_step_keV=.5)
        t=air_transmission(p,[1.04,6.4],1.)
        self.assertLess(t[0],t[1])
        a=simulate({'Na':10.,'Fe':90.},p,poisson=False)
        b=simulate({'Na':10.,'Fe':90.},replace(p,exit_air_path_cm=1.),poisson=False)
        self.assertLess(sum(b['expected_counts']),sum(a['expected_counts']))
        c=simulate({'Fe':100.},replace(p,incident_air_path_cm=1.),poisson=False)
        d=simulate({'Fe':100.},p,poisson=False)
        self.assertLess(sum(c['expected_counts']),sum(d['expected_counts']))

    def test_support_distinguishes_matrix_only_and_unexcitable_targets(self):
        report=element_support(Profile(voltage_kV=2.),['O','Fe','Pb'])
        self.assertEqual(report['elements']['O']['status'],'no_modeled_line_above_1keV')
        self.assertEqual(report['elements']['Fe']['status'],'no_excitable_line_in_window')
        self.assertFalse(report['is_detection_limit'])
        all_targets=element_support(Profile())
        self.assertEqual(set(all_targets['elements']),set(TARGET_ELEMENTS))
        self.assertEqual(len(TARGET_ELEMENTS),32)

    def test_mineral_design_reproducible_closed_with_exact_absence(self):
        spec={'compound_ranges_percent':{'Al2O3':[10,20]},'balance_compound':'SiO2',
              'balance_range_percent':[70,90],'trace_ranges_ppm':{'Pb':[1,100],'Zn':[1,100]},
              'trace_absence_probability':{'Pb':1.,'Zn':0.}}
        a=design_minerals(spec,5,7)
        self.assertEqual(a,design_minerals(spec,5,7))
        for row in a['samples']:
            self.assertAlmostEqual(sum(row['composition_percent'].values()),100.)
            self.assertEqual(row['composition_percent']['Pb'],0.)
            self.assertGreater(row['composition_percent']['Zn'],0.)
        bad=dict(spec,trace_absence_probability={'Pb':2.})
        with self.assertRaises(ValueError): design_minerals(bad,1,7)

    def test_batch_dense_zero_labels_and_source_provenance_are_hidden(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'library'
            sample={'id':'matrix','composition_percent':{'Fe':100.,'Pb':0.},'provenance':{'origin':'synthetic'}}
            generate_batch([sample],Profile(secondary=False,scatter=False,source_step_keV=.5),out,targets=['Fe','Pb','Zn'])
            truth=json.loads((out/'truth.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(truth['targets_percent'],{'Fe':100.,'Pb':0.,'Zn':0.})
            self.assertEqual(truth['source_provenance'],sample['provenance'])
            blind=json.loads((out/'blind_inputs/S000001.json').read_text(encoding='utf-8'))
            self.assertNotIn('element_support',blind)
            self.assertNotIn('targets_percent',blind)
            invalid=Path(temp)/'invalid'
            with self.assertRaises(ValueError):
                generate_batch([sample],Profile(),invalid,targets=['Bad'])
            self.assertFalse(invalid.exists())

    def test_negative_air_path_and_false_calibration_are_rejected(self):
        for value in ({'exit_air_path_cm':-1.},{'incident_air_path_cm':float('inf')},{'air_density_g_cm3':0.}, {'calibration_status':'verified'}):
            with self.assertRaises(ValueError): Profile.from_dict(value)


if __name__=='__main__': unittest.main()
