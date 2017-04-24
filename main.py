import os
import sys
import re
import time
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy import dataset_collections as collections
class AutoSNVPhyl(object):
    def main(self):
        print("Creating history " + self.name)
        #self.history_id = self.gi.histories.create_history(self.name)['id']
        print(self.history_id)
        self.history_id = "4b187121143038ff"
        for file in os.listdir("upload"):
            print(file)
        #    print(self.gi.tools.upload_file(os.path.join("upload", file), self.history_id))

        done = False
        while done == False:
            time.sleep(10)
            done = True

            for dataset in self.gi.histories.show_history(self.history_id, contents=True):
                print(dataset)
                try:
                    if dataset["state"] != "ok":
                        done = False
                except KeyError:
                    pass
        self.build_list()

        print("Completed.")

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
            result1 = re.findall(r"([\w\-_]+)_R1", fastq["name"], flags=0)
            result2 = re.findall(r"([\w\-_]+)_R2", fastq["name"], flags=0)
            if len(result1) >= 1:
                fastq["name"] = result1[0]
                R1s.append(fastq)
            if len(result2) >= 1:
                fastq["name"] = result2[0]
                R2s.append(fastq)

        if len(R1s) != len(R2s):
            print("[WARNING] There are different amounts of R1 and R2 files, will only use ones that can be paired.")

        print("pairing...")
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
        print(pairs)
        self.gi.histories.create_dataset_collection(self.history_id, collection_description)

    def load(self):
        from pyaccessories.SaveLoad import SaveLoad as SaveLoad

        config = SaveLoad()
        config.load("config.json", create=True)
        if "ip" not in config.__dict__ and "api_key" not in config.__dict__:
            config.ip = "<IP>"
            config.api_key = "<API_KEY>"
            config.workflow_id = "f2db41e1fa331b3e"  # SNVPhyl paired end
            config.dump("config.json")
            sys.exit(1)

        self.API_KEY = config.api_key
        self.IP = config.ip
        self.WORKFLOW_ID = config.workflow_id

        print("Using " + self.API_KEY + " as API key.")

    def create_paired_dataset(self):
        pass

    def __init__(self):
        self.name = "testname"
        self.IP = None
        self.API_KEY = None
        self.WORKFLOW_ID = None
        self.history_id = None
        self.load()
        self.gi = GalaxyInstance(self.IP, key=self.API_KEY)
        self.main()


AutoSNVPhyl()
