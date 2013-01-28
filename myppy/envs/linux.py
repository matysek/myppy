#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import stat

from myppy.envs import base

from myppy.recipes import linux as _linux_recipes


class MyppyEnv(base.MyppyEnv):

    DEPENDENCIES = ["bin_lsbsdk","patchelf"]
    DEPENDENCIES.extend(base.MyppyEnv.DEPENDENCIES)

    @property
    def _arch_switch(self):
        """Return cli option for the compiler to compile 32bit or 64bit app."""
        switch = {'32bit': '-m32', '64bit': '-m64'}
        return switch[self.ARCH]

    @property
    def _lsb_libdir(self):
        libdir = {'32bit': 'opt/lsb/lib', '64bit': 'opt/lsb/lib64'}
        return libdir[self.ARCH]

    @property
    def CC(self):
        return "lsbcc " + self._arch_switch

    @property
    def CXX(self):
        return "lsbc++ " + self._arch_switch

    @property
    def LDFLAGS(self):
        #  --lsb-besteffort tweaks  executables so they do not hardcode
        #  the special lsb-specified loader but uses best-effort code
        #  to choose the dynamic linker at runtime. This trades
        #  lsb-compatability for ability to run out-of-the-box on more linuxen.
        flags = self._arch_switch + ' --lsb-besteffort ' + ' '
        # Some recipes require this -L/libdir ldflag.
        for libdir in ('lib', ):
            flags += ' -L' + os.path.join(self.PREFIX, libdir)
        return flags

    @property
    def CFLAGS(self):
        flags = " -fPIC -Os -D_GNU_SOURCE -DNDEBUG " + self._arch_switch + ' '
        # Some recipes might not be able to find ncurses. Include it explicitly.
        for incdir in ("include", 'include/ncurses'):
            flags += " -I" + os.path.join(self.PREFIX,incdir)
        return  flags

    @property
    def CXXFLAGS(self):
        flags = " -fPIC -Os -D_GNU_SOURCE -DNDEBUG " + self._arch_switch
        for incdir in ("include", ):
            flags += " -I" + os.path.join(self.PREFIX,incdir)
        return  flags

    @property
    def LD_LIBRARY_PATH(self):
        return os.path.join(self.PREFIX,"lib")

    @property
    def PKG_CONFIG_PATH(self):
        return ":".join((os.path.join(self.PREFIX,"lib/pkgconfig"),
                         os.path.join(self.PREFIX, self._lsb_libdir, 'pkgconfig'),))

    def __init__(self,rootdir, architecture):
        super(MyppyEnv,self).__init__(rootdir, architecture)
        if not os.path.exists(os.path.join(self.PREFIX,"lib")):
            os.makedirs(os.path.join(self.PREFIX,"lib"))
        self.env["CC"] = self.CC
        self.env["CXX"] = self.CXX
        self.env["LDFLAGS"] = self.LDFLAGS
        self.env["CFLAGS"] = self.CFLAGS
        self.env["CXXFLAGS"] = self.CXXFLAGS
        self._add_env_path("PATH",os.path.join(self.PREFIX,"opt/lsb/bin"),1)
        self._add_env_path("PKG_CONFIG_PATH",self.PKG_CONFIG_PATH)
        self.env["PKG_CONFIG_SYSROOT_DIR"] = self.PREFIX.rstrip("/")
        # PKG_CONFIG_LIBDIR tells pkg-config where to look for .pc files.
        self.env['PKG_CONFIG_LIBDIR'] = os.path.join(self.PREFIX, 'lib') + ':' +  os.path.join(self.PREFIX, self._lsb_libdir) 

        ## Linux Standard Base (LSB) specific environment variables. (for commands lsbcc / lsbc++)
        # Path to LSB stub libraries.
        self.env["LSBCC_LIBS"] = os.path.join(self.PREFIX, self._lsb_libdir)
        # Path to LSB C/C++ header files.
        self.env["LSBCC_INCLUDES"] = os.path.join(self.PREFIX,"opt/lsb/include")
        self.env["LSBCXX_INCLUDES"] = os.path.join(self.PREFIX,"opt/lsb/include")
        # Where to look for additional libraries outside LSB specification.
        self.env["LSB_SHAREDLIBPATH"] = os.path.join(self.PREFIX,"lib")
        # Shared libraries outside LSB spec to be allowed to link with.
        # Not having 'python' causes to link 'libpython' statically with every
        # Python C extension and drastically increases size of myppy environment.
        self.env["LSBCC_SHAREDLIBS"] = "bz2:crypto:ncurses:ncursesw:python:python2.7:readline:ssl"
        # For debugging lsbcc options.
        #self.env["LSBCC_VERBOSE"] = '0x0040'

    def record_files(self,recipe,files):
        if recipe not in ("bin_lsbsdk",):
            for fpath in files:
                fpath = os.path.join(self.rootdir,fpath)
                fnm = os.path.basename(fpath)
                if fpath == os.path.realpath(fpath):
                    if fnm.endswith(".so") or ".so." in fnm:
                        self._check_glibc_symbols(fpath)
                        if recipe not in ("python27",):
                            self._strip(fpath)
                        self._adjust_rpath(fpath)
                    elif "." not in fnm or os.access(fpath, os.X_OK):
                        fileinfo = self.bt("file",fpath)
                        if "executable" in fileinfo and "ELF" in fileinfo:
                            if recipe not in ("python27",):
                                self._strip(fpath)
                            self._adjust_rpath(fpath)
        super(MyppyEnv,self).record_files(recipe,files)

    def _strip(self,fpath):
        mod = os.stat(fpath).st_mode
        os.chmod(fpath,stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.do("strip",fpath)
        os.chmod(fpath,mod)

    def _check_glibc_symbols(self,fpath):
        print "VERIFYING GLIBC SYMBOLS", fpath
        errors = []
        for ln in self.bt("objdump","-T",fpath).split("\n"):
            for field in ln.split():
                if field.startswith("GLIBC_"):
                    ver = field.split("_",1)[1].split(".")
                    ver = map(int,ver)
                    if ver >= [2,4,]:
                        errors.append(ln.strip())
                elif field.startswith("GLIBCXX_"):
                    ver = field.split("_",1)[1].split(".")
                    ver = map(int,ver)
                    if ver > [3,4,7]:
                        errors.append(ln.strip())
        assert not errors, "\n".join(errors)

    def _adjust_rpath(self,fpath):
        #  patchelf might not be installed if we're just initialising the env.
        if os.path.exists(os.path.join(self.PREFIX,"bin","patchelf")):
            print "ADJUSTING RPATH", fpath
            backrefs = []
            froot = os.path.dirname(fpath)
            while froot != self.PREFIX:
                backrefs.append("..")
                froot = os.path.dirname(froot)
            rpath = "/".join(backrefs) + "/lib"
            rpath = "${ORIGIN}:${ORIGIN}/" + rpath
            self.do("patchelf","--set-rpath",rpath,fpath)

    def load_recipe(self,recipe):
        return self._load_recipe_subclass(recipe,MyppyEnv,_linux_recipes)

