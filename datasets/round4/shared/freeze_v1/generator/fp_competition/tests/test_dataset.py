"""Auditable export/replay checks including deliberately damaged bundles."""
from dataclasses import replace
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fp_competition.core import Profile
from fp_competition.dataset import (generate_dataset,audit_dataset,replay_dataset,read_json,write_json,
    sha256,seal,energy_window,make_plan,safe_path,external_report_path,pack_dataset)


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fp-dataset-test-')
        cls.root=Path(cls.temp.name)
        cls.samples=[{'id':str(i),'composition_percent':{'Fe':70.+i,'Cr':20.-i,'Ni':10.,'Pb':0.}} for i in range(3)]
        cls.profile=Profile(secondary=False,scatter=False,source_step_keV=.5)
        cls.bundle=generate_dataset(cls.samples,cls.profile,cls.root/'valid',replicates=2,seed=18,
                                     jitter={'zero_keV':[.5,.7]},targets=['Fe','Cr','Ni','Pb'])

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def clone(self,name):
        path=self.root/name
        shutil.copytree(self.bundle,path)
        return path

    def test_complete_bundle_hashes_sources_and_qc(self):
        result=audit_dataset(self.bundle)
        self.assertEqual(result['status'],'passed',result['errors'])
        self.assertEqual(result['spectra_checked'],6)
        m=read_json(self.bundle/'manifest.json')
        self.assertEqual(m['acceptance_status'],'pending_independent_validation')
        for r in m['records']:
            self.assertEqual(r['full_results_sha256'],sha256(self.bundle/r['full_results']))
            self.assertEqual(r['blind_input_sha256'],r['sha256'])
        for name in ('dataset.py','app.py','core.py','tests/test_dataset.py'):
            self.assertTrue((self.bundle/'reproducibility/generator/fp_competition'/name).exists())
        self.assertTrue((self.bundle/'reproducibility/requirements-lock.txt').exists())

    def test_complete_physical_replay_and_subset_are_distinct(self):
        report=replay_dataset(self.bundle)
        self.assertEqual(report['status'],'passed',report)
        self.assertTrue(report['complete_physics_recalculation'])
        self.assertEqual(report['maximum_absolute_array_difference'],0.)
        report=replay_dataset(self.bundle,limit=1)
        self.assertEqual(report['scope'],'subset')
        self.assertFalse(report['complete_physics_recalculation'])

    def test_hash_tampering_is_rejected(self):
        root=self.clone('bad-hash');path=root/'full_results/S000001.json'
        path.write_bytes(path.read_bytes()+b' ')
        report=audit_dataset(root)
        self.assertEqual(report['status'],'failed')
        self.assertTrue(any('Hash mismatch' in e or 'hash mismatch' in e for e in report['errors']))

    def test_resealed_blind_leak_is_still_rejected(self):
        root=self.clone('leak');path=root/'blind_inputs/S000001.json';value=read_json(path)
        value['seed']=3;write_json(path,value)
        m=read_json(root/'manifest.json');m['records'][0].update(blind_input_sha256=sha256(path),sha256=sha256(path))
        write_json(root/'manifest.json',m);seal(root)
        self.assertTrue(any('isolation' in e for e in audit_dataset(root)['errors']))

    def test_resealed_component_error_is_rejected(self):
        root=self.clone('component');path=root/'full_results/S000001.json';value=read_json(path)
        value['components_expected_counts']['primary'][0]+=10;write_json(path,value)
        m=read_json(root/'manifest.json');m['records'][0]['full_results_sha256']=sha256(path)
        write_json(root/'manifest.json',m);seal(root)
        self.assertTrue(any('Component sum' in e for e in audit_dataset(root)['errors']))

    def test_path_escape_and_report_overwrite_are_rejected(self):
        for name in ('../outside.json','C:/outside.json','/absolute','..\\outside'):
            with self.assertRaises(ValueError): safe_path(self.bundle,name)
        with self.assertRaises(ValueError): external_report_path(self.bundle,self.bundle/'qc.json')
        with self.assertRaises(ValueError): external_report_path(self.bundle,self.bundle)
        existing=self.root/'existing-report.json';existing.write_text('{}',encoding='utf-8')
        with self.assertRaises(FileExistsError): external_report_path(self.bundle,existing)

    def test_preflight_writes_nothing_and_existing_bundle_is_preserved(self):
        out=self.root/'preflight'
        with self.assertRaises(ValueError): generate_dataset(self.samples,self.profile,out,jitter={'unknown':[0,1]})
        self.assertFalse(out.exists())
        original=sha256(self.bundle/'manifest.json')
        with self.assertRaises(FileExistsError): generate_dataset(self.samples,self.profile,self.bundle)
        self.assertEqual(original,sha256(self.bundle/'manifest.json'))

    def test_failed_generation_never_claims_completion(self):
        out=self.root/'failed'
        with patch('fp_competition.dataset.simulate',side_effect=ValueError('injected generation failure')):
            with self.assertRaises(ValueError): generate_dataset(self.samples,self.profile,out)
        self.assertEqual(read_json(out/'manifest.json')['status'],'failed_partial')
        self.assertEqual(audit_dataset(out)['status'],'failed')

    def test_split_seed_is_separate_and_legacy_default_is_retained(self):
        kwargs=dict(samples=self.samples,profile=self.profile,replicates=2,seed=5,jitter={},closure='strict',legacy_al='reject')
        a,_,sa=make_plan(**kwargs);b,_,sb=make_plan(**kwargs,split_seed=9)
        self.assertEqual(sa,5);self.assertEqual(sb,9)
        self.assertEqual([j[3] for j in a],[j[3] for j in b])
        self.assertEqual([j[2] for j in a],[j[2] for j in b])

    def test_window_centers_and_edges_are_not_confused(self):
        w=energy_window(replace(self.profile,zero_keV=.5,gain_keV_channel=.01,channels=100))
        self.assertAlmostEqual(w['first_center'],.5);self.assertAlmostEqual(w['last_center'],1.49)
        self.assertAlmostEqual(w['lower_edge'],.495);self.assertAlmostEqual(w['upper_edge'],1.495)

    def test_solver_support_is_reused_without_recalculating_all_targets(self):
        with patch('fp_competition.dataset.element_support',side_effect=AssertionError('Redundant support evaluation')):
            out=generate_dataset(self.samples,self.profile,self.root/'reuse-support',targets=['Fe','Cr','Ni','Pb'])
        self.assertEqual(audit_dataset(out)['status'],'passed')

    def test_zip_package_has_external_hash(self):
        out=self.root/'bundle.zip';result=pack_dataset(self.bundle,out)
        self.assertEqual(result['sha256'],sha256(out))
        self.assertTrue(out.with_suffix('.zip.sha256').exists())


if __name__=='__main__': unittest.main()
