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

import zipfile, tarfile, os, hashlib, stat, re, shutil, pipes, time, subprocess, posixpath
from os.path import join, exists, dirname, isdir, basename, getsize, abspath
from argparse import ArgumentParser

def abort(codeOrMessage):
    raise SystemExit(codeOrMessage)

def timestamp():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print timestamp() + ': ' + str(msg)

def check_call(args):
    log(' '.join(map(pipes.quote, args)))
    return subprocess.check_call(args)

def check_output(args):
    log(' '.join(map(pipes.quote, args)))
    return subprocess.check_output(args)

def create_archive(srcdir, arcpath, prefix):
    """
    Creates a compressed archive of a given directory.

    :param str srcdir: directory to archive
    :param str arcpath: path of file to contain the archive. The extension of `path`
           specifies the type of archive to create
    :param str prefix: the prefix to apply to each entry in the archive
    """

    def _taradd(arc, filename, arcname):
        arc.add(name=f, arcname=arcname, recursive=False)
    def _zipadd(arc, filename, arcname):
        arc.write(filename, arcname)

    if arcpath.endswith('.zip'):
        arc = zipfile.ZipFile(arcpath, 'w', zipfile.ZIP_DEFLATED)
        add = _zipadd
    elif arcpath.endswith('.tar'):
        arc = tarfile.open(arcpath, 'w')
        add = _taradd
    elif arcpath.endswith('.tgz') or arcpath.endswith('.tar.gz'):
        arc = tarfile.open(arcpath, 'w:gz')
        add = _taradd
    else:
        abort('unsupported archive kind: ' + arcpath)

    def onError(e):
        raise e
    for root, _, filenames in os.walk(srcdir, onerror=onError):
        for name in filenames:
            f = join(root, name)
            # Make sure files in the image are readable by everyone
            file_mode = os.stat(f).st_mode
            mode = stat.S_IRGRP | stat.S_IROTH | file_mode
            if isdir(f) or (file_mode & stat.S_IXUSR):
                mode = mode | stat.S_IXGRP | stat.S_IXOTH
            os.chmod(f, mode)
            arcname = prefix + os.path.relpath(f, srcdir)
            add(arc, f, arcname)

    arc.close()

def create_sha1(srcpath, dstpath):
    """
    Generates the SHA1 signature of `srcpath` and writes it to `dstpath`.
    """
    with open(srcpath, 'rb') as fp:
        d = hashlib.sha1()
        while True:
            buf = fp.read(4096)
            if not buf:
                break
            d.update(buf)
    with open(dstpath, 'w') as fp:
        fp.write(d.hexdigest())

def upload(local, scp_base_path, archive_prefix, ci_target):
    if local:
        os.chmod(local, 0664)
        name = basename(local)
        remote = posixpath.join(scp_base_path, 'jdk-candidates', name)
        log("Uploading {} to {}...".format(local, remote))
        check_call(['scp', local, remote])

        # Make candidate images available as dev versions so that pull requests can reference them
        dev_name = name.replace(archive_prefix, archive_prefix + '-dev')
        user_host, remote_dir = scp_base_path.split(':')
        check_call(['ssh', user_host, 'ln', '-f', '-s',
                         posixpath.join(remote_dir, 'jdk-candidates', name),
                         posixpath.join(remote_dir, dev_name)])
        if ci_target == 'deploy':
            log("Publishing {}...".format(local))
            check_call(['ssh', user_host, 'mv',
                             posixpath.join(remote_dir, 'jdk-candidates', name),
                             posixpath.join(remote_dir, name)])

def get_build_configuration(build_dir, prefix, jdk_debug_level):
    for name in os.listdir(build_dir):
        if name.startswith(prefix) and name.endswith(jdk_debug_level):
            return name
    abort('no entry starting with "{}" in {}: {}'.format(prefix, build_dir, os.listdir(build_dir)))

def get_java_version(version_numbers_file):
    values = {}
    with open(version_numbers_file) as fp:
        for l in fp:
            line = l.strip()
            if line and not line.startswith('#'):
                key, value = [e.strip() for e in line.split('=', 1)]
                values[key] = value
    return '{}.{}.{}'.format(values['DEFAULT_VERSION_FEATURE'], values['DEFAULT_VERSION_INTERIM'], values['DEFAULT_VERSION_UPDATE'])

if __name__ == '__main__':
    env = os.environ
    parser = ArgumentParser()
    parser.add_argument('--jvmci-version', action='store', help='JVMCI version (e.g., 19.3-b03)', required=True)
    parser.add_argument('--ci-arch', action='store', help='target architecture in CI terminology', default=env.get('CI_ARCH'), required='CI_ARCH' not in env)
    parser.add_argument('--ci-os', action='store', help='target OS in CI terminology', default=env.get('CI_OS'), required='CI_OS' not in env)
    parser.add_argument('--ci-target', action='store', help='purpose of CI job', choices=['gate', 'deploy'], default='gate')
    parser.add_argument('--jdk-arch', action='store', help='target architecture in JDK terminology', default=env.get('JDK_ARCH'), required='JDK_ARCH' not in env)
    parser.add_argument('--jdk-os', action='store', help='target OS in JDK terminology', default=env.get('JDK_OS'), required='JDK_OS' not in env)
    parser.add_argument('--make', action='store', help='GNU make executable', default=env.get('MAKE', 'make'))
    parser.add_argument('--images-dir', action='store', help='directory into which images are copied', required=True)
    parser.add_argument('--boot-jdk', action='store', help='value for --boot-jdk configure option', default=env.get('BOOT_JDK'), required='BOOT_JDK' not in env)
    parser.add_argument('--devkit', action='store', help='value for --devkit configure option', default=env.get('DEVKIT', ''))
    parser.add_argument('--clean-after-build', action='store_true', help='run "make clean" after building the image')
    parser.add_argument('--with-static-libs', action='store_true', help='build and include static libs in archive')
    parser.add_argument('--scp-base-path', action='store', help='scp path of remote labsjdk directory')
    parser.add_argument('--jdk-debug-level', action='store', help='value for --with-debug-level JDK config option', default='release')
    parser.add_argument('--java-home-link-target', action='store', help='symbolic link to create pointing to JAVA_HOME of built JDK')

    opts = parser.parse_args()
    jdk_debug_level = opts.jdk_debug_level
    jvmci_version = opts.jvmci_version
    images_dir = opts.images_dir
    is_closed = isdir('closed')
    if not exists(images_dir):
        os.makedirs(images_dir)
    images_dir = abspath(images_dir)

    version_numbers_file = join('make', 'autoconf', 'version-numbers')
    if is_closed:
        version_numbers_file = join('open', version_numbers_file)
    java_version = get_java_version(version_numbers_file)

    tag_prefix = 'jdk-' + java_version + '+'
    build_nums = [int(line[len(tag_prefix):]) for line in check_output(['git', '-C', ('open' if is_closed else '.'), 'tag']).split() if line.startswith(tag_prefix)]
    build_num = sorted(build_nums, reverse=True)[0]

    debug_level_qualifier = '' if jdk_debug_level == 'release' else '-' + jdk_debug_level
    ce_or_ee = 'ee' if is_closed else 'ce'
    archive_prefix = 'labsjdk-{}-{}+{}-jvmci-{}{}'.format(ce_or_ee, java_version, build_num, jvmci_version, debug_level_qualifier)
    install_prefix = 'labsjdk-{}-{}-jvmci-{}{}'.format(ce_or_ee, java_version, jvmci_version, debug_level_qualifier)
    archive = archive_prefix + '-{}-{}.tar.gz'.format(opts.ci_os, opts.ci_arch)

    if opts.ci_target == 'deploy':
        user_host, remote_dir = opts.scp_base_path.split(':')
        try:
            check_call(['ssh', user_host, 'test', '!' ,'-f',  posixpath.join(remote_dir, 'labsjdk', archive)])
        except subprocess.CalledProcessError as e:
            log(str(e))
            abort('Cannot deploy over existing binary at ' + posixpath.join(opts.scp_base_path, 'labsjdk', archive))

    configure_options = [
        "--with-debug-level=" + jdk_debug_level,
        "--enable-aot=no", # GR-10545
        "--with-jvm-features=graal",
        "--with-jvm-variants=server",
        "--disable-warnings-as-errors",
        "--with-boot-jdk=" + opts.boot_jdk,
        "--with-devkit=" + opts.devkit,
        "--with-zlib=bundled",
        "--with-version-build=" + str(build_num),
        "--with-version-opt=jvmci-" + jvmci_version + "-LTS", # JDK 11 is LTS

        # VERSION_IS_GA based on if VERSION_PRE has a value
        # See: make/autoconf/jdk-version.m4
        "--with-version-pre="
    ]
    if opts.ci_arch != 'aarch64':
        configure_options.append("--disable-precompiled-headers")
    if is_closed:
        configure_options.append("--disable-manpages") # Not included in OracleJDK11 binary
    if jdk_debug_level != 'release':
        configure_options.append("--with-native-debug-symbols=external")
    else:
        configure_options.append("--with-native-debug-symbols=none")

    saved_static_libs_dir = None

    # --enable-static-build is not supported for solaris
    if opts.with_static_libs and not opts.ci_os == 'solaris':
        # Build JDK with static libs
        check_call(["sh", "configure"] + configure_options + ["--enable-static-build"])
        check_call([opts.make, "CONF=" + jdk_debug_level, "images"])

        # Copy static libs dir out of built JDK image
        build_dir = join(os.getcwd(), 'build')
        configuration = get_build_configuration(build_dir, '{}-{}'.format(opts.jdk_os, opts.jdk_arch), jdk_debug_level)
        static_libs_dir = join(build_dir, configuration, 'images', 'jdk', 'lib', 'static')
        if not exists(static_libs_dir) or len(os.listdir(static_libs_dir)) == 0:
            abort("Static libs dir is empty: " + static_libs_dir)
        saved_static_libs_dir = join(build_dir, configuration + '-static-libs')
        if exists(saved_static_libs_dir):
            shutil.rmtree(saved_static_libs_dir)
        os.rename(static_libs_dir, saved_static_libs_dir)

        # Clean JDK image
        check_call(['rm', '-rf', join(build_dir, configuration)])

    check_call(["sh", "configure"] + configure_options)
    check_call([opts.make, "CONF=" + jdk_debug_level, "images"])
    build_dir = join(os.getcwd(), 'build')
    configuration = get_build_configuration(build_dir, '{}-{}'.format(opts.jdk_os, opts.jdk_arch), jdk_debug_level)
    jdk_bundle_dir = join(build_dir, configuration, 'images', 'jdk-bundle')
    if exists(jdk_bundle_dir):
        jdk_dirs = [join(jdk_bundle_dir, d) for d in os.listdir(jdk_bundle_dir) if d.endswith('.jdk')]
        assert len(jdk_dirs) == 1, str(os.listdir(jdk_bundle_dir))
        image = jdk_dirs[0]
        assert isdir(image), image
        java_home_dir = join(image, 'Contents/Home')
        needs_pathfix = True
    else:
        image = join(build_dir, configuration, 'images', 'jdk')
        java_home_dir = image
        needs_pathfix = False

    # Copy static libs into JDK image
    if saved_static_libs_dir:
        for name in os.listdir(saved_static_libs_dir):
            src = join(saved_static_libs_dir, name)
            dst = join(java_home_dir, 'lib', name)
            os.rename(src, dst)

    if is_closed:
        # Remove demo/ directory (OracleJDK does not include it)
        demo_dir = join(java_home_dir, 'demo')
        if exists(demo_dir):
            shutil.rmtree(demo_dir)

    arcpath = join(images_dir, archive)
    pathfixpath = None
    if needs_pathfix:
        # macOS JDK layout
        pathfixpath = arcpath + '.pathfix'
        with open(pathfixpath, 'w') as fp:
            fp.write('Contents/Home')

    log('Creating ' + arcpath)
    create_archive(image, arcpath, join(install_prefix, ''))
    sha1path = arcpath + '.sha1'
    create_sha1(arcpath, sha1path)

    if opts.clean_after_build:
        check_call([opts.make, "CONF=" + jdk_debug_level, "clean"])

    extracted_image_dir = join(images_dir, jdk_debug_level)
    if exists(extracted_image_dir):
        shutil.rmtree(extracted_image_dir)
    os.makedirs(extracted_image_dir)
    log('Extracting {} to {}'.format(arcpath, extracted_image_dir))
    with tarfile.open(arcpath, 'r:gz') as tf:
        tf.extractall(path=extracted_image_dir)

    extracted_java_home = join(extracted_image_dir, install_prefix)
    if needs_pathfix:
        extracted_java_home = join(extracted_java_home, 'Contents', 'Home')
    java_exe = join(extracted_java_home, 'bin', 'java')
    log('Executing {}'.format(java_exe))
    check_call([java_exe, "-version"])

    if opts.java_home_link_target:
        if exists(opts.java_home_link_target):
            os.unlink(opts.java_home_link_target)
        check_call(['ln', '-s', extracted_java_home, opts.java_home_link_target])

    if opts.scp_base_path:
        upload(arcpath, opts.scp_base_path, archive_prefix, opts.ci_target)
        upload(sha1path, opts.scp_base_path, archive_prefix, opts.ci_target)
        upload(pathfixpath, opts.scp_base_path, archive_prefix, opts.ci_target)
