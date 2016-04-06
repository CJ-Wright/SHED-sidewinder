import numpy as np
from uuid import uuid4
import os
from sidewinder_spec.utils.parsers import parse_spec_file, \
    parse_tif_metadata, parse_tif_metadata, parse_run_config
from metadatastore.api import insert_event, insert_run_start, insert_run_stop, \
    insert_descriptor
from filestore.api import insert_resource, insert_datum, register_handler
from filestore.api import db_connect as fs_db_connect
from metadatastore.api import db_connect as mds_db_connect

fs_db_connect(
    **{'database': 'data-processing-dev', 'host': 'localhost', 'port': 27017})
mds_db_connect(
    **{'database': 'data-processing-dev', 'host': 'localhost', 'port': 27017})


def get_tiffs(run_folder):
    # Load all the metadata files in the folder
    tiff_metadata_files = [os.path.join(run_folder, f) for f in
                           os.listdir(run_folder)
                           if f.endswith('.tif.metadata')]
    tiff_metadata_data = [parse_tif_metadata(f) for f in
                          tiff_metadata_files]

    # Sort the folder's data by time so we can have the start time
    timestamp_list = [f['timestamp'] for f in tiff_metadata_data]

    # read in all the image file names
    tiff_file_names = [f[:-9] for f in tiff_metadata_files]

    # sort remaining data by time
    sorted_tiff_metadata_data = [x for (y, x) in sorted(
        zip(timestamp_list, tiff_metadata_data))]
    sorted_tiff_file_names = [x for (y, x) in sorted(
        zip(timestamp_list, tiff_file_names))]
    return sorted_tiff_metadata_data, sorted_tiff_file_names, timestamp_list


def temp_dd_loader(run_folder, spec_data, section_start_times, run_kwargs,
                   dry_run=True):
    # Get the calibration/background header uid, if it exists or load it
    cal_hdrs = []
    background_hdrs = []
    for key in run_kwargs:
        try:
            cal_hdrs.append(
                general_loader(run_kwargs[key]['calibration_folder'],
                               spec_data, section_start_times, dry_run))
        # That part of the config file didn't have a calibration folder oh well
        except:
            pass
        try:
            background_hdrs.append(
                general_loader(run_kwargs[key]['background_folder'],
                               spec_data, section_start_times, dry_run))
        # That part of the config file didn't have a background folder oh well
        except KeyError:
            pass

    sorted_tiff_metadata_data, sorted_tiff_file_names, timestamp_list = get_tiffs(
        run_folder)

    # make subset of spec data for this run
    print(run_folder)
    ti = sorted_tiff_metadata_data[0]['time_from_date']

    # make a sub spec list which contains the spec section related to our data
    spec_start_idx = np.argmin(np.abs(section_start_times - ti))
    sub_spec = spec_data[spec_start_idx]
    assert len(cal_hdrs) > 0

    # 3. Create the run_start document.
    run_start_dict = dict(time=min(timestamp_list), scan_id=1,
                          beamline_id='11-ID-B',
                          uid=str(uuid4()),
                          is_calibration=False,
                          calibration=cal_hdrs,
                          background=background_hdrs,
                          run_type='temperature_dd',
                          run_folder=run_folder,
                          **run_kwargs)
    if dry_run:
        run_start_uid = run_start_dict['uid']
        print(run_start_dict)
    else:
        run_start_uid = insert_run_start(**run_start_dict)
        print(run_start_uid)

    data_keys1 = {'I0': dict(source='IO', dtype='number'),
                  'img': dict(source='det', dtype='array',
                              shape=(2048, 2048),
                              external='FILESTORE:'),
                  'detz': dict(source='detz', dtype='number'),
                  'metadata': dict(source='metadata', dtype='dict')}

    data_keys2 = {'T': dict(source='T', dtype='number'),}

    descriptor1_dict = dict(run_start=run_start_uid, data_keys=data_keys1,
                            time=0., uid=str(uuid4()))
    descriptor2_dict = dict(run_start=run_start_uid, data_keys=data_keys2,
                            time=0., uid=str(uuid4()))
    if dry_run:
        descriptor1_uid = descriptor1_dict['uid']
        descriptor2_uid = descriptor1_dict['uid']
        print descriptor1_dict
        print descriptor2_dict
    else:
        descriptor1_uid = insert_descriptor(**descriptor1_dict)
        descriptor2_uid = insert_descriptor(**descriptor2_dict)
        # print descriptor1_uid
        # print descriptor2_uid

    # insert all the temperature data
    temperature_data = [scan['T'] for scan in sub_spec]
    time_data = [scan['time_from_date'] for scan in sub_spec]

    for idx, (temp, t) in enumerate(zip(temperature_data, time_data)):
        event_dict = dict(descriptor=descriptor2_uid, time=t, data={'T': temp},
                          uid=str(uuid4()),
                          timestamps={'T': t}, seq_num=idx)

        # print event_dict
        if not dry_run:
            insert_event(**event_dict)

    # insert the images
    I0 = [scan['I00'] for scan in sub_spec]

    for idx, (img_name, I, timestamp, metadata) in enumerate(
            zip(sorted_tiff_file_names, I0, time_data,
                sorted_tiff_metadata_data)):
        fs_uid = str(uuid4())
        dz = float(os.path.split(os.path.splitext(img_name)[0])[-1][1:3])
        data = {'img': fs_uid, 'I0': I, 'detz': dz, 'metadata': metadata}
        timestamps = {'img': timestamp, 'I0': timestamp, 'detz': timestamp,
                      'metadata': timestamp}
        event_dict = dict(descriptor=descriptor1_uid, time=timestamp,
                          data=data,
                          uid=str(uuid4()), timestamps=timestamps, seq_num=idx,
                          )
        # print event_dict
        if not dry_run:
            resource = insert_resource('TIFF', img_name)
            insert_datum(resource, fs_uid)
            insert_event(**event_dict)

    if dry_run:
        print "Run Stop goes here"
    else:
        insert_run_stop(run_start=run_start_uid, time=np.max(timestamps),
                        uid=str(uuid4()))
    return run_start_uid


def dd_sample_changer_loader(run_folder, spec_data, section_start_times,
                             run_kwargs):
    pass


def calibration_loader(run_folder, spec_data, section_start_times,
                       run_kwargs, dry_run=True):
    # Load all the metadata files in the folder
    tiff_metadata_files = [os.path.join(run_folder, f) for f in
                           os.listdir(run_folder)
                           if f.endswith('.tif.metadata')]
    tiff_metadata_data = [parse_tif_metadata(f) for f in
                          tiff_metadata_files]

    sorted_tiff_metadata_data, sorted_tiff_file_names, timestamp_list = get_tiffs(
        run_folder)

    # make subset of spec data for this run
    ti = sorted_tiff_metadata_data[0]['time_from_date']

    # make a sub spec list which contains the spec section related to our data
    spec_start_idx = np.argmin(np.abs(section_start_times - ti))
    sub_spec = spec_data[spec_start_idx]

    poni_files = [os.path.join(run_folder, f) for f in
                  os.listdir(run_folder) if f.endswith('.poni')]
    poni_uuids = []

    for f in poni_files:
        fs_uid = str(uuid4())
        if not dry_run:
            resource = insert_resource('pyFAI-geo', f)
            insert_datum(resource, fs_uid)
        poni_uuids.append(fs_uid)

    # 3. Create the run_start document.
    # Note we need to associate any background run headers with this run header
    run_start_dict = dict(time=min(timestamp_list), scan_id=1,
                          beamline_id='11-ID-B',
                          group='Zhou',
                          owner='CJ-Wright',
                          project='PNO',
                          uid=str(uuid4()),
                          is_calibration=True,
                          poni=poni_uuids,  # Filestore save all the Poni files
                          run_folder=run_folder,
                          run_type='calibration',
                          **run_kwargs)
    if dry_run:
        run_start_uid = run_start_dict['uid']
        print run_start_dict
    else:
        run_start_uid = insert_run_start(**run_start_dict)
        print run_start_uid

    data_keys1 = {'I0': dict(source='IO', dtype='number'),
                  'img': dict(source='det', dtype='array',
                              shape=(2048, 2048),
                              external='FILESTORE:'),
                  'detz': dict(source='detz', dtype='number'),
                  'metadata': dict(source='metadata', dtype='dict')}

    descriptor1_dict = dict(run_start=run_start_uid, data_keys=data_keys1,
                            time=0., uid=str(uuid4()))
    if dry_run:
        descriptor1_uid = descriptor1_dict['uid']
        print descriptor1_dict
    else:
        descriptor1_uid = insert_descriptor(**descriptor1_dict)
        # print descriptor1_uid

    # insert all the temperature data
    time_data = [scan['time_from_date'] for scan in sub_spec]

    # insert the images
    I0 = [scan['I00'] for scan in sub_spec]

    for idx, (img_name, I, timestamp) in enumerate(
            zip(sorted_tiff_file_names, I0, time_data)):
        fs_uid = str(uuid4())
        dz = run_kwargs['general']['distance']
        data = {'img': fs_uid, 'I0': I, 'detz': dz}
        timestamps = {'img': timestamp, 'detz': timestamp, 'I0': timestamp,
                      'metadata': timestamp}
        event_dict = dict(descriptor=descriptor1_uid, time=timestamp,
                          data=data,
                          uid=str(uuid4()), timestamps=timestamps, seq_num=idx)
        # print event_dict
        if not dry_run:
            resource = insert_resource('TIFF', img_name)
            insert_datum(resource, fs_uid)
            insert_event(**event_dict)

    if dry_run:
        print "Run Stop goes here"
    else:
        insert_run_stop(run_start=run_start_uid, time=np.max(timestamps),
                        uid=str(uuid4()))
        print('Calibration inserted')
    return run_start_uid


run_loaders = {
    'temp_dd': temp_dd_loader,
    'dd_sample_changer': dd_sample_changer_loader,
    'calibration': calibration_loader
}


def general_loader(run_folder, spec_data, section_start_times, dry_run=True):
    from databroker import db
    config_file = os.path.join(run_folder, 'config.txt')

    # To load a folder we need to make certain it has a config file
    # and is not already in the DB
    if os.path.exists(config_file) and db(run_folder=run_folder) == []:
        print('loading {}'.format(run_folder))
        run_config = parse_run_config(config_file)
        if run_config and 'general' in run_config.keys():
            loader = run_loaders[run_config['general']['loader_name']]
            uid = loader(run_folder, spec_data, section_start_times,
                         run_config, dry_run)
            print('finished loading {} uid={}'.format(run_folder, uid))
            return uid
    elif db(run_folder=run_folder):
        print('{} is already loaded'.format(run_folder))
        return db(run_folder=run_folder)[0]['start']['uid']
    else:
        print('Not valid run folder, not in DB and no valid config file')
        return None
