# Written by Devon Mack April-May 2017
# This program takes a 5 parameters in the config file and runs a SNVPhyl in galaxy fully automatically
# Parameters (when it doubt, delete the config.json file and the program will create it for you with defaults):
#  config.json
#   api_key: The API key which must be generated in galaxy
#   workflow_id: The ID of the SNVPhyl workflow
#   ip: The ip of galaxy (with port)
#   name: The prefix of the history name
#   nasmnt: The directory of the NAS mount
#   redmine:
# TODO INDEX EXTERNAL WGS SPADES
# TODO MAKE SEPARATE SCRIPT FOR REDMINE REST API AND FOR CREATING LOG FILE
import os
import sys
import re
import time
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy import dataset_collections as collections
from pyaccessories.TimeLog import Timer


class AutoSNVPhyl(object):
    def main(self):
        self.t.time_print("Creating history " + self.NAME)
        self.history_id = self.gi.histories.create_history(self.NAME)['id']
        self.t.time_print(self.history_id)
        self.t.time_print("Uploading files to galaxy...")

        # TODO http error
        # Upload files that are in the upload folder
        if not self.noextract:
            self.t.time_print("Finding files on the NAS...")
            to_upload = self.extract_files()
            self.t.time_print("Uploading files from the NAS...")
            n = 1
            nfiles = len(to_upload)
            for file in to_upload:
                self.t.time_print("%d of %d: Uploading %s" % (n, nfiles, file))
                self.gi.tools.upload_file(os.path.join("upload", file), self.history_id)
                n += 1

        if self.manual:
            self.t.time_print("Using files in upload folder since -m was used")
            n = 1
            files = os.listdir("upload")
            nfiles = len(files)
            for file in files:
                self.t.time_print("%d of %d: Uploading %s" % (n, nfiles, file))
                self.gi.tools.upload_file(os.path.join("upload", file), self.history_id)
                n += 1

        self.t.time_print("Waiting for files to finish uploading...")
        while self.gi.histories.show_history(self.history_id)["state"] != "ok":
            time.sleep(10)

        self.t.time_print("Finished uploading...")
        self.t.time_print("Building list of dataset pairs...")
        self.build_list()

        self.t.time_print("Starting workflow...")
        self.run_workflow()
        time.sleep(10)  # Give it a bit of time to start the workflow
        done = False
        self.t.time_print("Waiting for workflow to finish.")
        wait = 0

        history_state = self.gi.histories.show_history(self.history_id)["state"]
        while history_state != "ok":
            wait += 1
            if wait > 60: # 10 minutes
                self.t.time_print("Still waiting for workflow to finish.")
                wait = 0

            time.sleep(10)
            history_state = self.gi.histories.show_history(self.history_id)["state"]
            if history_state == "error":
                print("Something went wrong! Check the galaxy history called " +
                      self.gi.histories.show_history(self.history_id)["name"])
                break

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

        print("Downloading files:")
        for dataset in self.gi.histories.show_history(self.history_id, contents=True):
            if dataset["name"] in to_download:
                print("    Downloading " + dataset["name"])
                self.gi.datasets.download_dataset(dataset["id"], "results", wait_for_completion=True, )

        self.t.time_print("Completed")
        # TODO LOGS (w/ list of all the files used in the SNVPhyl)

    def extract_files(self):
        from sequence_getter import SequenceGetter

        extractor = SequenceGetter(nasmnt=self.NASMNT, output=False)
        try:
            f = open("retrieve.txt", "r")
            # Get all of the ids in the file
            ids = re.findall(r"\n*(2\d{3}-\w+-\d{4})\n*",f.read())
            f.close()
        except FileNotFoundError:
            # create blank file
            open("retrieve.txt").close()
            print("Please enter SEQids in the retrieve.txt file")
            sys.exit(1)

        # Finds the invalid lines and output them
        for line in open("retrieve.txt", "r"):
            if line.rstrip("\n") not in ids:
                self.t.time_print("Invalid seqid: " + line.rstrip("\n"))

        # Get paths of fastq's
        path_list = []
        for seqid in ids:
            for i in [1, 2]:
                path_list.append(extractor.retrieve_file(seqid.rstrip("\n"), filetype="fastq_R" + str(i),
                                                          getpathonly=True))

        if self.reference is not None:
            # Get fasta
            path_list.append(extractor.retrieve_file(self.reference, "fasta", getpathonly=True))
        else:
            self.t.time_print("No reference file specified, using the one in the upload directory")
            #TODO make it check for one in the upload directory if they don't use this.
        return path_list

    def run_workflow(self):
        contents = self.gi.histories.show_history(self.history_id,contents=True)

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
            sys.exit(1)

        if not found_collection:
            self.t.time_print("[Error] Can't find list of dataset pairs on Galaxy.")
            sys.exit(1)

        min_coverage = "10"
        min_mean_mapping = "30"
        alternative_allele_proportion = "0.75"

        params = {
            '5': {
                'mindepth': min_coverage
            },
            '11': {
                'coverage': min_coverage,
                'mean_mapping': min_mean_mapping,
                'ao': alternative_allele_proportion
            },

        }

        self.gi.workflows.invoke_workflow(self.WORKFLOW_ID, inputs=datamap, params=params, history_id=self.history_id)

    def build_list(self):
        contents = self.gi.histories.show_history(self.history_id,contents=True)
        fastqs = []

        # get fastq files
        for item in contents:
            if item["history_content_type"] == "dataset" and item["extension"] == "fastq":
                fastqs.append(item)

        # pair fastq files
        R1s = []
        R2s = []
        for fastq in fastqs:
            result1 = re.findall(r"(.+)_[Rr]1", fastq["name"], flags=0)
            result2 = re.findall(r"(.+)_[Rr]2", fastq["name"], flags=0)
            if len(result1) >= 1:
                fastq["name"] = result1[0]
                R1s.append(fastq)
            if len(result2) >= 1:
                fastq["name"] = result2[0]
                R2s.append(fastq)

        if len(R1s) != len(R2s):
            self.t.time_print("[WARNING] There are different amounts of R1 and R2 files, will only use ones that can be paired.")

        pairs = []
        done = []

        for sequence in R1s:
            for compare in R2s:
                if sequence["name"] == compare["name"] and sequence["name"] not in done:
                    # Pair them
                    done.append(sequence["name"])
                    pairs.append(collections.CollectionElement(sequence["name"], type="paired",
                        elements=[
                            collections.HistoryDatasetElement(name="forward",id=sequence["id"]),
                            collections.HistoryDatasetElement(name="reverse", id=compare["id"])
                        ]))

        collection_description = collections.CollectionDescription("pair_list", type="list:paired", elements=pairs)
        self.gi.histories.create_dataset_collection(self.history_id, collection_description)

    def load(self):
        reqs = ["ip",
                "api_key",
                "workflow_id",
                "nasmnt"
                ]
        from pyaccessories.SaveLoad import SaveLoad as SaveLoad

        config = SaveLoad()

        import json.decoder
        try:
            if not config.load("config.json", create=True):  # If there was no config file
                config.ip = "http://192.168.1.3:48888/"
                config.api_key = "<API_KEY>"
                config.workflow_id = "f2db41e1fa331b3e"  # SNVPhyl paired end
                config.nasmnt = "/mnt/nas/"
                config.dump("config.json")
                print("Created config.json, please edit it and put in values.")
                exit(1)
        except json.decoder.JSONDecodeError:
            self.t.time_print("Invalid config.json")
            raise

        for requirement in reqs:
            if requirement not in config.__dict__:
                self.t.time_print("Invalid config file config.json")
                sys.exit(1)

        if re.match(r"^\w{32}$", config.api_key):
            self.API_KEY = config.api_key
        else:
            self.t.time_print("Invalid Galaxy API key.")
            sys.exit(1)

        if re.match(r"^\w{16}$", config.workflow_id):
            self.WORKFLOW_ID = config.workflow_id
        else:
            self.t.time_print("Invalid workflow ID format.")
            sys.exit(1)

        self.IP = config.ip
        self.NASMNT = os.path.normpath(config.nasmnt)

    def __init__(self, args):
        self.IP = None
        self.API_KEY = None
        self.WORKFLOW_ID = None
        self.NASMNT = None


        # Add arguments
        self.redmine = args.redmine
        self.reference = args.reference
        self.noextract = args.noextract
        self.NAME = args.history_name if args.history_name is not None else "AutoSNVPhyl_%s" % time.strftime("%d-%m-%Y")
        self.manual = args.manual

        self.t = Timer()
        self.t.set_colour(32)



        self.history_id = None
        self.load()
        self.gi = GalaxyInstance(self.IP, key=self.API_KEY)
        self.main()

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
                        help="Use if you don't want your fastq files to be extracted and only want the ones in upload")
    parser.add_argument("-n", "--history_name", type=str,
                        help="Name of the history to create")
    parser.add_argument("-i", "--redmine", type=int,
                        help="Set a redmine ticket id to put the lists in")
    parser.add_argument("-m", "--manual", action="store_true",
                        help="Use the files in your upload directory (can use this in addition to the files extracted)."
                             "If this flag is not used then it will clear the files in your upload directory.")
    args = parser.parse_args()
    AutoSNVPhyl(args)


