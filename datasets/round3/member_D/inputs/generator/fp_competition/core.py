"""Independent FP forward model. Synthetic method-development data, not certified spectra."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from functools import lru_cache
import math
import re

import numpy as np
from scipy.special import ndtr, exp1
import xraylib as xl

VERSION = '0.2.0'
# Individual transitions only. Aggregate macros (e.g. LA_LINE, L1N67_LINE)
# overlap their constituents and must never be summed with them.
LINE_NAMES = tuple(sorted(n for n in dir(xl) if re.fullmatch(
    r'(?:K[LMNOPQ][1-7]|L[123][LMNOPQ][1-7]|M[12345][MNOPQ][1-7])_LINE', n)))
TARGET_ELEMENTS = ('Na','Mg','Al','Si','P','S','Cl','K','Ca','Ti','V','Cr','Mn','Fe',
                   'Co','Ni','Cu','Zn','As','Se','Rb','Sr','Y','Zr','Nb','Mo','Cd','Sn','Sb','Ba','W','Pb')


@dataclass(frozen=True)
class Profile:
    name: str = 'assumed_SDD_method_validation'
    voltage_kV: float = 49.0
    current_uA: float = 196.1
    reference_current_uA: float = 196.1
    target: str = 'Ag'
    live_time_s: float = 150.0
    incident_photons_s: float = 1e7
    channels: int = 2048
    gain_keV_channel: float = 0.013839285714285714
    zero_keV: float = 0.6133928571428573
    noise_fwhm_eV: float = 55.0
    fano_factor: float = 0.115
    pair_creation_eV: float = 3.65
    detector_area_cm2: float = 0.25
    detector_distance_cm: float = 1.0
    detector_si_um: float = 500.0
    detector_be_um: float = 12.5
    tube_be_um: float = 200.0
    filter_Al_um: float = 0.0
    incident_air_path_cm: float = 0.0
    exit_air_path_cm: float = 0.0
    air_density_g_cm3: float = 0.001205
    incident_angle_deg: float = 45.0
    exit_angle_deg: float = 45.0
    scatter_angle_deg: float = 90.0
    mass_thickness_g_cm2: float = 2.37
    tube_line_fraction: float = 0.15
    escape_fraction: float = 0.01
    source_step_keV: float = 0.10
    secondary_layers: int = 96
    secondary: bool = True
    scatter: bool = True
    background_counts_channel: float = 0.0
    calibration_status: str = 'assumed_unverified'

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError('Profile must be an object')
        unknown = set(value)-{f.name for f in fields(cls)}
        if unknown:
            raise ValueError('Unknown profile fields: '+str(sorted(unknown)))
        profile = cls(**value)
        profile.validate()
        return profile

    def validate(self):
        for f in fields(self):
            value = getattr(self,f.name)
            if f.name in ('name','target','calibration_status'):
                if not isinstance(value,str) or not value:
                    raise ValueError(f.name+' must be a nonempty string')
            elif f.name in ('secondary','scatter'):
                if type(value) is not bool:
                    raise ValueError(f.name+' must be boolean')
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f.name+' must be a finite number')
        if type(self.channels) is not int or not 64<=self.channels<=8192:
            raise ValueError('channels must be an integer in [64,8192]')
        if type(self.secondary_layers) is not int or not 32<=self.secondary_layers<=512:
            raise ValueError('secondary_layers must be an integer in [32,512]')
        for key in ('current_uA','reference_current_uA','live_time_s','incident_photons_s','gain_keV_channel',
                    'detector_area_cm2','detector_distance_cm','detector_si_um','mass_thickness_g_cm2'):
            if getattr(self,key)<=0:
                raise ValueError(key+' must be positive')
        if not 2<=self.voltage_kV<=100 or not .01<=self.source_step_keV<=1:
            raise ValueError('voltage 2..100 kV and source_step 0.01..1 keV required')
        for key in ('incident_angle_deg','exit_angle_deg'):
            if not 5<=getattr(self,key)<=90:
                raise ValueError(key+' must be in [5,90] degrees')
        if not 5<=self.scatter_angle_deg<=175:
            raise ValueError('scatter angle must be in [5,175] degrees')
        if not 0<=self.fano_factor<=1 or not 1<=self.pair_creation_eV<=10 or self.noise_fwhm_eV<=0:
            raise ValueError('invalid detector noise/Fano parameters')
        if not 0<=self.tube_line_fraction<=.8 or not 0<=self.escape_fraction<=.1:
            raise ValueError('invalid tube line / escape fraction')
        for key in ('detector_be_um','tube_be_um','filter_Al_um','background_counts_channel',
                    'incident_air_path_cm','exit_air_path_cm'):
            if getattr(self,key)<0:
                raise ValueError(key+' cannot be negative')
        if not 0 < self.air_density_g_cm3 <= .01:
            raise ValueError('air_density_g_cm3 must be in (0,0.01]')
        if self.zero_keV<0 or self.gain_keV_channel*self.channels>200:
            raise ValueError('invalid output energy range')
        if self.incident_photons_s*self.live_time_s*self.current_uA/self.reference_current_uA>1e14:
            raise ValueError('incident exposure exceeds method-validation numeric limit')
        if self.calibration_status != 'assumed_unverified':
            raise ValueError('This release cannot certify a hardware-calibrated profile')
        z = xl.SymbolToAtomicNumber(self.target)
        if not 1<=z<=92:
            raise ValueError('target must be an element H..U')

    def fwhm_keV(self, energy):
        energy = np.asarray(energy,dtype=float)
        return np.sqrt(self.noise_fwhm_eV**2+2.354820045**2*self.fano_factor*self.pair_creation_eV*np.maximum(energy,0)*1000)/1000

    @property
    def solid_angle(self):
        radius2=self.detector_area_cm2/np.pi
        return 2*np.pi*(1-self.detector_distance_cm/np.sqrt(self.detector_distance_cm**2+radius2))


def composition(percent, closure='strict', legacy_al='reject'):
    """Returns normalized physical composition with explicit original/used provenance."""
    if closure not in ('strict','normalize_explicit') or legacy_al not in ('reject','sum_as_written','alt_is_total'):
        raise ValueError('invalid composition policy')
    if not isinstance(percent,dict) or not percent:
        raise ValueError('composition must be a nonempty object of mass percentages')
    original={}
    for symbol,value in percent.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=100:
            raise ValueError(f'invalid percentage for {symbol}')
        original[symbol]=float(value)
    used=dict(original)
    notes=[]
    als,alt=used.pop('Als',0),used.pop('Alt',0)
    if als or alt:
        if legacy_al=='reject':
            raise ValueError('Als/Alt meaning must be selected explicitly; they are not element symbols')
        if 'Al' in used:
            raise ValueError('Al cannot be supplied together with Als/Alt')
        used['Al']=als+alt if legacy_al=='sum_as_written' else alt
        notes.append('Legacy aluminum mapping '+legacy_al+' is user-selected and not independently verified')
    for symbol in used:
        try:
            z=xl.SymbolToAtomicNumber(symbol)
        except ValueError as exc:
            raise ValueError('Unsupported element '+symbol) from exc
        if not 1<=z<=92:
            raise ValueError('Supported elements: H..U')
    used={k:v for k,v in used.items() if v>0}
    total=sum(used.values())
    if total<=0:
        raise ValueError('composition total must be positive')
    if closure=='strict' and abs(total-100)>1e-6:
        raise ValueError(f'Composition sum is {total:.8g}%, not 100%; choose normalize_explicit or provide a complete composition')
    if abs(total-100)>1e-6:
        notes.append(f'Explicit normalization from {total:.8g}% to 100%; original values preserved separately')
    return {k:v/total for k,v in used.items()}, {'original_percent':original,'used_percent':{k:v/total*100 for k,v in used.items()},'original_mapped_sum_percent':total,'closure_policy':closure,'legacy_al_policy':legacy_al,'notes':notes,'basis':'User-designated values, not certified CRM values'}


@lru_cache(maxsize=400000)
def cross(section,z,e):
    return float(getattr(xl,section)(int(z),float(e)))


def mixture_mu(weights, energies):
    energies=np.atleast_1d(energies)
    return sum(w*np.array([cross('CS_Total',xl.SymbolToAtomicNumber(s),float(e)) for e in energies]) for s,w in weights.items())


@lru_cache(maxsize=92)
def line_data(z):
    result=[]
    seen=set()
    for name in LINE_NAMES:
        code=getattr(xl,name)
        if code in seen:
            continue
        seen.add(code)
        try:
            energy=xl.LineEnergy(z,code)
            if energy>=1:
                result.append((name,code,energy))
        except ValueError:
            pass
    return tuple(result)


@lru_cache(maxsize=400000)
def line_cs(z,code,e):
    # The library rejects transitions below their shell excitation threshold.
    try:
        return float(xl.CS_FluorLine_Kissel_Cascade(z,code,float(e)))
    except ValueError:
        return 0.0


def transmission(z, density, thickness_um, energies):
    if thickness_um==0:
        return np.ones_like(energies,dtype=float)
    return np.exp(-np.array([cross('CS_Total',z,float(e)) for e in energies])*density*thickness_um*1e-4)


def air_transmission(profile, energies, distance_cm):
    energies=np.atleast_1d(energies)
    if distance_cm==0:
        return np.ones_like(energies,dtype=float)
    return np.exp(-np.array([xl.CS_Total_CP('Air, Dry (near sea level)',float(e))
                            for e in energies])*profile.air_density_g_cm3*distance_cm)


def element_support(profile, elements=TARGET_ELEMENTS):
    """Structural support, not a detection limit or concentration accuracy claim."""
    profile.validate()
    edges=profile.zero_keV+profile.gain_keV_channel*(np.arange(profile.channels+1)-.5)
    rows={}
    for symbol in sorted(elements):
        composition({symbol:100.})
        z=xl.SymbolToAtomicNumber(symbol)
        lines=[]
        for name,code,energy in line_data(z):
            # At the upper bound: necessary excitation availability only, not flux.
            excitable=line_cs(z,code,profile.voltage_kV)>0
            fraction=float(gaussian_bin_weights(edges,energy,float(profile.fwhm_keV(energy))).sum())
            efficiency=float(detector_efficiency(profile,[energy])[0])
            path=float(air_transmission(profile,[energy],profile.exit_air_path_cm)[0])
            lines.append({'line':name,'energy_keV':energy,'excitable_at_voltage':excitable,
                          'recorded_window_fraction':fraction,'detector_efficiency':efficiency,
                          'exit_air_transmission':path})
        compatible=[r for r in lines if r['excitable_at_voltage'] and r['recorded_window_fraction']>.5]
        response=max((r['detector_efficiency']*r['exit_air_transmission'] for r in compatible),default=0.)
        status=('no_modeled_line_above_1keV' if not lines else
                'no_excitable_line_in_window' if not compatible else
                'strongly_attenuated_assumed_response' if response<.01 else 'structurally_supported_unvalidated')
        rows[symbol]={'status':status,'maximum_window_detector_air_response':response,'lines':lines}
    return {'elements':rows,'minimum_modeled_line_keV':1.,'is_detection_limit':False,
            'hardware_validated':False,'notes':[
                'Excitation/window checks do not establish sensitivity, selectivity or a reporting limit',
                'Response excludes incident flux, matrix absorption and peak overlap; values below 1% are a heuristic flag',
                'H/C/N/O and other sub-keV emitters can affect the matrix without directly modeled fluorescence',
                'Air paths default to zero as an explicit legacy assumption, not proof of vacuum operation']}


def source_spectrum(profile, weights):
    """Midpoint quadrature of a Kramers-like continuum + separate delta tube lines."""
    edges=list(np.linspace(1,profile.voltage_kV,int(math.ceil((profile.voltage_kV-1)/profile.source_step_keV))+1))
    for symbol in set(weights)|{profile.target}:
        z=xl.SymbolToAtomicNumber(symbol)
        for shell in (xl.K_SHELL,xl.L1_SHELL,xl.L2_SHELL,xl.L3_SHELL,
                      xl.M1_SHELL,xl.M2_SHELL,xl.M3_SHELL,xl.M4_SHELL,xl.M5_SHELL):
            try:
                edge=xl.EdgeEnergy(z,shell)
                if 1<edge<profile.voltage_kV:
                    edges.append(edge)
            except ValueError:
                pass
    edges=np.unique(edges)
    e=(edges[:-1]+edges[1:])/2
    continuum=(profile.voltage_kV-e)/e*np.diff(edges)
    continuum*=transmission(4,1.848,profile.tube_be_um,e)*transmission(13,2.70,profile.filter_Al_um,e)
    total=continuum.sum()
    if total<=0:
        raise ValueError('source fully attenuated')
    target_z=xl.SymbolToAtomicNumber(profile.target)
    tube_lines=[]
    for name,code,en in line_data(target_z):
        strength=line_cs(target_z,code,profile.voltage_kV)
        if strength>0 and en<profile.voltage_kV:
            strength*=float(transmission(4,1.848,profile.tube_be_um,np.array([en]))[0]*transmission(13,2.70,profile.filter_Al_um,np.array([en]))[0])
            tube_lines.append((en,strength))
    frac=profile.tube_line_fraction if tube_lines and sum(v for _,v in tube_lines)>0 else 0
    fluence=continuum/total*(1-frac)
    if frac:
        scale=sum(v for _,v in tube_lines)
        e=np.r_[e,[en for en,_ in tube_lines]]
        fluence=np.r_[fluence,[frac*v/scale for _,v in tube_lines]]
    order=np.argsort(e)
    return e[order],fluence[order]


def detector_efficiency(profile, energy):
    energy=np.atleast_1d(energy)
    return transmission(4,1.848,profile.detector_be_um,energy)*(-np.expm1(-np.array([cross('CS_Total',14,float(e)) for e in energy])*2.33*profile.detector_si_um*1e-4))


def gaussian_bin_weights(edges,energy,fwhm):
    if fwhm<=0:
        raise ValueError('Gaussian FWHM must be positive')
    return np.maximum(np.diff(ndtr((edges-energy)/(fwhm/2.354820045))),0)


def _kernel_primitive(t,mu):
    a=np.abs(t)
    out=np.zeros_like(a)
    good=a>0
    out[good]=a[good]*exp1(mu*a[good])-np.expm1(-mu*a[good])/mu
    return np.sign(t)*out


def simulate(percent, profile=None, *, seed=0, poisson=True, closure='strict', legacy_al='reject'):
    p=profile or Profile()
    p.validate()
    if type(seed) is not int or seed<0 or type(poisson) is not bool:
        raise ValueError('seed must be a nonnegative integer and poisson a boolean')
    weights,provenance=composition(percent,closure,legacy_al)
    ein,fluence=source_spectrum(p,weights)
    # incident_photons_s refers to flux before this specified external air path.
    # Do not renormalize attenuation away.
    fluence=fluence*air_transmission(p,ein,p.incident_air_path_cm)
    mu0=mixture_mu(weights,ein)
    sinin=math.sin(math.radians(p.incident_angle_deg))
    sinout=math.sin(math.radians(p.exit_angle_deg))
    t=p.mass_thickness_g_cm2
    channels=np.arange(p.channels)
    energies=p.zero_keV+p.gain_keV_channel*channels
    edges=p.zero_keV+p.gain_keV_channel*(np.arange(p.channels+1)-.5)
    exposure=p.incident_photons_s*p.live_time_s*p.current_uA/p.reference_current_uA
    if p.secondary:
        # Log-spaced mass-depth cells; exact cell-average primary source, finite-slab E1 kernel.
        zedges=np.r_[0,np.geomspace(min(1e-8,t*1e-6),t,p.secondary_layers)]
        z=(zedges[1:]+zedges[:-1])/2
        dz=np.diff(zedges)
        a=mu0/sinin
        primary_depth=(np.exp(-a[:,None]*zedges[:-1])-np.exp(-a[:,None]*zedges[1:]))/(a[:,None]*dz)
    records=[]
    for symbol,wi in weights.items():
        atomic=xl.SymbolToAtomicNumber(symbol)
        for name,code,eline in line_data(atomic):
            cs=np.array([line_cs(atomic,code,float(e)) for e in ein])
            excitation=fluence*cs*wi/sinin
            if excitation.sum()<=0:
                continue
            muline=float(mixture_mu(weights,[eline])[0])
            attenuation=mu0/sinin+muline/sinout
            factor=-np.expm1(-attenuation*t)/attenuation
            primary=float(np.dot(excitation,factor))
            depth=np.dot(excitation,primary_depth) if p.secondary else None
            records.append({'element':symbol,'Z':atomic,'line':name,'code':code,'energy_keV':eline,'mu':muline,'primary_emitted':primary,'secondary_emitted':0.0,'depth':depth})
    if p.secondary:
        # Isotropic, homogeneous plane slab, exactly one inter-element re-excitation.
        # H(z,z')=0.5 E1(mu_j |z-z'|); integrate each source cell analytically.
        for parent in records:
            mu=parent['mu']
            kernel=.5*(_kernel_primitive(zedges[1:][None,:]-z[:,None],mu)-_kernel_primitive(zedges[:-1][None,:]-z[:,None],mu))
            local_flux=kernel@parent['depth']
            for daughter in records:
                if daughter['energy_keV']>=parent['energy_keV']:
                    continue
                cs=line_cs(daughter['Z'],daughter['code'],parent['energy_keV'])
                if cs<=0:
                    continue
                emit=weights[daughter['element']]*cs*float(np.dot(local_flux,np.exp(-daughter['mu']*z/sinout)*dz))
                daughter['secondary_emitted']+=emit
    components={k:np.zeros(p.channels) for k in ('primary','secondary','rayleigh','compton','escape','background')}
    lost={'primary':0.0,'secondary':0.0,'rayleigh':0.0,'compton':0.0,'escape':0.0}
    before_window=0.0
    def deposit(energy,amplitude,component):
        nonlocal before_window
        if amplitude<=0:
            return
        eff=float(detector_efficiency(p,[energy])[0]*air_transmission(p,[energy],p.exit_air_path_cm)[0])
        amplitude*=eff
        before_window+=amplitude
        escape=p.escape_fraction if energy>xl.EdgeEnergy(14,xl.K_SHELL) else 0.0
        main=gaussian_bin_weights(edges,energy,float(p.fwhm_keV(energy)))
        components[component]+=amplitude*(1-escape)*main
        lost[component]+=amplitude*(1-escape)*max(0,1-main.sum())
        if escape:
            esc_energy=energy-xl.LineEnergy(14,xl.KA1_LINE)
            esc=gaussian_bin_weights(edges,esc_energy,float(p.fwhm_keV(esc_energy)))
            components['escape']+=amplitude*escape*esc
            lost['escape']+=amplitude*escape*max(0,1-esc.sum())
    for record in records:
        for component,key in [('primary','primary_emitted'),('secondary','secondary_emitted')]:
            deposit(record['energy_keV'],record[key]*exposure*p.solid_angle/(4*np.pi),component)
    if p.scatter:
        theta=math.radians(p.scatter_angle_deg)
        escat=ein/(1+ein/510.99895*(1-math.cos(theta)))
        for kind,out_energy,fn in [('rayleigh',ein,'DCS_Rayl'),('compton',escat,'DCS_Compt')]:
            scatter_cs=sum(w*np.array([getattr(xl,fn)(xl.SymbolToAtomicNumber(s),float(e),theta) for e in ein]) for s,w in weights.items())
            denom=mu0/sinin+mixture_mu(weights,out_energy)/sinout
            amount=fluence*scatter_cs/sinin*(-np.expm1(-denom*t))/denom*exposure*p.solid_angle
            for energy,value in zip(out_energy,amount):
                deposit(float(energy),float(value),kind)
    components['background'][:]=p.background_counts_channel
    expected=sum(components.values())
    if not np.isfinite(expected).all() or np.any(expected<0) or expected.max()>1e12:
        raise ValueError('invalid or excessive simulated counts')
    rng=np.random.default_rng(seed)
    counts=rng.poisson(expected) if poisson else expected.copy()
    lines=[{k:v for k,v in r.items() if k not in ('depth','mu','Z','code')} for r in records]
    warnings=[
        'Synthetic model output; not real-device ground truth or proof of 95%/5% accuracy',
        'Source: normalized Kramers-like continuum and assumed tube-line fraction; absolute flux is uncalibrated',
        'Homogeneous plane-parallel sample; mineral grain size, roughness, moisture and heterogeneity not separately modeled',
        'Single-scatter and at most second-generation fluorescence; no tertiary fluorescence, multiple scattering, pulse pile-up or dead-time model',
        'Escape fraction is an assumed effective parameter, not a recovered crystal geometry',
        'No empirical matrix correction or response profile has been fitted from the unpaired measured spectra',
        'Line set: available individual K/L/M transitions at >=1 keV; sub-keV fluorescence omitted; source grid starts at 1 keV',
        'Air attenuation uses xraylib dry-air mixture and assumed path/density; zero path does not establish vacuum conditions',
    ]+provenance['notes']
    support=element_support(p,provenance['original_percent'].keys()-{'Als','Alt'} | weights.keys())
    unsupported=[s for s,r in support['elements'].items() if r['status']!='structurally_supported_unvalidated']
    if unsupported:
        warnings.append('Composition labels are not evidence of observed elements; review structural support for: '+', '.join(sorted(unsupported)))
    if not p.secondary:
        warnings.append('Secondary fluorescence disabled; not a complete matrix-enhancement model')
    if min(energies)>1:
        warnings.append('Some low-energy lines may fall outside the recorded energy window')
    return {'schema':'competition-fp-spectrum/0.1','software_version':VERSION,'xraylib_version':xl.__version__,
            'synthetic':True,'hardware_validated':False,'axis':'channel','signal_unit':'counts',
            'channel':channels.tolist(),'energy_keV':energies.tolist(),'expected_counts':expected.tolist(),
            'counts':counts.tolist(),'components_expected_counts':{k:v.tolist() for k,v in components.items()},
            'profile':asdict(p),'composition':provenance,'lines':lines,'seed':seed,'poisson':poisson,
            'detected_signal_before_window_counts':before_window,'outside_window_counts':lost,
            'warnings':warnings,'element_support':support,
            'secondary_model':'finite-slab mass-depth E1 kernel, one fluorescence re-excitation' if p.secondary else 'disabled'}
