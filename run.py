from pyaccessories.TimeLog import Timer
import os
from pyaccessories.SaveLoad import SaveLoad
from main import AutoSNVPhyl
import base64
import requests
# TODO documentation on how to request API key


class Run(object):
    def main(self, args_in):
        self.t.time_print("Would you like to set the redmine api key? (y/n)")
        if input() == 'y':
            self.t.time_print("Enter the new api key (will be encrypted to file)")
            self.redmine_api_key = input()
            self.loader.redmine_api_key_encrypted = self.encode(self.key, self.redmine_api_key).decode('utf-8')
            self.loader.dump("config.json")
        else:
            self.redmine_api_key = self.decode(self.key, self.redmine_api_key)
            # TODO remove this line
            self.t.time_print("Using %s as api key" % self.redmine_api_key)

        self.make_call()

        # Parse input
        import re
        path_to_list = os.path.join(self.script_dir, "input.txt")
        try:
            f = open(path_to_list, "r")
            # Get all of the ids in the file
            # Get all of the ids in the file
            ids = re.findall(r"(2\d{3}-\w{2,10}-\d{3,4})", f.read())
            f.close()
        except FileNotFoundError:
            # create blank file
            open(path_to_list, "w").close()
            self.t.time_print("[Error] Please enter SEQids in the input.txt file")
            sys.exit(1)

        if len(ids) < 1:
            self.t.time_print("[Error] Please enter SEQids in the input.txt file")
            sys.exit(1)

        # Finds the invalid lines and output them
        for line in open(path_to_list, "r"):
            if line.rstrip("\n") not in ids and len(line.rstrip("\n")) > 2:
                self.t.time_print("Invalid seqid: %s" % line.rstrip("\n"))

        try:
            runner = AutoSNVPhyl(args_in, retrievelist=ids)
            resultzip = runner.run()
        except Exception:
            import traceback
            self.t.time_print("[Warning] AutoSNVPhyl had a problem, continuing redmine api anyways.")
            self.t.time_print("[AutoSNVPhyl Error Dump]\n" + traceback.format_exc())

    def make_call(self):
        url = "http://redmine.biodiversity.agr.gc.ca/projects/cfia/issues.json"
        headers = {'X-Redmine-API-Key': self.redmine_api_key}
        resp = requests.get(url, headers=headers)
        print(resp.status_code)
        import json
        data = json.loads(resp.content.decode("utf-8"))

    @staticmethod
    def encode(key, string):
        encoded_chars = []
        for i in range(len(string)):
            key_c = key[i % len(key)]
            encoded_c = chr(ord(string[i]) + ord(key_c) % 256)
            encoded_chars.append(encoded_c)
        encoded_string = "".join(encoded_chars)
        encoded_string = bytes(encoded_string, "utf-8")

        return base64.urlsafe_b64encode(encoded_string)

    @staticmethod
    def decode(key, string):
        decoded_chars = []
        string = base64.urlsafe_b64decode(string).decode('utf-8')
        for i in range(len(string)):
            key_c = key[i % len(key)]
            encoded_c = chr(abs(ord(str(string[i]))
                                - ord(key_c) % 256))
            decoded_chars.append(encoded_c)
        decoded_string = "".join(decoded_chars)

        return decoded_string

    def __init__(self, args_in):
        self.script_dir = sys.path[0]
        self.config_json = os.path.join(self.script_dir, "config.json")
        import datetime
        if not os.path.exists(os.path.join(self.script_dir, 'runner_logs')):
            os.makedirs(os.path.join(self.script_dir, 'runner_logs'))
        self.t = Timer(log_file=os.path.join(self.script_dir, 'runner_logs',
                                        datetime.datetime.now().strftime("%d-%m-%Y_%S:%M:%H")))
        self.t.set_colour(30)

        # Load
        self.loader = SaveLoad(self.config_json)
        import json.decoder
        try:
            # If there was no config file
            if not self.loader.load(os.path.join(self.script_dir, "config.json"), create=True):
                self.loader.ip = "http://192.168.1.3:48888/"
                self.loader.api_key = "<API_KEY>"
                self.loader.workflow_id = "f2db41e1fa331b3e"  # SNVPhyl paired end
                self.loader.nasmnt = "/mnt/nas/"
                self.loader.dump(os.path.join(self.script_dir, "config.json"))
                self.loader.redmine_api_key = ""

                self.t.time_print("Created config.json, please edit it and put in values.")
                exit(1)
        except json.decoder.JSONDecodeError:
            self.t.time_print("[Error] Invalid config.json")
            raise

        if "redmine_api_key_encrypted" not in self.loader.__dict__:
            self.t.time_print("[Error] Invalid config file config.json, missing \"redmine_api_key_encrypted\"")
            sys.exit(1)

        # Get encrypted api key from config
        self.redmine_api_key = self.loader.redmine_api_key_encrypted

        self.key = 'Sixteen byte key'
        self.main(args_in)


if __name__ == "__main__":
    import sys
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

    Run(args)
