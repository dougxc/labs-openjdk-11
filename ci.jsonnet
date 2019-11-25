{
    WindowsMsys2:: {
        downloads+: {
            MSYS2: {name: "msys2", version: "20190524", platformspecific: true},
            DEVKIT: {name: "devkit", version: "VS2017-15.5.5", platformspecific: true},
        },
        capabilities+: ["windows"],
        name+: "-windows-msys2",
        environment+: {
            CI_OS: "windows",
            JIB_OS: "windows",
            JIB_PLATFORM_OS: "windows",
            SEP: "\\",
            PATH: "$MSYS2\\usr\\bin;$PATH",
            # Don't fake ln by copying files
            MSYS: "winsymlinks:nativestrict",
            # Prevent expansion of `/` in args
            MSYS2_ARG_CONV_EXCL: "-Fe;/Gy",
            ZLIB_BUNDLING: "bundled"
        },
        setup+: [
            # Initialize MSYS2
            ["bash", "--login"],
        ],
    },
    WindowsCygwin:: {
        downloads+: {
            CYGWIN: {name: "cygwin", version: "3.0.7", platformspecific: true},
        },
        capabilities+: ["windows"],
        name+: "-windows-cygwin",
        environment+: {
            CI_OS: "windows",
            JIB_OS: "windows",
            JIB_PLATFORM_OS: "windows",
            SEP: "\\",
            PATH: "$CYGWIN\\bin;$PATH",
            ZLIB_BUNDLING: "bundled"
        },
        setup+: [
            # Need to fix line endings on Windows to satisfy cygwin's perspective
            # https://stackoverflow.com/a/26408129
            ["git", "clone", "--config", "core.autocrlf=input", ".", "..${SEP}fixed-jdk"],
            ["cd", "..${SEP}fixed-jdk"],
        ],
    },
    Linux:: {
        docker: {
          "image": "phx.ocir.io/oraclelabs2/c_graal/jdk-snapshot-builder:2018-11-19"
        },
        capabilities+: ["linux"],
        name+: "-linux",
        environment+: {
            CI_OS: "linux",
            JIB_OS: "linux",
            JIB_PLATFORM_OS: "linux",
            SEP: "/",
        },
    },
    Darwin:: {
        packages+: {
            # No need to specify a "make" package as Mac OS X has make 3.81
            # available once Xcode has been installed.
        },
        environment+: {
            CI_OS: "darwin",
            JIB_OS: "macosx",
            JIB_PLATFORM_OS: "osx",
            SEP: "/",
            ac_cv_func_basename_r: "no",
            ac_cv_func_clock_getres: "no",
            ac_cv_func_clock_gettime: "no",
            ac_cv_func_clock_settime: "no",
            ac_cv_func_dirname_r: "no",
            ac_cv_func_getentropy: "no",
            ac_cv_func_mkostemp: "no",
            ac_cv_func_mkostemps: "no",
            MACOSX_DEPLOYMENT_TARGET: "10.11"
        },
        name+: "-darwin",
    },
    Mojave:: {
        capabilities+: ["darwin_mojave"] # JIB only works on the darwin_mojave slaves
    },
    Sierra:: {
        capabilities+: ["darwin_sierra"] # autoconf only available darwin_sierra slaves
    },

    AMD64:: {
        capabilities+: ["amd64"],
        name+: "-amd64",
        environment+: {
            CI_ARCH: "amd64",
            JIB_ARCH: "x64"
        }
    },

    AArch64:: {
        capabilities+: ["aarch64"],
        name+: "-aarch64",
        environment+: {
            CI_ARCH: "aarch64",
            JIB_ARCH: "aarch64"
        }
    },

    Eclipse:: {
        downloads+: {
            ECLIPSE: {
                name: "eclipse",
                version: "4.5.2",
                platformspecific: true
            }
        },
        environment+: {
            ECLIPSE_EXE: "$ECLIPSE/eclipse"
        },
    },

    JDT:: {
        downloads+: {
            JDT: {
                name: "ecj",
                version: "4.5.1",
                platformspecific: false
            }
        }
    },

    OracleJDK:: {
        downloads+: {
            JAVA_HOME: {
                name : "oraclejdk",
                version : "11.0.3+12",
                platformspecific: true
            }
        }
    },

    local jvmci_version = "20.0-b01",

    Build:: {
        environment: {
            MAKE : "make",
            ZLIB_BUNDLING: "system"
        },
        packages+: {
            "pip:astroid" : "==1.1.0",
            "pip:pylint" : "==1.1.0",
        },
        name: "gate",
        timelimit: "1:00:00",
        diskspace_required: "10G",
        logs: ["*.log"],
        targets: ["gate"],
    },

    WithJib:: {
        setup : [
            ["set-export", "JIB_DATA_DIR", "${PWD}${SEP}..${SEP}jib"],
            ["set-export", "JIB_SERVER", "https://java.se.oracle.com/artifactory"],
            ["set-export", "JIB_SERVER_MIRRORS", "https://jpg.uk.oracle.com/artifactory http://artifactory-sth.se.oracle.com:8081/artifactory"]
        ],
        run: [
            # Make release build
            ["bash", "bin/jib.sh", "configure", "-p", "${JIB_OS}-${JIB_ARCH}-open"],
            ["bash", "bin/jib.sh", "make", "-c", "${JIB_OS}-${JIB_ARCH}-open", "--", "product-bundles", "static-libs-bundles"],
            ["python", ".make_labsjdk.py", "--jvmci-version=" + jvmci_version,
                                           "--ci-platform=${CI_OS}-${CI_ARCH}",
                                           "--target-dir=build${SEP}release",
                                           "--conf=${JIB_OS}-${JIB_ARCH}-open"],
            ["build${SEP}release${SEP}java_home${SEP}bin${SEP}java", "-version"],

            # Make fastdebug build
            ["bash", "bin/jib.sh", "configure", "-p", "${JIB_OS}-${JIB_ARCH}-open-debug"],
            ["bash", "bin/jib.sh", "make", "-c", "${JIB_OS}-${JIB_ARCH}-open-debug", "--", "product-bundles", "static-libs-bundles"],
            ["python", ".make_labsjdk.py", "--jvmci-version=" + jvmci_version,
                                           "--ci-platform=${CI_OS}-${CI_ARCH}",
                                           "--target-dir=build${SEP}fastdebug",
                                           "--conf=${JIB_OS}-${JIB_ARCH}-open-debug"],
            ["build${SEP}fastdebug${SEP}java_home${SEP}bin${SEP}java", "-version"],
        ],
    },

    WithoutJib:: {
        run: [
            # Make release build
            ["sh", "configure",
                        "--with-conf-name=${CI_OS}-${CI_ARCH}-open",
                        "--with-debug-level=release",
                        "--with-jvm-features=graal",
                        "--enable-openjdk-only",
                        "--disable-warnings-as-errors",
                        "--with-zlib=${ZLIB_BUNDLING}",
                        "--with-boot-jdk=${JAVA_HOME}",
                        "--with-devkit=${DEVKIT}"],
            ["$MAKE", "CONF=${CI_OS}-${CI_ARCH}-open", "product-bundles", "static-libs-bundles"],
            ["python", ".make_labsjdk.py", "--jvmci-version=" + jvmci_version,
                                           "--ci-platform=${CI_OS}-${CI_ARCH}",
                                           "--target-dir=build${SEP}release",
                                           "--conf=${CI_OS}-${CI_ARCH}-open"],
            ["build${SEP}release${SEP}java_home${SEP}bin${SEP}java", "-version"],

            # Make fastdebug build
            ["sh", "configure",
                        "--with-conf-name=${CI_OS}-${CI_ARCH}-open-debug",
                        "--with-debug-level=fastdebug",
                        "--with-jvm-features=graal",
                        "--enable-openjdk-only",
                        "--disable-warnings-as-errors",
                        "--with-zlib=${ZLIB_BUNDLING}",
                        "--with-boot-jdk=${JAVA_HOME}",
                        "--with-devkit=${DEVKIT}"],
            ["$MAKE", "CONF=${CI_OS}-${CI_ARCH}-open-debug", "product-bundles", "static-libs-bundles"],
            ["python", ".make_labsjdk.py", "--jvmci-version=" + jvmci_version,
                                           "--ci-platform=${CI_OS}-${CI_ARCH}",
                                           "--target-dir=build${SEP}fastdebug",
                                           "--conf=${CI_OS}-${CI_ARCH}-open-debug"],
            ["build${SEP}fastdebug${SEP}java_home${SEP}bin${SEP}java", "-version"],
        ]
    },

    builds: [
        self.Build + self.WithJib + mach
        for mach in [
            self.Linux + self.AMD64,
            self.Darwin + self.Mojave + self.AMD64,
            self.WindowsCygwin + self.AMD64,
        ]
    ] + [
        self.Build + self.WithoutJib + self.Linux + self.AArch64 + self.OracleJDK
    ]
}
