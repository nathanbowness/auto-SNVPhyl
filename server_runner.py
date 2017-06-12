from pyaccessories.TimeLog import Timer
import os
from RedmineAPI.RedmineAPI import RedmineInterface
from pyaccessories.SaveLoad import SaveLoad
from main import AutoSNVPhyl
import base64

import requests
# TODO documentation


class Run(object):
    def main(self, force):
        if self.first_run == 'yes':
            choice = 'y'
            if force:
                raise ValueError('Need redmine API key!')
        else:
            if force:
                choice = 'n'
            else:
                self.t.time_print("Would you like to set the redmine api key? (y/n)")
                choice = input()
        if choice == 'y':
            self.t.time_print("Enter your redmine api key (will be encrypted to file)")
            self.redmine_api_key = input()
            # Encode and send to json file
            self.loader.redmine_api_key_encrypted = self.encode(self.key, self.redmine_api_key).decode('utf-8')
            self.loader.first_run = 'no'
            self.loader.dump(self.config_json)
        else:
            # Import and decode from file
            self.redmine_api_key = self.decode(self.key, self.redmine_api_key)

        import re
        if not re.match(r'^[a-z0-9]{40}$', self.redmine_api_key):
            self.t.time_print("Invalid Redmine API key!")
            exit(1)

        self.redmine = RedmineInterface('http://redmine.biodiversity.agr.gc.ca/', self.redmine_api_key)

        self.main_loop()

    @staticmethod
    def generate_args(inputs):
        import argparse

        args = argparse.Namespace()
        args.reference = inputs['reference']
        args.history_name = inputs['name']
        args.noextract = False
        args.manual = False  # Change this to true if you want to manually run the snvphyl

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
            if line.lower().startswith('reference') and len(line) < len('reference') + 3:
                mode = 'ref'
                continue
            elif line.lower().startswith('compare') and len(line) < len('compare') + 3:
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
                    pass
                    raise ValueError("Invalid seq-id \"%s\"" % line)

        if inputs['reference'] is None or len(inputs['fastqs']) < 1:
            raise ValueError("Invalid format for redmine request.")

        return inputs

    def completed_response(self, result_path, redmine_id):
        from RedmineAPI.RedmineAPI import RedmineUploadError
        notes = "Completed running SNVPhyl. Results stored at %s" % os.path.join("NAS/bio_requests/%s" %
                                                                                              redmine_id)
        try:
            self.redmine.upload_file(result_path, redmine_id, 'application/zip',
                                     file_name_once_uploaded="SNVPhyl_%s_Results.zip" % redmine_id)
        except RedmineUploadError:
            notes = "Couldn't upload your file to redmine. Results stored at %s" % \
                  os.path.join("NAS/bio_requests/%s" % redmine_id)

        # Assign it back to the author
        get = self.redmine.get_issue_data(redmine_id)

        self.redmine.update_issue(redmine_id, notes + self.botmsg, status_change=4, assign_to_id=get['issue']['author']['id'])

    def run_snvphyl(self, inputs):
        # Parse input
        args = self.generate_args(inputs)
        # noinspection PyBroadException
        from main import AutoSNVPhylError
        try:
            runner = AutoSNVPhyl(args, inputs=inputs)
            result_path = runner.run()
            # SNVPhyl finished, copy the zip to the NAS
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
            self.completed_response(result_path, inputs['name'])

        except Exception as e:
            import traceback
            self.t.time_print("[Warning] AutoSNVPhyl had a problem, continuing redmine api anyways.")
            self.t.time_print("[AutoSNVPhyl Error Dump]\n" + traceback.format_exc())
            # Send response
            if type(e) == AutoSNVPhylError or ValueError:
                msg = str(e)
            else:
                msg = traceback.format_exc()

            # Set it to feedback and assign it back to the author
            get = self.redmine.get_issue_data(inputs['name'])
            self.redmine.update_issue(
                                      inputs['name'],
                                      notes="There was a problem with your SNVPhyl. Please create a new issue on"
                                            " Redmine to re-run it.\n%s" % msg + self.botmsg,
                                      status_change=4,
                                      assign_to_id=get['issue']['author']['id']
                                      )

    def main_loop(self):
        import time
        while True:
            self.clear_space()
            self.make_call()
            self.t.time_print("Waiting for next check.")
            time.sleep(self.seconds_between_redmine_checks)

    def clear_space(self):
        from bioblend.galaxy import GalaxyInstance
        from bioblend import ConnectionError
        gi = GalaxyInstance(self.loader.get('ip', default='http://192.168.1.3:48888/'), key=self.loader.get('api_key'))
        self.t.time_print("Clearing space on Galaxy")

        while True:
            try:
                available = gi.histories.get_histories()  # Ping galaxy
                break
            except ConnectionError as e:
                if e.status_code == 403:  # Invalid API key
                    self.t.time_print("Invalid Galaxy API Key!")
                    del self.loader.__dict__['api_key']
                    self.loader.dump()
                    self.loader.get('api_key')
                elif 'Max retries exceeded' in str(e.args[0]):
                    self.t.time_print("Error: Galaxy isn't running/connection error.")
                    self.t.time_print("Waiting 1 hour...")
                    import time
                    time.sleep(3600)
                else:
                    raise

        if len(available) >= self.max_histories:
            msg = 'Clearing data.'
        else:
            msg = 'Not clearing data.'

        self.t.time_print("Currently %d histories on Galaxy. %s" % (len(available), msg))
        while len(available) > self.max_histories:
            self.t.time_print("Deleting history %s to clear space..." % available.pop(len(available)-1)['name'])
            try:
                gi.histories.delete_history(available[-1]['id'], purge=True)
            except ConnectionError as e:
                if e.status_code == 403:  # Invalid API key
                    self.t.time_print("Invalid Galaxy API Key!")
                    exit(1)
                elif 'Max retries exceeded' in str(e.args[0]):
                    self.t.time_print("Error: Galaxy isn't running/connection error.")
                    exit(1)
                else:
                    raise

        self.t.time_print("Finished clearing space")

    def make_call(self):
        self.t.time_print("Checking for SNVPhyl requests...")

        data = self.redmine.get_new_issues('cfia')

        found = []

        for issue in data['issues']:
            if issue['id'] not in self.responded_issues and issue['status']['name'] == 'New':
                if issue['subject'].lower() == 'snvphyl':
                    found.append(issue)

        self.t.time_print("Found %d issues..." % len(found))

        while len(found) > 0:  # While there are still issues to respond to
            self.respond_to_issue(found.pop(len(found)-1))
            self.clear_space()

    def respond_to_issue(self, issue):
        # Run snvphyl
        if self.redmine.get_issue_data(issue['id'])['issue']['status']['name'] == 'New':
            self.t.time_print("Found SNVPhyl to run. Subject: %s. ID: %s" % (issue['subject'], issue['id']))
            self.t.time_print("Adding to responded to")
            self.responded_issues.add(issue['id'])
            self.issue_loader.responded_issues = list(self.responded_issues)
            self.issue_loader.dump()

            # Turn the description into a list of lines
            input_list = issue['description'].split('\n')
            input_list = map(str.strip, input_list)  # Get rid of \r
            error = False
            try:
                inputs = self.get_input(input_list, issue['id'])
                response = "Running SNVPhyl with reference %s\n\nComparing to:" % inputs['reference']
                for fastq in list(inputs['fastqs']):
                    response += '\n' + fastq
                if inputs['reference'] not in inputs['fastqs']:
                    response += "Did you mean to not compare the reference to itself?"  # TODO ask for answer

            except ValueError as e:
                response = "Sorry, there was a problem with your SNVPhyl request:\n%s\n" \
                           "Please submit a new request and close this one." % e.args[0]
                error = True

            # Rename file'Invalid name to rename %s. Ignoring.'s if the rename.txt text file is include
            more_msg, inputs['rename'] = self.rename_files(issue['id'])
            if more_msg is not None:
                response += '\n' + more_msg

            self.t.time_print('\n' + response)

            if error:  # If something went wrong set the status to feedback and assign the author the issue
                get = self.redmine.get_issue_data(issue['id'])
                self.redmine.update_issue(issue['id'], notes=response + self.botmsg, status_change=4,
                                          assign_to_id=get['issue']['author']['id'])
            else:
                # Set the issue to in progress since the SNVPhyl is running
                self.redmine.update_issue(issue['id'], notes=response + self.botmsg, status_change=2)

            if error:
                return
            else:
                self.run_snvphyl(inputs)

    def rename_files(self, issue_id):
        self.t.time_print('Looking for rename.txt')
        data = self.redmine.get_issue_data(issue_id)
        try:
            attachments = data['issue']['attachments']
            self.t.time_print('Found attachment to redmine request.')
        except KeyError:
            # No attachments
            return None, []
        rename = None
        for attachment in attachments:
            if attachment['filename'] == 'rename.txt':
                # Good
                self.t.time_print('Found rename.txt, downloading...')
                rename = self.redmine.download_file(attachment['content_url'])
                break

        if rename is None:
            return None, []

        import re
        regex = r'([^\t\n]+)(?:,|\n)([^\t\n]+)'  # Matches a list of comma separated pairs eg. seq,a,seq2,b
        pairs = re.findall(regex, rename)

        if len(pairs) == 0:
            return 'Invalid rename.txt file.', []

        # Check its a good file
        ignore = []
        for pair in pairs:
            # Check duplicate
            for compare in pairs:
                if pair[0] == compare[0]:
                    if pair[1] != compare[1]:
                        return 'Not using rename.txt because of duplicate definition in the rename.txt file', []
                    # Otherwise let it go

            # Make sure its valid
            regex = r'.+'  # TODO actual regex
            if not re.fullmatch(regex, pair[1]):
                ignore.append(pair)

        # Feedback
        msg = "Renaming files before starting SNVPhyl."
        if len(ignore) > 0:
            msg += 'Some names were invalid and were ignored:\n'
            for out in ignore:
                msg += '\n%s' % out[1]

        # Convert to dict
        result = {}
        for pair in pairs:
            result[pair[0]] = pair[1]

        return msg, result

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

    def __init__(self, force):
        # import logging
        # logging.basicConfig(level=logging.INFO)
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
        self.responded_issues = set(self.issue_loader.get('responded_issues', default=[], ask=False))

        # Get encrypted api key from config
        # Load the config
        self.loader = SaveLoad(self.config_json, create=True)
        self.redmine_api_key = self.loader.get('redmine_api_key_encrypted', default='none', ask=False)

        # If it's the first run then this will be yes
        self.first_run = self.loader.get('first_run', default='yes', ask=False)

        self.nas_mnt = os.path.normpath(self.loader.get('nasmnt', default="/mnt/nas/", get_type=str))
        self.max_histories = self.loader.get('max_histories', default=6, get_type=int)
        self.seconds_between_redmine_checks = (self.loader.get('seconds_between_redmine_checks', default=600, get_type=int))

        # Make sure all the arguments are there
        self.loader.get('workflow_id', default="f2db41e1fa331b3e")
        self.loader.get('ip', default="http://192.168.1.3:48888/")
        self.key = 'Sixteen byte key'

        self.redmine = None

        self.botmsg = '\n\n_I am a bot. This action was performed automatically._'

        try:
            self.main(force)
        except Exception as e:
            import traceback
            self.t.time_print("[Error] Dumping...\n%s" % traceback.format_exc())
            raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--force", action="store_true",
                        help="Don't ask to update redmine api key")

    args = parser.parse_args()
    Run(args.force)
