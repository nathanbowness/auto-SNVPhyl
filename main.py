#!/usr/bin/env python3
# Written by Devon Mack April-May 2017
# This program takes a 5 parameters in the config file and runs a SNVPhyl in galaxy fully automatically
# Parameters (when it doubt, delete the config.json file and the program will create it for you with defaults):
#  config.json
#   api_key: The API key which must be generated in galaxy
#   workflow_id: The ID of the SNVPhyl workflow
#   ip: The ip of galaxy (with port)
#   name: The prefix of the history name
#   nasmnt: The directory of the NAS mount

# TODO Combined sequences folder to index
# TODO SNVPhyl Renamer

import os
import sys
import re
import time
import requests
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy import dataset_collections as collections
from bioblend import ConnectionError
from pyaccessories.TimeLog import Timer
import zipfile


class AutoSNVPhylError(ValueError):
    """Raise when a specific subset of values in context of app is wrong"""

    def __init__(self, message, *args):
        self.message = message  # without this you may get DeprecationWarning
        # allow users initialize misc. arguments as any other builtin Error
        super(AutoSNVPhylError, self).__init__(message, *args)


class AutoSNVPhyl(object):
    def run(self):
        try:
            self.load()  # Load from config
            self.gi = GalaxyInstance(self.IP, key=self.API_KEY)

            if not self.manual and self.reference is None:
                # No reference and it isn't using files in upload folder
                self.t.time_print("No reference file specified with -r, please input one or use the --manual"
                                  " flag to use a reference file that you put in the upload folder.")
                exit(1)

            if self.noextract and not self.manual:
                self.t.time_print("[Warning] Using manual flag since noextract was specified without manual.")
                self.manual = True

            return self.main()  # Return the path to the results zip
        except:
            import traceback

            # Print error to file
            self.t.time_print("[Error Dump]\n" + traceback.format_exc())
            raise

    def main(self):
        # Create history in Galaxy
        self.t.time_print("Creating history " + self.NAME)
        while True:
            try:
                self.history_id = self.gi.histories.create_history(self.NAME)['id']
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        self.t.time_print(self.history_id)

        # Begin uploading files to Galaxy
        self.t.time_print("Uploading files to galaxy...")

        # Upload files from the NAS based on the SEQ-ID list given
        if not self.noextract:
            self.t.time_print("Finding files on the NAS...")

            # Get list of files to retrieve
            to_upload = self.extract_files()

            # Upload to galaxy
            self.t.time_print("Uploading files from the NAS...")
            n = 1
            nfiles = len(to_upload)
            for file in to_upload:
                self.t.time_print("%d of %d: Uploading %s" % (n, nfiles, file))
                self.upload_file(file)
                self.uploaded.append(os.path.split(file)[-1].split('.gz')[0])
                n += 1

        # Upload files from the upload folder if the manual flag is used
        if self.manual:
            self.t.time_print("Using files in upload folder since -m was used")
            n = 1
            upload_folder = os.path.join(self.script_dir, "upload")
            files = os.listdir(upload_folder)
            nfiles = len(files)
            for file in files:
                self.t.time_print("%d of %d: Uploading %s from %s directory." % (n, nfiles, file, upload_folder))
                self.upload_file(os.path.join(upload_folder, file))
                if file.endswith('.fastq.gz'):
                    self.uploaded.append(file.split('.gz')[0])  # In galaxy the .gz is removed
                else:
                    self.uploaded.append(file)  # Fasta file
                n += 1

        self.t.time_print("Waiting for files to finish uploading...")
        while True:
            try:
                while self.gi.histories.show_history(self.history_id)["state"] != "ok":
                    time.sleep(10)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        # Check if all the files are on galaxy and that there are no duplicate/extra files there
        # Create list that stores all the files on galaxy
        on_galaxy = []
        while True:
            try:
                datasets = self.gi.histories.show_history(self.history_id, contents=True)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        for dataset in datasets:
            on_galaxy.append(dataset['name'])

        # Check for duplicate files
        count = {}
        for file in on_galaxy:
            try:
                self.t.time_print(count[file])  # If this succeeds then the file is already on galaxy so duplicate
                self.t.time_print("[Error] Duplicate file %s on galaxy!" % file)
            except KeyError:
                # If it isn't already in the dictionary add it to the dictionary
                count[file] = True

        # Print all the files that weren't successfully uploaded.
        for file in self.uploaded:
            if file not in on_galaxy:
                # It wasn't decompressed
                if file + ".gz" in on_galaxy:
                    if 'R1' in file:
                        n = 'R1'
                    else:
                        n = 'R2'

                    # Re-upload the file
                    self.t.time_print("[Warning] File %s wasn't automatically decompressed by galaxy,"
                                      " re-uploading..." % file + '.gz')
                    self.upload_file(self.extractor.retrieve_file(file.split('_')[0], filetype="fastq_" + n,
                                                                  getpathonly=True))
                    if not self.upload_check(file):
                        errmsg = "[Error] File %s wasn't automatically decompressed by galaxy again, something is " \
                                 "wrong with the file?" % file + '.gz'
                        self.t.time_print(errmsg)
                        raise AutoSNVPhylError(errmsg)
                else:
                    n = ""
                    if 'R1' in file:
                        n = 'R1'
                    elif 'R2'in file:
                        n = 'R2'

                    self.t.time_print("[Warning] File %s wasn't uploaded to galaxy! Attempting to re-upload" % file)
                    if n == "":
                        if file.endswith('.fasta'):
                            self.upload_file(self.extractor.retrieve_file(file.split('.')[0], filetype="fasta",
                                                                          getpathonly=True))
                    else:
                        self.upload_file(self.extractor.retrieve_file(file.split('_')[0], filetype="fastq_" + n,
                                                                      getpathonly=True))
                    if not self.upload_check(file):
                        errmsg = "[Error] File %s couldn't be uploaded to galaxy!" % file
                        self.t.time_print(errmsg)
                        raise AutoSNVPhylError(errmsg)

        self.t.time_print("Finished uploading.")
        self.t.time_print("Building list of dataset pairs...")
        self.build_list()

        self.t.time_print("Starting workflow...")
        self.run_workflow()
        time.sleep(10)  # Give it a bit of time to start the workflow

        # Wait for workflow to finish
        self.t.time_print("Waiting for workflow to finish.")
        wait = 0
        while True:
            try:
                history_state = self.gi.histories.show_history(self.history_id)["state"]
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        while history_state != "ok":
            wait += 1
            if wait > 60:  # 10 minutes
                self.t.time_print("Still waiting for workflow to finish.")
                wait = 0

            time.sleep(10)
            while True:
                try:
                    history_state = self.gi.histories.show_history(self.history_id)["state"]
                    break
                except (ConnectionError, requests.exceptions.ConnectionError):
                    self.wait_for_problem()

            if history_state == "error":
                name = history_state["name"]
                self.t.time_print("Something went wrong with your SNVPhyl! Check the galaxy history called %s" % name)
                raise AutoSNVPhylError("Something went wrong with your SNVPhyl! "
                                       "Check the galaxy history called %s" % name)

        self.t.time_print("Workflow finished, downloading files...")

        to_download = [
            "snvMatrix.tsv",
            "phylogeneticTreeStats.txt",
            "phylogeneticTree.newick",
            "filterStats.txt",
            "snvAlignment.phy",
            "vcf2core.tsv",
            "snvTable.tsv"
        ]

        self.t.time_print("Creating directory %s." % self.NAME)
        folder = os.path.join(self.script_dir, 'results', self.NAME)
        if not os.path.exists(folder):
            os.makedirs(folder)

        self.t.time_print("Downloading files:")

        not_downloaded = to_download
        while True:
            try:
                datasets = self.gi.histories.show_history(self.history_id, contents=True)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()
        for dataset in datasets:
            # Renames and downloads
            if dataset["name"] in to_download:
                self.t.time_print("    Downloading %s to %s" % (dataset["name"], os.path.join(folder, dataset["name"])))
                while True:
                    try:
                        self.gi.datasets.download_dataset(dataset["id"], os.path.join(folder, dataset["name"]),
                                                          wait_for_completion=True, use_default_filename=False)
                        break
                    except (ConnectionError, requests.exceptions.ConnectionError):
                        self.wait_for_problem()
                not_downloaded.remove(dataset["name"])

        if len(not_downloaded) > 0:
            self.t.time_print("[Warning] Can't find some results files on Galaxy!,"
                              " these will not be included in the zip file: ")
            for missing in to_download:
                self.t.time_print("     %s" % missing)

        self.zip_results(folder)

        self.t.time_print("Completed")

        return os.path.join(self.script_dir, folder, self.NAME + '.zip')

    def upload_check(self, filename):
        self.t.time_print("Waiting for upload to finish...")
        while True:
            try:
                while self.gi.histories.show_history(self.history_id)["state"] != "ok":
                    time.sleep(10)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        # Check if the file is on galaxy
        on_galaxy = []
        while True:
            try:
                datasets = self.gi.histories.show_history(self.history_id, contents=True)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        for dataset in datasets:
            on_galaxy.append(dataset['name'])

        if filename in on_galaxy:
            return True
        else:
            return False

    def zip_results(self, r_folder):
        f_list = [
            "snvMatrix.tsv",
            "phylogeneticTreeStats.txt",
            "phylogeneticTree.newick",
            "filterStats.txt",
            "snvAlignment.phy",
            "vcf2core.tsv",
            "snvTable.tsv"
        ]
        # Zip all the files
        results_zip = os.path.join(self.script_dir, r_folder, self.NAME + '.zip')
        self.t.time_print("Creating zip file %s" % results_zip)

        try:
            os.remove(results_zip)
        except OSError:
            pass

        zipf = zipfile.ZipFile(results_zip, 'w', zipfile.ZIP_DEFLATED)
        for to_zip in f_list:
            try:
                zipf.write(os.path.join(r_folder, to_zip), arcname=to_zip)
                self.t.time_print("Zipped %s" % to_zip)
            except FileNotFoundError:
                self.t.time_print("[Warning] Can't find %s, will leave it out of .zip." % to_zip)
                raise

        zipf.close()

    def upload_file(self, path):
        from bioblend import ConnectionError as bioblendConnectionError
        import time
        attempts = 0
        while True:
            try:
                self.t.time_print("Uploading...")
                self.gi.tools.upload_file(os.path.join(self.script_dir, "upload", path), self.history_id)
                return
            except bioblendConnectionError:
                if attempts < self.max_attempts:
                    attempts += 1
                    self.t.time_print("[Warning] Failed to upload %s, retrying (attempt %d of %d)" %
                                      (path, attempts, self.max_attempts))
                    time.sleep(5)
                    continue
                else:
                    self.t.time_print("[Error] Failed to upload %s, after %d attempts." %
                                      (path, self.max_attempts))
                    raise
            except requests.exceptions.ConnectionError:
                if attempts < self.max_attempts:
                    attempts += 1
                    self.t.time_print("Galaxy isn't responding...")
                    self.wait_for_problem()
                    self.t.time_print("[Warning] Failed to upload %s, retrying (attempt %d of %d)" %
                                      (path, attempts, self.max_attempts))
                    continue
                else:
                    self.t.time_print("[Error] Failed to upload %s, after %d attempts." %
                                      (path, self.max_attempts))
                    raise

    def extract_files(self):
        from sequence_getter import SequenceGetter
        from sequence_getter import ExtractionError

        self.extractor = SequenceGetter(nasmnt=self.NASMNT, output=False)
        if self.inputs is None:
            path_to_list = os.path.join(self.script_dir, "retrieve.txt")
            try:
                f = open(path_to_list, "r")
                # Get all of the ids in the file
                ids = re.findall(r"(2\d{3}-\w{2,10}-\d{3,4})", f.read())
                f.close()
            except FileNotFoundError:
                # create blank file
                open(path_to_list, "w").close()
                print("Please enter SEQids in the retrieve.txt file")
                exit(1)

            # Finds the invalid lines and output them
            for line in open("retrieve.txt", "r"):
                if line.rstrip("\n") not in ids and len(line.rstrip("\n")) > 2:
                    self.t.time_print("Invalid seqid: \"%s\"" % line.rstrip("\n"))

        else:
            ids = self.inputs

        # Get paths of fastq's
        path_list = []
        err = ""
        for seqid in ids:
            for i in [1, 2]:
                try:
                    path_list.append(self.extractor.retrieve_file(seqid.rstrip("\n"), filetype="fastq_R" + str(i),
                                                             getpathonly=True))
                except ExtractionError as e:
                    err += e.message + '\n'

        if self.reference is not None:
            # Get fasta
            try:
                refpath = self.extractor.retrieve_file(self.reference, "fasta", getpathonly=True)
            except ExtractionError as e:
                err += e.message + '\n'
            if len(err) > 0:
                raise AutoSNVPhylError(err)
            path_list.append(refpath)
            self.uploaded.append(os.path.split(refpath)[-1])
        else:
            # Since there is no reference specified, check for one in the upload directory
            self.t.time_print("No reference file specified, using the one in the upload directory")
            found_ref = False
            for file in os.listdir(os.path.join(self.script_dir, 'upload')):
                if file.endswith(".fasta"):
                    if not found_ref:
                        self.t.time_print("Found " + file + ", using it as a reference...")
                        found_ref = True
                    else:
                        self.t.time_print("[Error] Found another reference file in upload folder, please only use one.")
                        exit(1)
            if not found_ref:
                self.t.time_print("[Error] No reference file(fasta) found. Cannot run.")
                exit(1)

        return path_list

    def run_workflow(self):
        while True:
            try:
                contents = self.gi.histories.show_history(self.history_id, contents=True)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

        datamap = dict()
        found_ref = False
        found_collection = True
        # Find the reference file
        for item in contents:
            if item["history_content_type"] == "dataset" and item["extension"] == "fasta":
                datamap['1'] = {
                    'src': 'hda',
                    'id': item['id']
                }
                found_ref = True
            if item["name"] == "pair_list":
                datamap['0'] = {
                    'src': 'hdca',
                    'id': item['id']
                }
                found_collection = True

        if not found_ref:
            self.t.time_print("[Error] Can't find a reference on Galaxy.")
            raise AutoSNVPhylError("Can't find a reference on Galaxy.")
        if not found_collection:

            self.t.time_print("[Error] Can't find list of dataset pairs on Galaxy.")
            raise AutoSNVPhylError("Can't find list of dataset pairs on Galaxy.")

        min_coverage = "10"
        min_mean_mapping = "30"
        alternative_allele_proportion = "0.75"

        params = {  # Don't change this, it works
            '5': {
                'mindepth': min_coverage
            },
            '11': {
                'coverage': min_coverage,
                'mean_mapping': min_mean_mapping,
                'ao': alternative_allele_proportion
            },

        }

        while True:
            try:
                self.gi.workflows.invoke_workflow(self.WORKFLOW_ID, inputs=datamap,
                                                  params=params, history_id=self.history_id)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

    def build_list(self):
        while True:
            try:
                contents = self.gi.histories.show_history(self.history_id, contents=True)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()
        fastqs = []

        # get fastq files
        for item in contents:
            if item["history_content_type"] == "dataset" and item["extension"] == "fastq":
                fastqs.append(item)

        # pair fastq files
        r1s = []
        r2s = []
        for fastq in fastqs:
            result1 = re.findall(r"(.+)_[Rr]1", fastq["name"], flags=0)
            result2 = re.findall(r"(.+)_[Rr]2", fastq["name"], flags=0)
            if len(result1) >= 1:
                fastq["name"] = result1[0]
                r1s.append(fastq)
            if len(result2) >= 1:
                fastq["name"] = result2[0]
                r2s.append(fastq)

        if len(r1s) != len(r2s):
            self.t.time_print("[WARNING] There are different amounts of R1 and R2 files,"
                              " will only use ones that can be paired.")

        pairs = []
        done = []

        for sequence in r1s:
            for compare in r2s:
                if sequence["name"] == compare["name"] and sequence["name"] not in done:
                    # Pair them
                    elements = [
                            collections.HistoryDatasetElement(name="forward", id=sequence["id"]),
                            collections.HistoryDatasetElement(name="reverse", id=compare["id"])
                        ]
                    done.append(sequence["name"])
                    pairs.append(collections.CollectionElement(sequence["name"], type="paired", elements=elements))

        collection_description = collections.CollectionDescription("pair_list", type="list:paired", elements=pairs)
        while True:
            try:
                self.gi.histories.create_dataset_collection(self.history_id, collection_description)
                break
            except (ConnectionError, requests.exceptions.ConnectionError):
                self.wait_for_problem()

    def load(self):
        from pyaccessories.SaveLoad import SaveLoad as SaveLoad

        config = SaveLoad(os.path.join(self.script_dir, "config.json"), create=True)

        self.API_KEY = config.get('api_key')
        if not re.match(r"^\w{32}$", self.API_KEY):
            self.t.time_print("Invalid Galaxy API key.")
            exit(1)

        self.WORKFLOW_ID = config.get('workflow_id', default='f2db41e1fa331b3e')  # SNVPhyl paired end
        if not re.match(r"^\w{16}$", self.WORKFLOW_ID):
            self.t.time_print("Invalid workflow ID format.")
            exit(1)

        self.IP = config.get('ip', default="http://192.168.1.3:48888/")
        self.NASMNT = os.path.normpath(config.get('nasmnt', default="/mnt/nas/"))

    def wait_for_problem(self):
        import time
        short_wait = 5
        time_until_giveup = 36
        problem = True
        while problem:
            problem = False
            try:
                self.gi.histories.get_histories()
                return
            except (ConnectionError, requests.exceptions.ConnectionError) as e:
                if e.status_code == 403:  # Invalid API key
                    self.t.time_print("Invalid Galaxy API Key!")
                    exit(1)
                elif 'Max retries exceeded' in str(e.args[0]):
                    self.t.time_print("Error: Galaxy isn't running/connection error.")
                    problem = True
                    if short_wait > 1:
                        self.t.time_print("Waiting 30 seconds...")
                        time.sleep(30)
                        short_wait -= 1
                    else:
                        self.t.time_print("Waiting 1 hour...")
                        time_until_giveup -= 1
                        if time_until_giveup < 1:
                            raise
                        time.sleep(3600)
                else:
                    raise

    def __init__(self, args_in, inputs=None):
        self.max_attempts = 10
        self.uploaded = []  # A list of all uploaded files

        # constants sort of
        self.IP = None
        self.API_KEY = None
        self.WORKFLOW_ID = None
        self.NASMNT = None
        self.inputs = inputs
        self.gi = None

        # Add arguments
        self.reference = args_in.reference
        self.noextract = args_in.noextract
        self.NAME = args_in.history_name if args_in.history_name is not None else "AutoSNVPhyl_%s"\
                                                                                  % time.strftime("%d-%m-%Y")
        self.manual = args_in.manual

        self.script_dir = sys.path[0]
        if not os.path.exists(os.path.join(self.script_dir, 'galaxy_logs')):
            os.makedirs(os.path.join(self.script_dir, 'galaxy_logs'))

        import datetime
        self.t = Timer(log_file=os.path.join(self.script_dir, 'galaxy_logs',
                                             datetime.datetime.now().strftime("%d-%m-%Y_%S:%M:%H")
                                             + "_%s.txt" % self.NAME))
        self.t.set_colour(32)

        self.extractor = None
        self.history_id = None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--reference",
                        help="Input the seqid of the reference file. "
                             "Also tells the program to extract the fastqs in your retrieve.txt. "
                             "If this parameter is not given then it will use the files in your "
                             "upload folder, it will autodetect the reference file as long as it's"
                             "a fasta. ", type=str)
    parser.add_argument("-e", "--noextract", action="store_true",
                        help="Use if you don't want any fastq files to be extracted from the nas.")
    parser.add_argument("-n", "--history_name", type=str,
                        help="Name of the history to create")
    parser.add_argument("-m", "--manual", action="store_true",
                        help="Use the files in your upload directory (can use this in addition to the files extracted)."
                             "If this flag is not used then it will clear the files in your upload directory.")
    # If no arguments
    if len(sys.argv) == 1:
        parser.print_help()
        exit(1)

    args = parser.parse_args()
    runner = AutoSNVPhyl(args)
    runner.run()
