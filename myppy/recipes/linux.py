#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import sys
import tempfile
import stat
import urlparse
import urllib2
import subprocess
import shutil
from textwrap import dedent

from myppy.util import md5file, do, bt, cd, relpath, tempdir, chstdin

from myppy.recipes import base

class Recipe(base.Recipe):

    @property
    def CC(self):
        return self.target.CC

    @property
    def CXX(self):
        return self.target.CXX

    @property
    def LDFLAGS(self):
        return self.target.LDFLAGS

    @property
    def CFLAGS(self):
        return self.target.CFLAGS

    @property
    def CXXFLAGS(self):
        return self.target.CXXFLAGS

    @property
    def LD_LIBRARY_PATH(self):
        return self.target.LD_LIBRARY_PATH

    @property
    def PKG_CONFIG_PATH(self):
        return self.target.PKG_CONFIG_PATH

    @property
    def CONFIGURE_VARS(self):
        return ["CC="+self.CC,
                "CXX="+self.CXX,
                "LDFLAGS="+self.LDFLAGS,
                "CFLAGS="+self.CFLAGS,
                "CXXFLAGS="+self.CXXFLAGS,
                "CPPFLAGS="+self.CXXFLAGS,
                "LD_LIBRARY_PATH="+self.LD_LIBRARY_PATH,
                "PKG_CONFIG_PATH="+self.PKG_CONFIG_PATH] 

    def _generic_configure(self,script=None,vars=None,args=None,env={}):
        if vars is None and self.CONFIGURE_VARS is None:
            env = env.copy()
            env.setdefault("LDFLAGS",self.LDFLAGS)
            env.setdefault("CFLAGS",self.CFLAGS)
            env.setdefault("CXXFLAGS",self.CXXFLAGS)
            env.setdefault("LD_LIBRARY_PATH",self.LD_LIBRARY_PATH)
            env.setdefault("PKG_CONFIG_PATH",self.PKG_CONFIG_PATH)
        super(Recipe,self)._generic_configure(script,vars,args,env)

    def _generic_make(self,vars=None,relpath=None,target=None,makefile=None,env={}):
        """Do a generic "make" for this recipe."""
        env = env.copy()
        env.setdefault("LD_LIBRARY_PATH",self.LD_LIBRARY_PATH)
        workdir = self._get_builddir()
        if vars is None:
            vars = self.MAKE_VARS
        if relpath is None:
            relpath = self.MAKE_RELPATH
        cmd = ["make",]
        if vars is not None:
            cmd.extend(["CC="+self.CC,"CXX="+self.CXX])
            cmd.extend(vars)
        if makefile is not None:
            cmd.extend(("-f",makefile))
        cmd.extend(("-C",os.path.join(workdir,relpath)))
        if target is not None:
            cmd.append(target)
        self.target.do(*cmd,env=env)

    def _generic_pyinstall(self,relpath="",args=[],env={}):
        env = env.copy()
        env.setdefault("LDFLAGS",self.LDFLAGS)
        env.setdefault("CFLAGS",self.CFLAGS)
        env.setdefault("CXXFLAGS",self.CXXFLAGS)
        env.setdefault("LD_LIBRARY_PATH",self.LD_LIBRARY_PATH)
        env.setdefault("PKG_CONFIG_PATH",self.PKG_CONFIG_PATH)
        super(Recipe,self)._generic_pyinstall(relpath,args,env)


class CMakeRecipe(base.CMakeRecipe,Recipe):
    @property
    def CXXFLAGS(self):
        flags = super(CMakeRecipe, self).CXXFLAGS
        flags += " -I" + os.path.join(self.PREFIX, "opt/lsb/include/c++")
        return flags
    def _generic_cmake(self,relpath=".",args=[],env={}):
        env = env.copy()
        env.setdefault("LDFLAGS",self.LDFLAGS)
        env.setdefault("CFLAGS",self.CFLAGS)
        env.setdefault("CXXFLAGS",self.CXXFLAGS)
        env.setdefault("LD_LIBRARY_PATH",self.LD_LIBRARY_PATH)
        env.setdefault("PKG_CONFIG_PATH",self.PKG_CONFIG_PATH)
        super(CMakeRecipe,self)._generic_cmake(relpath,args,env)

class PyRecipe(base.PyRecipe,Recipe):
    pass

class PyCMakeRecipe(base.PyCMakeRecipe,CMakeRecipe):
    pass


class cmake(base.cmake,Recipe):
    @property
    def CXXFLAGS(self):
        flags = super(cmake, self).CXXFLAGS
        flags += " -I" + os.path.join(self.PREFIX, "opt/lsb/include/c++")
        return flags
    def _patch(self):
        super(cmake,self)._patch()
        def stub_out_device_functions(lines):
            for ln in lines:
                if ln.startswith("archive_entry_dev") or ln.startswith("archive_entry_rdev"):
                    yield ln
                    ln = lines.next()
                    assert ln.strip() == "{"
                    yield ln
                    while ln.strip() != "}":
                        ln = lines.next()
                    yield "    return 0;"
                    yield ln
                else:
                    yield ln
        self._patch_build_file("Utilities/cmlibarchive/libarchive/archive_entry.c",stub_out_device_functions)


class python27(base.python27,Recipe,):
    """Install the basic Python interpreter, with myppy support."""
    DEPENDENCIES = ["lib_openssl"]

    def _post_config_patch(self):
        super(python27,self)._post_config_patch()
        #  Can't link epoll without symbols from a later libc.
        #  We'll have to settle for old-fashioned select().
        def remove_have_epoll(lines):
            for ln in lines:
                if "HAVE_EPOLL" not in ln:
                    yield ln
        self._patch_build_file("pyconfig.h",remove_have_epoll)
        #  Device functions are not part of LSB?
        def remove_have_device_macros(lines):
            for ln in lines:
                if "HAVE_DEVICE_MACROS" not in ln:
                    yield ln
        self._patch_build_file("pyconfig.h",remove_have_device_macros)
        #  Remove logic that adds unwanted include directories.
        def remove_multiarch_paths(lines):
            for ln in lines:
                yield ln
                if ln.strip() == "def add_multiarch_paths(self):":
                    yield "        return\n"
        self._patch_build_file("setup.py",remove_multiarch_paths)
        #  Fix bad handling of -R option to the compiler.
        def remove_runtime_library_support(lines):
            for ln in lines:
                yield ln
                if ln.strip().startswith("def runtime_library_dir_option("):
                    yield "        # Hardcode this for lcc/lcc++\n"
                    yield "        return '-L' + dir\n"
        self._patch_build_file("Lib/distutils/unixccompiler.py",
                               remove_runtime_library_support)

    def install(self):
        #  Hard-code distutils.util.get_platform() to return linux-i686
        #  We can't do this until after the build has completed.
        super(python27, self).install()
        def hardcode_platform(lines):
            for ln in lines:
                yield ln
                if ln.strip() == "def get_platform ():":
                    yield "    return 'linux-i686'\n\n"
        self._patch_file(os.path.join(self.PREFIX, "lib/python2.7/distutils/util.py"),hardcode_platform)

class patchelf(Recipe):
    SOURCE_URL = "http://hydra.nixos.org/build/1524660/download/2/patchelf-0.6.tar.bz2"
    SOURCE_MD5 = "5087261514b4b5814a39c3d3a36eb6ef"


class lib_openssl(base.lib_openssl,Recipe):
    def _configure(self):
        super(lib_openssl,self)._configure()
        def ensure_gnu_source(lines):
            for ln in lines:
                if ln.startswith("CFLAG="):
                    ln = ln.strip() + " -D_GNU_SOURCE -m32\n"
                    ln = ln.replace("-O3","-Os")
                    yield ln
                else:
                    yield ln
        self._patch_build_file("Makefile",ensure_gnu_source)


class py_cxfreeze(PyRecipe):
    DEPENDENCIES = ["python27"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/cx-freeze/4.2.2/cx_Freeze-4.2.2.tar.gz"


class py_bbfreeze(PyRecipe):
    DEPENDENCIES = ["python27"]
    SOURCE_URL = "http://pypi.python.org/packages/source/b/bbfreeze/bbfreeze-1.0.2.zip"
    def _patch(self):
        super(py_bbfreeze,self)._patch()
        def add_double_link_libs(lines):
            for ln in lines:
                yield ln
                if ln.strip() == "libs.append(conf.PYTHONVERSION)":
                    yield "            libs.extend(libs[:-1])"
        self._patch_build_file("setup.py",add_double_link_libs)
        def add_support_for_pyw_files(lines):
            for ln in lines:
                yield ln
                if ln.strip() == "fn = fn[:-3]":
                    yield 12*" " + "elif fn.endswith('.pyw'):\n"
                    yield 16*" " + "fn = fn[:-4]\n"
        self._patch_build_file("bbfreeze/freezer.py",add_support_for_pyw_files)


class lib_tiff(base.lib_tiff,Recipe):
    @property
    def CXXFLAGS(self):
        flags = super(lib_tiff,self).CXXFLAGS
        #  For whatever reason, -Os causes libtiff to suck in newer symbols.
        flags = flags.replace("-Os","")
        return flags


#  This is deliberately an old version of GTK; don't ship it with your
#  frozen apps, just depend on the system GTK.
class lib_gtk(Recipe):
    DEPENDENCIES = ["lib_glib","lib_pango","lib_atk","lib_tiff"]
    SOURCE_URL = "http://ftp.gnome.org/pub/gnome/sources/gtk+/2.8/gtk+-2.8.0.tar.gz"
    def _patch(self):
        #  We need access to the deprecated GMemChunk type when compiling
        #  against glib-2.10.  Hack the makefiles to avoid hiding it.
        def undisable_deprecated(lines):
            for ln in lines:
               if ln.strip() == "-DG_DISABLE_DEPRECATED":
                   pass
               elif "-DG_DISABLE_DEPRECATED" in ln:
                   yield ln.replace("-DG_DISABLE_DEPRECATED","")
               else:
                   yield ln
        workdir = self._get_builddir()
        for fnm in self.target.bt("find",workdir,"-name","Makefile").split():
            self._patch_file(fnm,undisable_deprecated)
        for fnm in self.target.bt("find",workdir,"-name","Makefile.am").split():
            self._patch_file(fnm,undisable_deprecated)
        for fnm in self.target.bt("find",workdir,"-name","Makefile.in").split():
            self._patch_file(fnm,undisable_deprecated)


class _lib_qt4_base(base._lib_qt4_base,Recipe):
    @property
    def DISABLE_FEATURES(self):
        features = super(_lib_qt4_base,self).DISABLE_FEATURES
        features.append("inotify")
        return features
    @property
    def CONFIGURE_ARGS(self):
        args = list(super(_lib_qt4_base,self).CONFIGURE_ARGS)
        args.append("-no-glib")
        args.append("-platform")
        args.append("linux-lsb-g++")
        args.append("-arch")
        args.append("i386")
        args.append("-L")
        args.append(os.path.join(self.PREFIX, "opt/lsb/lib"))
        return args
    def _patch(self):
        super(_lib_qt4_base,self)._patch()
        #  Force compilation with -m32
        def force_i386(lines):
            for ln in lines:
                for prog in ("CC", "CXX", "LINK"):
                    if ln.startswith("QMAKE_" + prog + "\t"):
                        yield ln.strip() + " -m32\n"
                        break
                else:
                    yield ln
        self._patch_build_file("mkspecs/linux-lsb-g++/qmake.conf",force_i386)
        #  Disable some functions only available on newer linuxes.
        #  Fortunately qt provides runtime fallbacks for these.
        def dont_use_newer_funcs(lines):
            for ln in lines:
                if "pipe2" in ln:
                    yield ln.replace("pipe2","disabled_pipe2")
                elif "dup3" in ln:
                    yield ln.replace("dup3","disabled_dup3")
                elif "accept4" in ln:
                    yield ln.replace("accept4","disabled_accept4")
                else:
                    yield ln
        self._patch_build_file("src/corelib/kernel/qcore_unix_p.h",dont_use_newer_funcs)
        self._patch_build_file("src/network/socket/qnet_unix_p.h",dont_use_newer_funcs)
        #  Disabling exceptions makes pthread_cleanup_push/pop require newer
        #  glibc symbols.  Just disable them.
        def dont_use_pthread_cleanup(lines):
            for ln in lines:
                if ln.strip().startswith("pthread_cleanup_push"):
                    pass
                elif ln.strip().startswith("pthread_cleanup_pop"):
                    yield "    QThreadPrivate::finish(arg);\n"
                else:
                    yield ln
        self._patch_build_file("src/corelib/thread/qthread_unix.cpp",dont_use_pthread_cleanup)
        #  Fix some LSB compiance errors in webkit.
        def fix_timegm(lines):
            for ln in lines:
                if ln.strip() == "#define HAVE_TIMEGM 1":
                    yield "#if !defined(__LSB_VERSION__)\n"
                    yield ln
                    yield "#endif\n"
                else:
                    yield ln
        self._patch_build_file("src/3rdparty/javascriptcore/JavaScriptCore/wtf/Platform.h", fix_timegm)
        self._patch_build_file("src/3rdparty/webkit/JavaScriptCore/wtf/Platform.h", fix_timegm)


class lib_qt4_small(base.lib_qt4_small,_lib_qt4_base):
    pass

class lib_qt4(base.lib_qt4,_lib_qt4_base):
    pass


class lib_wxwidgets_base(base.lib_wxwidgets_base,Recipe):
    DEPENDENCIES = ["lib_gtk","lib_png","lib_jpeg","lib_tiff"]
    #  Use of std_iostreams seems to suck in newer glibc symbols, so
    #  we explicitly disable it until someone proves it's needed.
    CONFIGURE_ARGS = ["--with-gtk","--disable-std_iostreams"]
    CONFIGURE_ARGS.extend(base.lib_wxwidgets_base.CONFIGURE_ARGS)


class bin_lsbsdk(Recipe):
    @property
    def SOURCE_URL(self):
        url = {
                '32bit': 'http://ftp.linuxfoundation.org/pub/lsb/bundles/released-4.1.0/sdk/lsb-sdk-4.1.5-1.ia32.tar.gz',
                '64bit': 'http://ftp.linuxfoundation.org/pub/lsb/bundles/released-4.1.0/sdk/lsb-sdk-4.1.5-1.x86_64.tar.gz',
        }
        return url[self.target.ARCH]
    def build(self):
        pass
    def install(self):
        updir = self._unpack()
        for nm in os.listdir(updir):
            if nm.endswith(".rpm"):
                fpath = os.path.join(updir, nm)
                with open(fpath+".cpio", "w+") as stdout:
                    self.target.do("rpm2cpio", fpath, stdout=stdout)
                    stdout.seek(0)
                    with cd(self.INSTALL_PREFIX):
                        self.target.do("cpio", "-duvi", stdin=stdout)
        def hackily_define_TIOCSWINSZ(lines):
            for ln in lines:
                yield ln
                if ln.strip().startswith("#define TIOCGWINSZ"):
                    yield "#define TIOCSWINSZ    0x5414\n"
        ioctl_header = os.path.join(self.INSTALL_PREFIX,
                                    "opt/lsb/include/sys/ioctl.h")
        self._patch_file(ioctl_header, hackily_define_TIOCSWINSZ)


class lib_sparsehash(Recipe):
    """Google sparehash, using old C++ hash function APIs.

    This installs a private copy of the google sparsehash library, tricked into
    sucking in old definitions for hash_fun.h rather than the ones provided by
    C++ tr1.  Other libraries can then avoid sucking in the tr1 symbols.
    """
    SOURCE_URL = "http://google-sparsehash.googlecode.com/files/sparsehash-1.10.tar.gz"
    def _patch(self):
        super(lib_sparsehash,self)._patch()
        def dont_use_tr1(lines):
            for ln in lines:
                yield ln.replace("tr1/","tr1_DONT_USE_ME/")
        self._patch_build_file("configure",dont_use_tr1)
        def include_typeinfo(lines):
            ln = lines.next()
            while not ln.startswith("#include"):
                yield ln
                ln = lines.next()
            yield "#include <typeinfo>\n"
            yield ln
            for ln in lines:
                yield ln
        self._patch_build_file("src/hashtable_test.cc",include_typeinfo)


class lib_shiboken(base.lib_shiboken,CMakeRecipe):
    #  Use a private build of google sparsehash, so we don't pull
    #  in symbols from C++ TR1 hashtable spec.
    #DEPENDENCIES = ["lib_sparsehash"]
    @property
    def CXXFLAGS(self):
        flags = super(lib_shiboken,self).CXXFLAGS
        flags += " -I" + os.path.join(self.PREFIX,"include")
        return flags
    @property
    def LDFLAGS(self):
        flags = super(lib_shiboken,self).LDFLAGS
        libdir = os.path.join(lib_qt4(self.target).INSTALL_PREFIX,"lib")
        flags = ("-L%s -lpthread -lrt -lz -ldl -lQtNetwork -lQtCore -ljpeg -ltiff -lpng15 -lz -lX11 -lXrender -lXext -lfontconfig -lSM -lICE " % (libdir,)) + flags
        return flags
    def _patch(self):
        super(lib_shiboken,self)._patch()
        #  Provide hash function implementations that would be automatically
        #  provided by tr1, but are missing in the backwards-compat code.
        def provide_hash_funcs(lines):
            for ln in lines:
                if "namespace Shiboken" in ln:
                    break
                yield ln
            yield dedent("""
                      #include <hash_fun.h>
                      namespace __gnu_cxx {
                      template<>
                      struct hash<void *> {
                          size_t operator()(const void * __x) const {
                              return reinterpret_cast<size_t>(__x); }
                          };
                      template<>
                      struct hash<const void *> {
                          size_t operator()(const void * __x) const {
                              return reinterpret_cast<size_t>(__x); }
                          };
                      template<>
                      struct hash<SbkObjectType *> {
                          size_t operator()(const SbkObjectType * __x) const {
                              return reinterpret_cast<size_t>(__x); }
                          };
                      template<>
                      struct hash<std::basic_string<char, std::char_traits<char>, std::allocator<char> > > {
                          size_t operator()(std::basic_string<char, std::char_traits<char>, std::allocator<char> > __x) const {
                              //  copied from the hash func for char*
                              unsigned long __h = 0;
                              for(unsigned long i=0;i<__x.size();i++) {
                                  __h = 5 * __h + __x[i];
                              }
                              return size_t(__h);
                              }
                          };
                      }

                  """)
            yield ln
            for ln in lines:
                yield ln
        #self._patch_build_file("libshiboken/bindingmanager.cpp",provide_hash_funcs)
        #self._patch_build_file("libshiboken/typeresolver.cpp",provide_hash_funcs)


class py_myppy(base.py_myppy,Recipe):
    def install(self):
        super(py_myppy,self).install()
        with open(self._init_shell_script("python"),"a") as f:
            f.write("exec \"$WHEREAMI/local/bin/python\" \"$@\"\n")
        with open(self._init_shell_script("shell"),"a") as f:
            f.write(dedent("""
                if [ -n "$BASH" ]; then
                    SHELL="$SHELL --noprofile --norc"
                fi
                
                exec $SHELL "$@"
            """))
        with open(self._init_shell_script("myppy"),"a") as f:
            f.write("\"$WHEREAMI/local/bin/python\" -m myppy.__main__ \"$WHEREAMI\" \"$@\"\n")

    def _init_shell_script(self,relpath):
        fpath = os.path.join(self.target.rootdir,relpath)
        with open(fpath,"wb") as f:
            f.write(self._SHELLSCRIPT_STANZA)
        mod = os.stat(fpath).st_mode
        mod |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        os.chmod(fpath,mod)
        return fpath

    _SHELLSCRIPT_STANZA = dedent("""
        #  We may not have a GNU-compatible readlink, so we're forced to find
        #  the real file for this script the hard way.

        CURDIR=`pwd`
        MYFILE="$0"
        MYDIR=`dirname "$MYFILE"`
        cd "$MYDIR"
        MYFILE=`basename "$MYFILE"`
        while [ -L "$MYFILE" ]; do
            MYFILE=`readlink "$MYFILE"`
            MYDIR=`dirname "$MYFILE"`
            cd "$MYDIR"
            MYFILE=`basename "$MYFILE"`
        done
        MYFILE=`pwd -P`/"$MYFILE"
        cd "$CURDIR"

        WHEREAMI=`dirname "$MYFILE"`
        WHOAMI=`basename "$MYFILE" .sh`

        PATH="$WHEREAMI/local/bin":$PATH
        export PATH

        PS1="myppy(`basename $WHEREAMI`):\w$ "
        export PS1

        if [ -n "$BASH" -o -n "$ZSH_VERSION" ] ; then
            hash -r
        fi
    """)



class lib_fontconfig(Recipe):
    #  This is intentionally an old version.  We don't dsitribute it,
    #  but it's API compatible back to some old Linux distros.
    SOURCE_URL = "http://fontconfig.org/release/fontconfig-2.4.1.tar.gz"


class lib_pango(Recipe):
    BUILD_DEPENDENCIES = ["lib_fontconfig"]
    SOURCE_URL = "http://ftp.acc.umu.se/pub/gnome/sources/pango/1.12/pango-1.12.0.tar.bz2"

class lib_glib(Recipe):
    SOURCE_URL = "http://ftp.gnome.org/pub/gnome/sources/glib/2.10/glib-2.10.0.tar.bz2"

class lib_atk(Recipe):
    SOURCE_URL = "http://ftp.acc.umu.se/pub/gnome/sources/atk/1.11/atk-1.11.4.tar.bz2"


class py_pyside(base.py_pyside,PyCMakeRecipe):
    @property
    def LDFLAGS(self):
        flags = super(py_pyside,self).LDFLAGS
        if "-static" in lib_qt4(self.target).CONFIGURE_ARGS:
            flags = " -lpthread -lrt -lz -ldl -lQtNetwork -lQtCore -ljpeg -ltiff -lpng15 -lz -lX11 -lXrender -lXrandr -lXext -lfontconfig -lSM -lICE " + flags
        return flags


class py_pypy(base.py_pypy,Recipe):
    def _patch(self):
        def dont_use_setaffinity(lines):
            #  Completely replace the file.
            yield "void pypy_setup_profiling() { }\n"
            yield "void pypy_teardown_profiling() { }\n"
        self._patch_build_file("pypy/translator/c/src/profiling.c",dont_use_setaffinity)


class lib_bz2(base.lib_bz2,Recipe):
    def _patch(self):
        super(lib_bz2,self)._patch()
        def add_cflags(lines):
            for ln in lines:
                if ln.startswith("CFLAGS="):
                    ln = ln.strip() + self.CFLAGS + "\n"
                yield ln
        self._patch_build_file("Makefile",add_cflags)

