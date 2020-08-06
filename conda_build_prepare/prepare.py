#!/usr/bin/env python3

import json
import os
import re
import subprocess
import shutil
import yaml
import datetime
import platform

from git_helpers import remotes, extract_github_user, _call_custom_git_cmd
from travis import get_travis_slug

from collections import OrderedDict

#import conda

def get_local_channels():
    local_channels = OrderedDict()

    travis_slug = get_travis_slug()
    if travis_slug:
        user = extract_github_user(travis_slug)
        assert user, travis_slug
        local_channels[user] = None

    for url in remotes('fetch').values():
        user = extract_github_user(url)
        if user:
            local_channels[user] = None

    return tuple(local_channels.keys())


# condarc_$OS has precedence, if exists and '$OS' matches the current OS
# (it can be condarc_linux, condarc_macos or condarc_windows)
def get_package_condarc(recipe_dir):
    cur_os = platform.system().lower().replace('darwin', 'macos')
    condarc = os.path.join(recipe_dir, 'condarc')
    condarc_os = condarc + '_' + cur_os

    if os.path.exists(condarc_os):
        return condarc_os
    elif os.path.exists(condarc):
        return condarc
    else:
        return None


def write_metadata(package_dir):
    metadata_file = os.path.join(package_dir, 'recipe_append.yaml')

    metadata = {
        'extra': {
            'build_type': 'local'
        }
    }

    # Try and get the recipe metadata from git
    def _try_to_get_git_output(cmd_string):
        try:
            return _call_custom_git_cmd('.', cmd_string)
        except:
            return 'ERROR'

    metadata['extra']['recipe'] = {
        'repo':     _try_to_get_git_output('remote get-url origin'),
        'branch':   _try_to_get_git_output('rev-parse --abbrev-ref HEAD'),
        'commit':   _try_to_get_git_output('rev-parse HEAD'),
        'describe': _try_to_get_git_output('describe --long'),
        'date':     datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S'),
    }

    # Fill in metadata from travis environment
    if os.environ.get('TRAVIS', 'false') == 'true':
        metadata['extra']['build_type'] = 'travis',
        metadata['extra']['travis'] = {
            'job_id': int(os.environ.get('TRAVIS_JOB_ID', repr(-1))),
            'job_num': os.environ.get('TRAVIS_JOB_NUMBER', repr(-1)),
            'type': os.environ.get('TRAVIS_EVENT_TYPE'),
        }
        # Override details from git with data from travis
        metadata['extra']['recipe'] = {
            'repo': 'https://github.com/' + get_travis_slug(),
            'branch': os.environ.get('TRAVIS_BRANCH', '?'),
            'commit': os.environ.get('TRAVIS_COMMIT', '?'),
        }

    toolchain_arch = os.environ.get('TOOLCHAIN_ARCH')
    if toolchain_arch is not None:
        metadata['extra']['toolchain_arch'] = toolchain_arch

    package_condarc = get_package_condarc(package_dir)
    if package_condarc is not None:
        with open(package_condarc, 'r') as condarc_file:
            condarc = yaml.safe_load(condarc_file)
        metadata['extra']['condarc'] = condarc

    with open(metadata_file, "w") as meta:
        yaml.safe_dump(metadata, meta)


def prepare_directory(package_dir, dest_dir):
    assert os.path.exists(package_dir)
    assert not os.path.exists(dest_dir)

    shutil.copytree(package_dir, dest_dir)

    # Prescript

    prescript_name = f"prescript.{os.environ.get('TOOLCHAIN_ARCH') or ''}.sh"
    prescript_path = os.path.join(dest_dir, prescript_name)
    if os.path.exists(prescript_path):
        print('\nPrescript file found! Executing...\n')
        os.chmod(prescript_path, 0o0777)
        subprocess.check_call([prescript_path], env=os.environ, cwd=dest_dir)
        print('\nFinished executing prescript.\n')

    write_metadata(dest_dir)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
