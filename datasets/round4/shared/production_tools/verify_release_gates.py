"""Exercise production rejection gates with in-memory invalid fixtures; no spectra."""
from __future__ import annotations
import argparse,copy,pathlib
from unittest.mock import patch
import run_member
from prepare_global import read,write

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repository',type=pathlib.Path,required=True);a.add_argument('--freeze',type=pathlib.Path,required=True);a.add_argument('--release',type=pathlib.Path,required=True);a.add_argument('--out',type=pathlib.Path,required=True);args=a.parse_args()
    repo=args.repository.resolve();freeze=args.freeze.resolve();release=args.release.resolve()
    if args.out.resolve().is_relative_to(freeze):raise ValueError('Gate reports must be outside the freeze')
    original_read=run_member.read;original_sha=run_member.sha;base=read(release);results=[]
    def rejection(name,fixture=None,include=True,hash_target=None,expected=''):
        def fixture_read(path):return copy.deepcopy(fixture) if pathlib.Path(path).resolve()==release and fixture is not None else original_read(path)
        def fixture_sha(path):return '0'*64 if hash_target is not None and pathlib.Path(path).resolve()==hash_target.resolve() else original_sha(path)
        with patch.object(run_member,'read',side_effect=fixture_read),patch.object(run_member,'sha',side_effect=fixture_sha):
            try:run_member.validate_freeze(repo,freeze,release,'A',production=True,include_sealed=include)
            except ValueError as exc:
                if expected not in str(exc):raise AssertionError(f'{name}: unexpected rejection {exc}')
                results.append({'case':name,'rejected':True,'message':str(exc)});return
            raise AssertionError(name+': invalid production request accepted')
    rejection('unapproved_release',expected='not approved')
    bad=copy.deepcopy(base);bad['freeze_manifest_sha256']='0'*64;rejection('wrong_freeze_hash',bad,expected='different freeze')
    bad=copy.deepcopy(base);name=next(iter(bad['production_tool_sha256']));bad['production_tool_sha256'][name]='0'*64;rejection('wrong_tool_hash',bad,expected='tool changed')
    bad=copy.deepcopy(base);bad['production_approved']=True;rejection('missing_collaborator_review_evidence',bad,expected='review/merge evidence')
    bad=copy.deepcopy(base);bad.update(production_approved=True,review_evidence={'pull_request_url':'fixture://not-an-approval','merged_commit':'fixture','reviewed_by':'fixture'})
    rejection('sealed_mode_not_requested',bad,include=False,expected='include-sealed-qc')
    rejection('changed_frozen_input',hash_target=freeze/'scope.json',expected='Frozen file changed')
    rejection('changed_pinned_candidate',fixture=bad,hash_target=repo/'datasets/round4/member_A/candidates_v1/A_samples.json',expected='Pinned candidate/history source changed')
    result={'status':'passed_no_spectrum_rejection_checks','cases':results,'case_count':len(results),'spectra_generated':0,'fixtures':'Invalid release objects and hashes were injected only in memory; the real release remains unapproved and no source/input file was edited.'}
    write(args.out,result);print(result['status'],len(results))

if __name__=='__main__':main()
