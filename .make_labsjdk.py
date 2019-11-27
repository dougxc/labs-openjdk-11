#
# ----------------------------------------------------------------------------------------------------
#
# Copyright (c) 2019, Oracle and/or its affiliates. All rights reserved.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# This code is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 only, as
# published by the Free Software Foundation.
#
# This code is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# version 2 for more details (a copy is included in the LICENSE file that
# accompanied this code).
#
# You should have received a copy of the GNU General Public License version
# 2 along with this work; if not, write to the Free Software Foundation,
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
# or visit www.oracle.com if you need additional information or have any
# questions.
#
# ----------------------------------------------------------------------------------------------------

#pylint: disable=missing-docstring
#pylint: disable=line-too-long
#pylint: disable=invalid-name
from __future__ import print_function
import glob, os, pipes, time, subprocess, posixpath, zipfile, tarfile
from os.path import join, exists, abspath, dirname, relpath
from argparse import ArgumentParser

def abort(code_or_message):
    raise SystemExit(code_or_message)

def timestamp():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(timestamp() + ': ' + str(msg))

def check_call(args):
    log(' '.join(map(pipes.quote, args)))
    return subprocess.check_call(args)

def call(args):
    log(' '.join(map(pipes.quote, args)))
    return subprocess.call(args)

def check_output(args):
    log(' '.join(map(pipes.quote, args)))
    return subprocess.check_output(args)

def get_java_version(version_numbers_file):
    values = {}
    with open(version_numbers_file) as fp:
        for l in fp:
            line = l.strip()
            if line and not line.startswith('#'):
                key, value = [e.strip() for e in line.split('=', 1)]
                values[key] = value
    return '{}.{}.{}'.format(values['DEFAULT_VERSION_FEATURE'], values['DEFAULT_VERSION_INTERIM'], values['DEFAULT_VERSION_UPDATE'])

def posix_relpath(path, start=os.curdir):
    """
    Converts `path` to a posix path relative to `start` for use by posix tools.
    """
    return posixpath.join(*relpath(path, start=start).split(os.sep))

def main():
    parser = ArgumentParser()
    parser.add_argument('--jvmci-version', action='store', help='JVMCI version (e.g., 19.3-b03)', required=True)
    parser.add_argument('--ci-platform', action='store', help='target platform in CI terminology (e.g, darin-amd64)', required=True)
    parser.add_argument('--target-dir', action='store', help='directory in which the labsjdk image will be created', required=True)
    parser.add_argument('--clean', action='store_true', help='delete build directory after creating labsjdk', required=True)
    parser.add_argument('--conf', action='store', help='configuration of the build', required=True)

    opts = parser.parse_args()
    jvmci_version = opts.jvmci_version
    target_dir = abspath(opts.target_dir)
    if exists(target_dir):
        abort(target_dir + ' exists - please remove and run again')
    os.makedirs(target_dir)

    my_dir = dirname(abspath(__file__))
    version_numbers_file = join(my_dir, 'make', 'autoconf', 'version-numbers')
    java_version = get_java_version(version_numbers_file)

    # Get build number from tags
    tag_prefix = 'jdk-' + java_version + '+'
    build_nums = [int(line[len(tag_prefix):]) for line in check_output(['git', '-C', my_dir, 'tag']).split() if line.startswith(tag_prefix)]
    build_num = sorted(build_nums, reverse=True)[0]

    debug_level_qualifier = '' if 'debug' not in opts.conf else '-fastdebug'
    ce_or_ee = 'ce' if 'open' in opts.conf else 'ee'
    archive_prefix = 'labsjdk-{}-{}+{}-jvmci-{}{}'.format(ce_or_ee, java_version, build_num, jvmci_version, debug_level_qualifier)
    install_prefix = 'labsjdk-{}-{}-jvmci-{}{}'.format(ce_or_ee, java_version, jvmci_version, debug_level_qualifier)

    debug_qualifier = '' if 'debug' not in opts.conf else '-debug'
    jdk_bundle_ext = '.zip' if 'windows' in opts.conf else '.tar.gz'
    bundles = glob.glob(join(my_dir, 'build', opts.conf, 'bundles', '*_bin' + debug_qualifier + jdk_bundle_ext)) + \
              glob.glob(join(my_dir, 'build', opts.conf, 'bundles', '*_bin-static-libs' + debug_qualifier + '.tar.gz'))

    for bundle in bundles:
        log('Extracting {} in {}'.format(bundle, target_dir))
        if bundle.endswith('.zip'):
            with zipfile.ZipFile(bundle) as zf:
                zf.extractall(target_dir)
        else:
            with tarfile.open(bundle, 'r:gz') as tf:
                tf.extractall(target_dir)

    if opts.clean:
        conf_build_dir = join(my_dir, 'build', opts.conf)
        # Use `rm -rf` instead of shutil.rmtree to avoid problems with
        # read-only files on Windows (https://stackoverflow.com/questions/1889597/deleting-directory-in-python)
        check_call(['rm', '-rf', conf_build_dir])

    def _get_single_entry(directory):
        entries = os.listdir(directory)
        assert len(entries) == 1, 'Expected single entry in {} but got {} entries: {}'.format(abspath(directory), len(entries), entries)
        return entries[0]

    if 'debug' in opts.conf:
        jdk_dir_parent = join(target_dir, _get_single_entry(target_dir))
    else:
        jdk_dir_parent = target_dir

    jdk_name = _get_single_entry(jdk_dir_parent)
    if 'debug' in opts.conf and 'darwin' in opts.ci_platform:
        # Create missing Contents/Home structure
        contents_dir = join(jdk_dir_parent, install_prefix, 'Contents')
        os.makedirs(contents_dir)
        os.rename(join(jdk_dir_parent, jdk_name), join(contents_dir, 'Home'))
    else:
        os.rename(join(jdk_dir_parent, jdk_name), join(jdk_dir_parent, install_prefix))
    java_home = join(jdk_dir_parent, install_prefix)
    if 'darwin' in opts.ci_platform:
        java_home += '/Contents/Home'

    archive_path = join(target_dir, archive_prefix + '-{}.tar.gz'.format(opts.ci_platform))
    check_call(['tar', 'czf', posix_relpath(archive_path), '-C', posix_relpath(jdk_dir_parent), posixpath.join('.', install_prefix)])
    if 'windows' in opts.conf:
        subprocess.check_call(['mklink', '/D', join(target_dir, 'java_home'), join(target_dir, java_home)], shell=True)
    else:
        check_call(['ln', '-s', join(target_dir, java_home), join(target_dir, 'java_home')])

if __name__ == '__main__':
    main()
