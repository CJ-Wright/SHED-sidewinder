import re
from pprint import pprint
import numpy as np
import os
from bluesky.utils import new_uid
import time

files_types = ['.gsa', '.dat']

gsas_parser_list = [
    ('bt_wavelength', 0, 'Wavelength: (.+?) Angstrom',
     ('Wavelength:', 'Angstrom'), float),
    ('run', 0, 'Sample Run: (.+?) ', ('Sample Run: ',), int),
    ('IPTS', 7, 'IPTS-(.+?)', ('IPTS-',), int),
    ('primary flight path', 11, 'Primary flight path (.+?)m',
     ('Primary flight path ', 'm'), float),
    ('total flight path', 12, 'Total flight path   (.+?)m',
     ('Total flight path   ', 'm'), float),
    ('tth', 12, 'tth   (.+?)deg', ('tth   ', 'deg'), float),
]


def gsas_subparser(string):
    output = {}
    gsas_data = string.split('\n')[:14]
    gsas_data = [s.strip('# ').strip() for s in gsas_data]
    for name, line, re_string, strips, dtype in gsas_parser_list:
        re_res = re.search(re_string, gsas_data[line])
        if re_res:
            data = re_res.group()
            for strip in strips:
                data = data.strip(strip)
            data = data.strip()
            if data:
                data = dtype(data)
                output[name] = data
    output.update({'wavelength unit': 'A',
                   'primary flight path unit': 'm',
                   'total flight path unit': 'm',
                   'tth unit': 'deg'
                   })

    return output


def parse(file_dir):
    gsas_root = os.path.join(file_dir, 'GSAS')
    gsas_files = [f for f in os.listdir(gsas_root) if f.endswith('.gsa')]
    for gsas_file in gsas_files:
        suid = new_uid()
        start_doc = {'facility': 'NOMAD',
                     'uid': suid,
                     'sideloaded': True,
                     'time': time.time(),
                     'filename': os.path.splitext(gsas_file)[0]}

        full_prof_root = os.path.join(file_dir, 'fullprof')

        a = gsas_file.split('_')
        with open(os.path.join(gsas_root, gsas_file), 'r') as f:
            start_doc.update(gsas_subparser(f.read()))
        start_doc['sample_name'] = a[1]
        start_doc['composition_string'] = a[1]
        if 'gas' in a:
            start_doc.update({'gas': a[3]})
        if 'dry' in a:
            start_doc.update({'dry': True})
        if 'C' in a[6]:
            start_doc.update({'temperature': a[6].replace('C', '')})
        start_doc.update({'cycle': a[-1].split('cycle')[1].split('.')[0]})
        yield 'start', start_doc

        for bank in range(6):
            duid = new_uid()
            descriptor_doc = {'uid': duid,
                              'name': 'bank {}'.format(bank),
                              'run_start': suid,
                              'data_keys':
                                  {'tof': {'source': 'file',
                                           'dtype': 'array',
                                           'unit': 'time'},
                                   'intensity': {'source': 'file',
                                                 'dtype': 'array',
                                                 'unit': 'arb'},
                                   'error': {'source': 'file',
                                             'dtype': 'array',
                                             'unit': 'arb'}
                                   },
                              'time': time.time()}
            yield 'descriptor', descriptor_doc
            full_prof_file_name = gsas_file.replace('.gsa',
                                                    '-{}.dat'.format(bank))
            tof, i, err = np.loadtxt(os.path.join(full_prof_root,
                                                  full_prof_file_name)).T
            event = {'uid': new_uid(),
                     'descriptor': duid,
                     'filled': {'tof': True,
                                'intensity': True,
                                'error': True},
                     'data': {'tof': tof, 'intensity': i, 'error': err},
                     'timestamps': {'tof': time.time(),
                                    'intensity': time.time(),
                                    'error': time.time()},
                     'seq_num': i,
                     'time': time.time(),
                     }
            yield 'event', event
        yield 'stop', {'uid': new_uid(), 'run_start': suid,
                       'time': time.time()}


if __name__ == '__main__':
    for n, d in parse('/home/christopher/dev/17ly_NOMADpipeline/data'):
        print(n)
        pprint(d)