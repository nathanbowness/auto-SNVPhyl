# Written by Devon Mack
# March 2017
# This will use already existing scripts in the MiSeq_Backup folder and WGSspades to
# extract files easily. It is sped up by the fact that it will create multiple sub-processes
# for every request it makes.

import os
import shutil
import sys
import glob
from collections import defaultdict
from pyaccessories.SaveLoad import SaveLoad


class SequenceGetter(object):
    def retrieve_file(self, seqid, filetype="fastq_R1", getpathonly=False):
        """
        This will retrieve a file from the NAS and put it in the directory specified in the constructor
            Parameters:
                seqid: sequence id
                part: 1 or 2 (which part of the pair you want, R1 or R2)
                filetype: either fasta or fastq
                getpathonly: return the path instead of retrieving the file
        """

        msg = "Default message (something went wrong)"
        return_path = None
        # Create the output folder if it doesn't exist
        if self.outputfolder is not None and not os.path.exists(self.outputfolder):
            os.makedirs(self.outputfolder)

        # Get a fastq file
        import re
        if re.match(r"^fastq_R[1,2]$", filetype):
            # Check if in master list, extract the two paths and copy to output folder
            if seqid in self.file_dict:
                pair = [self.file_dict[seqid][0], self.file_dict[seqid][1]]
                for path in pair:
                    if "_R%s_" % filetype[-1] in path:
                        if getpathonly:
                            return_path = path
                        else:
                            msg = "Copying file %s to %s" % (path, self.outputfolder)
                            outpath = os.path.join(self.outputfolder, os.path.split(path)[1])
                            shutil.copy(path, outpath)

            else:
                msg = "Missing file " + seqid
        # Get a fasta file
        elif filetype == "fasta":
            # Check if in master list, extract the two paths and copy to output folder
            if seqid in self.file_dict_fasta:
                path = self.file_dict_fasta[seqid][0]
                if getpathonly:
                    return_path = path
                else:
                    msg = "Copying file %s to %s" % (path, self.outputfolder)
                    outpath = os.path.join(self.outputfolder, os.path.split(path)[1])
                    shutil.copy(path, outpath)

            else:
                msg = "Missing file " + seqid
        else:
            raise ValueError("Invalid filetype " + filetype)

        if self.output:
            print(msg)

        if getpathonly:
            return return_path
        else:
            return msg

    def get_file_list(self):
        """ 
        Gather an iterative of every fastq.gz file found in all subdirectories
        and create a dictionary based on SEQ-IDs with the value being the paired end files.
        """

        for path in glob.iglob(os.path.join(self.nasmnt, 'MiSeq_Backup', '*', '*.fastq.gz')):
            self.file_dict[os.path.split(path)[1].split('_')[0]].append(path)

        for path in glob.iglob(os.path.join(self.nasmnt, 'WGSspades', '*', 'BestAssemblies', '*.fasta')):
            self.file_dict_fasta[os.path.split(path)[1].split('.fasta')[0]].append(path)

        def walklevel(some_dir, level=1):
            """os.walk but it allows you to limit the level"""
            some_dir = some_dir.rstrip(os.path.sep)
            assert os.path.isdir(some_dir)
            num_sep = some_dir.count(os.path.sep)
            for root, dirs, files in os.walk(some_dir):
                yield root, dirs, files
                num_sep_this = root.count(os.path.sep)
                if num_sep + level <= num_sep_this:
                    del dirs[:]

        # External fastq
        for root, dirs, files in walklevel(os.path.join(self.nasmnt,'External_MiSeq_Backup'), level=3):
            for x in files:
                if x.endswith(".fastq.gz"):
                    self.file_dict[os.path.split(x)[-1].split('_')[0]].append(os.path.join(root, x))

        # External fasta
        for path in glob.iglob(os.path.join(self.nasmnt, 'External_WGSspades/*/*/BestAssemblies/*.fasta')):
            self.file_dict_fasta[os.path.split(path)[1].split('.fasta')[0]].append(path)

    def __init__(self, outputfolder=None, nasmnt="/mnt/nas/", output=True):
        self.file_dict = defaultdict(list)
        self.file_dict_fasta = defaultdict(list)
        self.nasmnt = nasmnt
        self.outputfolder = outputfolder
        self.output = output
        self.get_file_list()