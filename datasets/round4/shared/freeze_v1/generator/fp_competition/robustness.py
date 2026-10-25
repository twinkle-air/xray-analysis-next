"""Area-preserving channel-space views, not a physical calibration or a deconvolution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve
from scipy.special import ndtr


def broaden_channels(signal,extra_fwhm_channels):
    y=np.asarray(signal,dtype=float)
    if y.ndim!=1 or not 64<=len(y)<=8192 or not np.isfinite(y).all() or np.any(y<0):
        raise ValueError('Signal requires 64..8192 finite nonnegative channels')
    if isinstance(extra_fwhm_channels,bool) or not isinstance(extra_fwhm_channels,(int,float)) or not np.isfinite(extra_fwhm_channels) or not 0<=extra_fwhm_channels<=64:
        raise ValueError('Additional FWHM must be in [0,64] channels')
    if extra_fwhm_channels==0:
        return y.copy(),{'extra_fwhm_channels':0,'input_sum':float(y.sum()),'output_sum':float(y.sum()),'outside_window_signal':0.,'kernel_omitted_mass':0.,'budget_residual':0.}
    sigma=extra_fwhm_channels/2.354820045
    radius=max(1,int(np.ceil(8*sigma)))
    dx=np.arange(-radius,radius+1)
    kernel=ndtr((dx+.5)/sigma)-ndtr((dx-.5)/sigma)
    omitted=max(0.,1-float(kernel.sum()))
    full=fftconvolve(y,kernel,mode='full')
    result=np.maximum(full[radius:radius+len(y)],0.)
    outside=float(np.maximum(full[:radius],0).sum()+np.maximum(full[radius+len(y):],0).sum())
    # Signal that leaves the window is counted explicitly, never folded back or re-normalized.
    return result,{'extra_fwhm_channels':float(extra_fwhm_channels),'input_sum':float(y.sum()),
                   'output_sum':float(result.sum()),'outside_window_signal':outside,'kernel_omitted_mass':omitted,
                   'budget_residual':float(y.sum()-result.sum()-outside-y.sum()*omitted)}


def read_channel_signal(path):
    path=Path(path)
    raw=path.read_bytes()
    if path.suffix.lower() in ('.pu','.txt'):
        rows=raw.decode('utf-8-sig').splitlines()
        if len(rows) not in (2048,2050):
            raise ValueError('PU/TXT needs 2048 signal rows and optionally two preserved footer rows')
        y=np.array([float(s) for s in rows[:2048]])
        info={'signal_unit':'unknown','synthetic':False,'synthetic_status_basis':'User states these PU files are measured; file has no type tag',
              'uninterpreted_footer':rows[2048:],'axis':'channel','channel_index_origin_assumption':0}
    elif path.suffix.lower()=='.json':
        def reject(value):
            raise ValueError('Nonfinite JSON '+value)
        def pairs(items):
            value={}
            for key,item in items:
                if key in value:
                    raise ValueError('Duplicate JSON key '+key)
                value[key]=item
            return value
        data=json.loads(raw.decode('utf-8-sig'),parse_constant=reject,object_pairs_hook=pairs)
        if not isinstance(data,dict):
            raise ValueError('Channel JSON must be an object')
        if data.get('axis')!='channel':
            raise ValueError('Only channel spectra supported; do not silently reinterpret energy axes')
        y=np.asarray(data.get('counts'),dtype=float)
        x=data.get('x',data.get('channel'))
        if x is not None and (len(x)!=len(y) or not np.array_equal(np.asarray(x),np.arange(len(y)))):
            raise ValueError('Expected contiguous zero-based channels')
        if 'synthetic' in data and type(data['synthetic']) is not bool:
            raise ValueError('synthetic must be a boolean when supplied')
        if data.get('signal_unit','unknown') not in ('counts','counts/s','unknown'):
            raise ValueError('Unknown signal-unit declaration')
        info={'signal_unit':data.get('signal_unit','unknown'),'synthetic':data.get('synthetic'),
              'synthetic_status_basis':'source JSON declaration or unknown','axis':'channel','uninterpreted_footer':[]}
    else:
        raise ValueError('Input must be PU/TXT or channel JSON')
    broaden_channels(y,0)
    return y,dict(info,source=str(path.resolve()),source_sha256=hashlib.sha256(raw).hexdigest())


def integrate_channel_feature(signal,left,right,side_bins=3):
    """Local signal integral with flank-based linear baseline; no Gaussian peak shape."""
    y,_=broaden_channels(signal,0)
    if type(left) is not int or type(right) is not int or type(side_bins) is not int or not 0<=left<right<=len(y) or side_bins<1 or right-left<2*side_bins+3:
        raise ValueError('Invalid integration region')
    x=np.arange(left,right,dtype=float);values=y[left:right]
    xl=float(x[:side_bins].mean());xr=float(x[-side_bins:].mean())
    yl=float(values[:side_bins].mean());yr=float(values[-side_bins:].mean())
    background=yl+(yr-yl)*(x-xl)/(xr-xl)
    return {'roi_start_channel':left,'roi_end_exclusive':right,'side_bins':side_bins,
            'net_integral':float((values-background).sum()),'total_integral':float(values.sum()),
            'background_integral':float(background.sum()),'negative_background':bool(np.any(background<0)),
            'method':'Fixed channel ROI; linear baseline from flanks; no Gaussian shape assumption',
            'limitations':['Side bands must be free of substantial interfering peaks',
                           'Overlapped elemental contributions are not separated; integral is not concentration',
                           'ROI choices are analysis assumptions, not independently calibrated energy intervals']}


def write_views(signal,out,widths=(0.,6.,10.),source_info=None):
    if __package__:
        from .core import VERSION
    else:
        from core import VERSION
    if len(widths)!=len(set(widths)) or not 1<=len(widths)<=12:
        raise ValueError('Use 1..12 distinct channel-space widths')
    prepared=[broaden_channels(signal,width) for width in widths]
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':'channel-robustness-views/0.1','software_version':VERSION,'source':source_info or {},
              'calibration_verified':False,'physical_correction':False,'status':'complete','views':[],
              'quantitative_source_policy':'Use the unchanged original for quantitative work; these views are for sensitivity/shape analysis',
              'warnings':['Derived broadened views; original measurement is unchanged',
                          'No energy calibration, no recovered detector response, no independently measured physical resolution',
                          'Additional smoothing introduces channel correlations; do not treat processed bins as independent Poisson counts',
                          'Broadening reduces peak-shape dependence but also reduces separation of neighboring lines',
                          'All views of one source must stay in its original train/validation/test group',
                          'This operation does not demonstrate more accurate elemental concentrations']}
    for index,((view,budget),width) in enumerate(zip(prepared,widths)):
        name=f'view-{index:02d}.json'
        data={'axis':'channel','signal_unit':manifest['source'].get('signal_unit','unknown'),
              'synthetic':manifest['source'].get('synthetic'),'derived':True,'physical_correction':False,
              'counts_kind':('smoothed_counts' if width>0 else 'counts') if manifest['source'].get('signal_unit')=='counts' else 'unknown',
              'channel':list(range(len(view))),'signal':view.tolist(),'budget':budget,
              'processing':'Gaussian channel broadening; original calibration remains unknown'}
        path=out/name;path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        manifest['views'].append({'file':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**budget})
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return out
