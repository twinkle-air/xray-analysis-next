"""Explicit compound/trace designs. These are homogeneous synthetic mixtures."""
from __future__ import annotations
import math
import numpy as np
import xraylib as xl

if __package__:
    from .core import composition
else:
    from core import composition


def _limits(value, maximum, name):
    if not isinstance(value,list) or len(value)!=2 or any(
            isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value
        ) or not 0<=value[0]<=value[1]<=maximum:
        raise ValueError('Invalid range: '+str(name))
    return value


def components_to_elements(compounds_percent, trace_ppm=None, *, closure='strict'):
    """Use atomic mass fractions; ppm=mg/kg, 10000 ppm=1 mass percent.

    Fe2O3T is a reporting convention, not proof of Fe valence or oxygen content.
    Trace elements already represented by a compound are rejected to avoid duplication.
    """
    if not isinstance(compounds_percent,dict) or not compounds_percent:
        raise ValueError('Nonempty compounds_percent required')
    if trace_ppm is not None and not isinstance(trace_ppm,dict):
        raise ValueError('trace_ppm must be an object')
    trace_ppm=trace_ppm or {}
    elements={}; matrix_elements=set(); notes=[]
    for formula,amount in compounds_percent.items():
        _limits([amount,amount],100,formula)
        if formula=='Fe2O3T':
            notes.append('Total Fe expressed as Fe2O3T converted assuming Fe2O3 stoichiometry; oxygen/valence not independently measured')
        parsed=xl.CompoundParser('Fe2O3' if formula=='Fe2O3T' else formula)
        for z,weight in zip(parsed['Elements'],parsed['massFractions']):
            symbol=xl.AtomicNumberToSymbol(z)
            matrix_elements.add(symbol)
            elements[symbol]=elements.get(symbol,0.)+amount*weight
    for symbol,value in trace_ppm.items():
        _limits([value,value],1e6,symbol)
        composition({symbol:100.})
        if symbol in matrix_elements:
            raise ValueError('Trace element also represented in compounds: '+symbol)
        elements[symbol]=value/10000.
    _,material=composition(elements,closure)
    used={s:material['used_percent'].get(s,0.) for s in sorted(elements)}
    return used,{'kind':'compound_and_trace_conversion','compounds_percent':dict(compounds_percent),
                 'trace_ppm':dict(trace_ppm),'input_sum_percent':sum(compounds_percent.values())+sum(trace_ppm.values())/10000.,
                 'conversion_original_percent':elements,'closure':material,
                 'notes':notes+['Oxygen is stoichiometric matrix bookkeeping; not a direct XRF prediction target in this model',
                               'Homogeneous elemental attenuation approximation; chemical speciation and mineral grain effects omitted']}


def design_minerals(spec,count,seed):
    required={'compound_ranges_percent','balance_compound','balance_range_percent','trace_ranges_ppm'}
    if not isinstance(spec,dict) or not required<=set(spec) or set(spec)-required-{'trace_absence_probability'}:
        raise ValueError('Mineral design needs compound_ranges_percent, balance_compound, balance_range_percent, trace_ranges_ppm')
    if type(count) is not int or not 1<=count<=10000 or type(seed) is not int or seed<0:
        raise ValueError('count 1..10000 and nonnegative integer seed required')
    ranges=spec['compound_ranges_percent'];balance=spec['balance_compound'];br=spec['balance_range_percent']
    traces=spec['trace_ranges_ppm'];absence=spec.get('trace_absence_probability',{})
    if not isinstance(ranges,dict) or not ranges or balance in ranges or not isinstance(traces,dict) or not isinstance(absence,dict) or set(absence)-set(traces):
        raise ValueError('Invalid compound/trace design fields')
    for formula,value in {**ranges,balance:br}.items():
        _limits(value,100,formula)
    for symbol,value in traces.items():
        _limits(value,1e6,symbol)
        if value[0]<=0:
            raise ValueError('Positive log-uniform trace range required; use absence_probability for exact zero: '+symbol)
    for symbol,value in absence.items():
        _limits([value,value],1,symbol)
    # Validate formulas, symbols and duplicate trace elements before sampling.
    components_to_elements({s:1. for s in list(ranges)+[balance]},
                           {s:0. for s in traces},closure='normalize_explicit')
    rng=np.random.default_rng(seed);samples=[]
    for attempt in range(count*100+1000):
        compounds={s:float(rng.uniform(*v)) for s,v in ranges.items()}
        ppm={s:0. if rng.random()<absence.get(s,0.) else float(np.exp(rng.uniform(*np.log(v))))
             for s,v in traces.items()}
        rest=100-sum(compounds.values())-sum(ppm.values())/10000.
        if not br[0]<=rest<=br[1]:
            continue
        compounds[balance]=rest
        percent,provenance=components_to_elements(compounds,ppm)
        provenance['basis']='User-selected synthetic design ranges; not a population distribution or certified material'
        samples.append({'id':f'MINERAL{len(samples)+1:05d}','composition_percent':percent,'provenance':provenance})
        if len(samples)==count:
            return {'synthetic_design':True,'design_spec':spec,'seed':seed,'samples':samples}
    raise ValueError('Too few feasible compound mixtures; adjust ranges')
