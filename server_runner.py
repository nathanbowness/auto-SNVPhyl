from pyaccessories.TimeLog import Timer
import os
from pyaccessories.SaveLoad import SaveLoad
from main import AutoSNVPhyl
import base64
import requests
# TODO documentation on how to request API key


class Run(object):
    def main(self):
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

        self.main_loop()

    @staticmethod
    def generate_args(inputs):
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

        args = parser.parse_args()
        args.reference = inputs['reference']
        args.history_name = inputs['name']
        return args

    @staticmethod
    def get_input(input_file, redmine_id):
        mode = 'none'
        regex = r"^(2\d{3}-\w{2,10}-\d{3,4})$"
        inputs = {
            'reference': None,
            'fastqs': list(),
            'name': str(redmine_id)
        }
        import re
        for line in input_file:
            # Check for mode changes
            if line.lower() == 'reference':
                mode = 'ref'
                continue
            elif line.lower() == 'compare':
                mode = 'comp'
                continue
            elif line.lower() == '':
                # Blank line
                mode = 'none'
                continue

            if inputs['reference'] is not None and len(inputs['fastqs']) > 0 and mode == 'none':
                # Finished gathering all input
                break

            # Get seq-id
            if mode == 'ref':
                if re.match(regex, line):
                    inputs['reference'] = line
                else:
                    raise ValueError("Invalid seq-id \"%s\"" % line)
            elif mode == 'comp':
                if re.match(regex, line):
                    inputs['fastqs'].append(line)
                else:
                    raise ValueError("Invalid seq-id \"%s\"" % line)

        if inputs['reference'] is None or len(inputs['fastqs']) < 1:
            raise ValueError("Invalid format for redmine request.")

        return inputs

    def run_snvphyl(self, inputs):
        # Parse input
        args = self.generate_args(inputs)
        try:
            runner = AutoSNVPhyl(args, inputs=inputs['fastqs'])
            result_path = runner.run()
            import shutil
            bio_request_folder = os.path.join(self.nas_mnt, 'bio_requests', inputs['name'])
            # Create folder with redmine id
            self.t.time_print("Creating directory %s" % bio_request_folder)
            if not os.path.exists(os.path.join(bio_request_folder)):
                os.makedirs(bio_request_folder)

            # Copy results to bio_request folder
            self.t.time_print("Copying %s to %s" % (result_path, bio_request_folder))
            shutil.copy(result_path, bio_request_folder)

            # Respond on redmine

        except Exception:
            import traceback
            self.t.time_print("[Warning] AutoSNVPhyl had a problem, continuing redmine api anyways.")
            self.t.time_print("[AutoSNVPhyl Error Dump]\n" + traceback.format_exc())

    def main_loop(self):
        import time
        while True:
            try:
                self.make_call()
            except ValueError as e:
                self.t.time_print("[Error] %s" % e)
            time.sleep(100)

    def make_call(self):
        url = "http://redmine.biodiversity.agr.gc.ca/projects/cfia/issues.json"
        self.t.time_print("Checking for SNVPhyl requests...")
        self.t.time_print("Sending GET request to %s" % url)
        headers = {'X-Redmine-API-Key': self.redmine_api_key}
        resp = requests.get(url, headers=headers)

        import json
        data = json.loads(resp.content.decode("utf-8"))
        for issue in data['issues']:
            if issue['id'] not in self.responded_issues and issue['status']['name'] == 'In Progress':
                # if issue['subject'].lower() == 'snvphyl':
                if issue['subject'].lower().startswith('snvphyl'):
                    self.respond_to_issue(issue)

    def respond_to_issue(self, issue):
        # Run snvphyl
        self.t.time_print("Found SNVPhyl to run. Subject: %s. ID: %d" % (issue['subject'], issue['id']))
        self.t.time_print("Adding to responded to")
        # TODO addback> self.responded_issues.add(issue['id'])
        self.issue_loader.responded_issues = list(self.responded_issues)
        self.issue_loader.dump(os.path.join(self.script_dir, 'responded_issues.json'))

        # Turn the description into a list of lines
        input_list = issue['description'].split('\n')
        input_list = map(str.strip, input_list)  # Get rid of \r
        error = False
        try:
            inputs = self.get_input(input_list, issue['id'])
            response = "Running SNVPhyl with reference %s\n\nComparing to:" % inputs['reference']
            for fastq in list(inputs['fastqs']):
                response += '\n' + fastq
        except ValueError as e:
            response = "Sorry, there was a problem with your SNVPhyl request:\n%s\n" \
                       "Please submit a new request and close this one." % e.args[0]
            error = True
        self.t.time_print('\n' + response)
        # Respond
        url = 'http://redmine.biodiversity.agr.gc.ca/issues/%d.json' % issue['id']
        headers = {'X-Redmine-API-Key': self.redmine_api_key, 'content-type': 'application/json'}
        id = 67
        data = {
            "issue": {
                "notes": response,
            }
        }
        if error:  # If something went wrong set the status to feedback and assign the author the issue
            data['issue']["status_id"] = 4
            import json
            get = json.loads(requests.get(url, headers=headers).content.decode("utf-8"))
            data['issue']['assigned_to_id'] = str(get['issue']['author']['id'])
            print(data)
        else:
            data['issue']["status_id"] = 2

        resp = requests.put(url, headers=headers, json=data)
        print(resp.status_code)

        if error:
            return
        self.run_snvphyl(inputs)

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

    def __init__(self):
        # Vars
        import sys
        self.script_dir = sys.path[0]
        self.config_json = os.path.join(self.script_dir, "config.json")

        # Set up timer/logger
        import datetime
        if not os.path.exists(os.path.join(self.script_dir, 'runner_logs')):
            os.makedirs(os.path.join(self.script_dir, 'runner_logs'))
        self.t = Timer(log_file=os.path.join(self.script_dir, 'runner_logs',
                                        datetime.datetime.now().strftime("%d-%m-%Y_%S:%M:%H")))
        self.t.set_colour(30)

        # Load issues that the bot has already responded to
        self.issue_loader = SaveLoad(os.path.join(self.script_dir, 'responded_issues.json'), create=True)
        if "responded_issues" not in self.issue_loader.__dict__:
            self.responded_issues = set()
            self.issue_loader.responded_issues = list(self.responded_issues)
            self.issue_loader.dump(os.path.join(self.script_dir, 'responded_issues.json'))
        else:
            self.responded_issues = set(self.issue_loader.responded_issues)

        # Load the config
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

        if 'nasmnt' not in self.loader.__dict__:
            self.t.time_print('[Error] Can\'t find nasmnt in config file!')
            sys.exit(1)

        # Get encrypted api key from config
        self.redmine_api_key = self.loader.redmine_api_key_encrypted
        self.nas_mnt = self.loader.nasmnt
        self.key = 'Sixteen byte key'
        self.main()


if __name__ == "__main__":
    Run()
