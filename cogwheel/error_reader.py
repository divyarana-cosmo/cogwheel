import os

def is_xphm_warning(x):
    return (('XLAL Error - IMRPhenomX' in x) and
            (('Defaulting to NNLO angles' in x)
             or ('Triggering MSA failure' in x)))

class ErrorReader:
    """Class for reading error file and other textual output"""
    def __init__(self, dirname=None, get_outfiles=False, print_tail=False):
        self.lines = {}
        self.dirname, self.subdir_paths = dirname, None
        self.errorfile_paths, self.outfile_paths = None, None
        if dirname is not None:
            self.refresh_and_print(self, get_outfiles=get_outfiles,
                                   print_tail=print_tail)

    def refresh_and_print(self, get_outfiles=False, print_tail=False):
        self.subdir_paths = self.get_subdir_paths()
        self.errorfile_paths = self.get_errorfile_paths()
        self.print(print_tail)
        self.outfile_paths = None
        if get_outfiles:
            self.outfile_paths = self.get_outfile_paths()
            self.print(print_tail, self.outfile_paths)

    def path(self, filename):
        if str(self.dirname) in str(filename):
            return filename
        return os.path.join(self.dirname, filename)

    def get_subdir_paths(self, dir=None):
        dir = dir or self.dirname
        return [os.path.join(dir, x) for x in os.listdir(dir)
                if os.path.isdir(os.path.join(dir, x))]

    def get_paths(self, dir=None, subdirs=True, ext='.err'):
        dir = dir or self.dirname
        pathlist = [os.path.join(dir, x) for x in os.listdir(dir)
                    if x[-len(ext):] == ext]
        if subdirs:
            for d in self.get_subdir_paths(dir):
                pathlist += self.get_paths(d, True)
        return pathlist

    def get_errorfile_paths(self, dir=None, subdirs=True):
        return self.get_paths(dir=dir, subdirs=subdirs, ext='.err')

    def get_outfile_paths(self, dir=None, subdirs=True):
        return self.get_paths(dir=dir, subdirs=subdirs, ext='.out')

    def get_lines(self, paths=None, keep_empty=False,
                  keep_xphm_warnings=False):
        lineok0 = ((lambda x: True) if keep_empty else
                   (lambda x: (len(x.strip()) > 0)))
        lineok = ((lambda x: lineok0(x)) if keep_xphm_warnings else
                  (lambda x: (lineok0(x) and (not is_xphm_warning(x)))))
        lines = {}
        for p in [str(p) for p in (paths or self.errorfile_paths)]:
            lines[p] = [l for l in open(p, 'r').readlines() if lineok(l)]
        return lines

    def print(self, print_tail, paths=None, get_lines=True):
        pathstrs = [str(p) for p in (paths or self.errorfile_paths)]
        ntail = int(print_tail)
        print(f'....Printing {ntail} lines for {len(pathstrs)} files....')
        if get_lines:
            self.lines.update(self.get_lines(pathstrs))
        for i, p in enumerate(pathstrs):
            print(f'[{i}]\t' + '-' * 64 + f'\n{p}:\n({len(self.lines[p])} lines)')
            for jback in range(ntail):
                print(f'[[-{ntail - jback}]] {self.lines[p][-(ntail - jback)]}')

    def archive_paths(self, paths=None):
        for p in [str(p) for p in (paths or self.errorfile_paths)]:
            new_p = p + '.old'
            if os.path.exists(new_p):
                self.archive_paths(new_p)
            os.system(f'mv {p} {new_p}')